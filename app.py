import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ExifTags
import io
import os
import re
import tempfile
from fpdf import FPDF
import time

# --- Fonction de nettoyage renforcé ---
def sanitize_number(num):
    # Convertir en majuscules pour uniformiser
    num = num.upper()
    # Supprimer les préfixes "S/N" ou "SER" éventuellement suivis de ponctuation ou d'espaces
    num = re.sub(r'(S\s*/\s*N|SER)[\s:,\-]*', '', num)
    # Supprimer tous les caractères qui ne sont pas lettres ou chiffres (supprime espaces, tirets, ponctuations, etc.)
    num = re.sub(r'[^0-9A-Z]', '', num)
    return num

# --- Dictionnaire de substitutions classiques (optionnel pour surligner) ---
confusion_pairs = {
    'S': '8',
    '8': 'S',
    'O': '0',
    '0': 'O',
    'I': '1',
    '1': 'I',
}

def highlight_confusions(text):
    result_html = ""
    for char in text:
        if char in confusion_pairs or char in confusion_pairs.values():
            result_html += f"<span style='color:red; font-weight:bold;'>{char}</span>"
        else:
            result_html += char
    return result_html

# --- Fonction pour générer des candidats de correction ---
def generate_candidates(text):
    candidates = set()
    candidates.add(text)
    for i, char in enumerate(text):
        if char in confusion_pairs:
            candidate = text[:i] + confusion_pairs[char] + text[i+1:]
            candidates.add(candidate)
        for k, v in confusion_pairs.items():
            if char == v:
                candidate = text[:i] + k + text[i+1:]
                candidates.add(candidate)
    # Retourne uniquement les candidats différents du texte initial
    return [c for c in candidates if c != text]

def get_best_candidate(text):
    cands = generate_candidates(text)
    return cands[0] if cands else text

# --- Fonction pour corriger l'orientation de l'image ---
def correct_image_orientation(image):
    try:
        exif = image._getexif()
        if exif:
            orientation = exif.get(274)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except Exception as e:
        st.warning(f"Erreur d'orientation : {e}")
    return image

# --- Fonction pour générer un code‑barres (Code128) ---
def generate_barcode_pybarcode(sn):
    sn_clean = sanitize_number(sn)
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn_clean, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Configuration de la page ---
st.set_page_config(page_title="Daher – OCR & Code‑barres Ultra Sécurisé", page_icon="✈️", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        font-family: 'Poppins', sans-serif;
        color: #ffffff;
        margin: 0;
        padding: 0;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255,255,255,0.92);
        backdrop-filter: blur(8px);
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1400px;
        margin: 2rem auto;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    .validated {
        border: 2px solid #00FF00;
        padding: 8px;
        border-radius: 8px;
        background-color: rgba(0,255,0,0.1);
        margin-bottom: 4px;
    }
    .nonvalidated {
        border: 2px solid #FF0000;
        padding: 8px;
        border-radius: 8px;
        background-color: rgba(255,0,0,0.1);
        margin-bottom: 4px;
    }
    .confidence {
        font-weight: bold;
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("Téléversez les pages de votre bordereau. L'outil extrait le texte via OCR, nettoie automatiquement les segments (supprime espaces, tirets, 'S/N', 'SER', etc.) et affiche un indice de confiance sous forme de barre de progression et en pourcentage. Pour chaque segment, l'opérateur doit confirmer la validité via une interface de validation visuelle individuelle. Ensuite, les segments validés serviront à générer les codes‑barres et à assembler un PDF téléchargeable.")

# --- Charger EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement multiple de pages ---
uploaded_files = st.file_uploader("Téléchargez les pages (png, jpg, jpeg)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

overall_start = time.time()
all_validated_serials = []

if uploaded_files:
    st.write("### Traitement des pages")
    for i, file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            image = Image.open(file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale", use_container_width=True)
            
            st.write("Sélectionnez la zone d'intérêt (cadre rouge) :")
            cropped = st_cropper(image, key=f"cropper_{i}")
            st.image(cropped, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR..."):
                results = ocr_reader.readtext(cropped_bytes)
            ocr_text = " ".join([r[1] for r in results])
            confidences = [r[2] for r in results]
            st.write("Texte extrait:", ocr_text)
            
            # Découper le texte en segments (ici par espaces pour simplifier)
            segments = [sanitize_number(seg) for seg in ocr_text.split()]
            
            page_validated = []
            for j, seg in enumerate(segments):
                st.markdown(f"**Segment {j+1} :** {highlight_confusions(seg)}", unsafe_allow_html=True)
                if j < len(confidences):
                    conf = confidences[j]
                    conf_pct = conf * 100
                    st.progress(int(conf_pct))
                    st.markdown(f"<div class='confidence'>Confiance : {conf_pct:.0f}%</div>", unsafe_allow_html=True)
                    
                    if conf_pct < 99:
                        st.error("Segment douteux ! Une correction est requise.")
                        # Génère automatiquement une correction candidate et supprime les caractères indésirables
                        candidate = get_best_candidate(seg)
                        # Propose via un menu déroulant (l'opérateur doit cliquer et confirmer une option différente)
                        selection = st.selectbox("Sélectionnez la correction proposée", options=[candidate], key=f"select_{i}_{j}")
                        if selection == seg:
                            st.error("La correction doit être différente du résultat initial.")
                            validated = False
                        else:
                            validated = True
                            final_seg = sanitize_number(selection)
                    else:
                        # Pour segments fiables, afficher un bouton de validation individuel
                        if st.button(f"Valider ce segment", key=f"confirm_{i}_{j}"):
                            validated = True
                            final_seg = seg
                        else:
                            validated = False
                    if validated:
                        st.markdown(f"<div class='validated'>Segment validé : {final_seg}</div>", unsafe_allow_html=True)
                        page_validated.append(final_seg)
                    else:
                        st.markdown(f"<div class='nonvalidated'>Segment non validé</div>", unsafe_allow_html=True)
                else:
                    st.write("Confiance N/A")
                    page_validated.append(seg)
            if st.button(f"Confirmer cette page", key=f"page_confirm_{i}"):
                if len(page_validated) == len(segments) and page_validated:
                    st.success(f"Page {i+1} validée.")
                    # Pour chaque segment validé, afficher un bouton pour flasher le code barre individuellement
                    barcode_cols = st.columns(3)
                    for j, segment in enumerate(page_validated):
                        if st.button(f"Flasher code barre (segment {j+1})", key=f"flash_{i}_{j}"):
                            barcode_buf = generate_barcode_pybarcode(segment)
                            barcode_cols[j % 3].image(barcode_buf, caption=f"{segment}", use_container_width=True)
                    all_validated_serials.extend(page_validated)
                else:
                    st.error("Tous les segments doivent être validés pour cette page.")
            page_end = time.time()
            st.write(f"Temps de traitement de la page {i+1} : {page_end - page_start:.2f} secondes")
    
    if all_validated_serials and st.button("Générer PDF de tous les codes‑barres"):
        st.write("Génération du PDF...")
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            for seg in all_validated_serials:
                barcode_buf = generate_barcode_pybarcode(seg)
                fname = os.path.join(temp_dir, f"barcode_{seg}.png")
                with open(fname, "wb") as f:
                    f.write(barcode_buf.getvalue())
                pdf.add_page()
                pdf.image(fname, x=10, y=10, w=pdf.w - 20)
            pdf_path = os.path.join(temp_dir, "barcodes.pdf")
            pdf.output(pdf_path, "F")
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            st.download_button("Télécharger le PDF", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
        except Exception as e:
            st.error("Erreur lors de la génération du PDF : " + str(e))
    
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")
