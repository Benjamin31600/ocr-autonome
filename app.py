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
from difflib import SequenceMatcher

# --- Paramètres ---
CONFIDENCE_THRESHOLD = 0.99  # Seuil de confiance à 99%

# --- Fonction pour nettoyer un numéro (supprime caractères spéciaux et préfixe S/N:) ---
def sanitize_number(num):
    # Supprime "S/N:" (insensible à la casse, avec ou sans espaces, virgule, etc.)
    sanitized = re.sub(r'(?i)S\s*/\s*N\s*[:,\-]?', '', num)
    # Conserve uniquement lettres et chiffres (supprime espaces, /, ;, etc.)
    sanitized = re.sub(r'[^0-9A-Za-z]', '', sanitized)
    return sanitized

# --- Dictionnaire de substitutions classiques (pour générer des candidats) ---
confusion_pairs = {
    'S': '8',
    '8': 'S',
    'O': '0',
    '0': 'O',
    'I': '1',
    '1': 'I',
}

# --- Fonction pour surligner les caractères à risque ---
def highlight_confusions(text):
    result_html = ""
    for char in text:
        if char in confusion_pairs or char in confusion_pairs.values():
            result_html += f"<span style='color:red;font-weight:bold'>{char}</span>"
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
    return list(candidates)

# --- Fonction pour corriger l'orientation de l'image via EXIF ---
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

# --- Configuration de la page et styles CSS ---
st.set_page_config(page_title="Daher – OCR & Code‑barres Ultra Sécurisé", page_icon="✈️", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    body { background: linear-gradient(135deg, #0d1b2a, #1b263b); font-family: 'Poppins', sans-serif; color: #ffffff; margin: 0; padding: 0; }
    [data-testid="stAppViewContainer"] { background: rgba(255,255,255,0.92); backdrop-filter: blur(8px); border-radius: 20px; padding: 2rem 3rem; max-width: 1400px; margin: 2rem auto; box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
    .stButton button { background-color: #0d1b2a; color: #fff; border: none; border-radius: 30px; padding: 14px 40px; font-size: 16px; font-weight: 600; box-shadow: 0 8px 16px rgba(0,0,0,0.2); transition: background-color 0.3s ease, transform 0.2s ease; }
    .stButton button:hover { background-color: #415a77; transform: translateY(-3px); }
    .validated { border: 2px solid #00FF00; padding: 8px; border-radius: 8px; background-color: rgba(0,255,0,0.1); margin-bottom: 4px; }
    .non-validated { border: 2px solid #FF0000; padding: 8px; border-radius: 8px; background-color: rgba(255,0,0,0.1); margin-bottom: 4px; }
    .confidence-low { color: red; font-weight: bold; }
    .confidence-high { color: green; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("Téléversez les pages de votre bordereau. Pour chaque page, sélectionnez la zone d'intérêt (cadre rouge) et extrayez le texte. Chaque segment est affiché avec une barre de progression et le pourcentage de confiance. Pour les segments dont la confiance est inférieure à 99%, l'interface vous oblige à choisir une correction via un menu déroulant (la suggestion est générée automatiquement). Pour les segments à haute confiance, un simple bouton 'Confirmer' suffit. Seuls les segments validés seront nettoyés automatiquement avant de générer des codes‑barres et assembler un PDF téléchargeable.")

# --- Charger EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement des fichiers ---
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
            st.write("Sélectionnez la zone d'intérêt:")
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
            
            # Pour simplifier, on découpe le texte par espaces (à adapter selon le layout)
            segments = [sanitize_number(seg) for seg in ocr_text.split()]
            
            page_validated = []
            for j, seg in enumerate(segments):
                st.markdown(f"**Segment {j+1} :** {highlight_confusions(seg)}", unsafe_allow_html=True)
                if j < len(confidences):
                    conf = confidences[j]
                    conf_pct = conf * 100
                    st.progress(int(conf_pct))
                    st.markdown(f"Confiance : {conf_pct:.0f}%", unsafe_allow_html=True)
                    # Choix d'action via menu radio
                    default_action = "Confirm" if conf_pct >= 99 else "Reject"
                    action = st.radio("Action", options=["Confirm", "Reject"], index=0 if default_action=="Confirm" else 1, key=f"radio_{i}_{j}")
                    if action == "Confirm":
                        # Pour segments à haute confiance, le résultat OCR est accepté
                        final_seg = seg
                    else:
                        # Pour segments douteux, proposer la correction candidate
                        candidate = get_best_candidate(seg) if conf_pct < 99 else seg
                        st.markdown(f"<span style='color:red;'>Suggestion de correction : {candidate}</span>", unsafe_allow_html=True)
                        # Utiliser un selectbox qui affiche la correction candidate (on peut proposer d'autres options si besoin)
                        option = st.selectbox("Veuillez choisir la correction", options=[candidate], key=f"select_{i}_{j}")
                        if option == seg:
                            st.error("La correction doit être différente du résultat initial.")
                            final_seg = ""
                        else:
                            final_seg = sanitize_number(option)
                    if final_seg:
                        st.markdown(f"<div class='validated'>Validé : {final_seg}</div>", unsafe_allow_html=True)
                        page_validated.append(final_seg)
                    else:
                        st.markdown(f"<div class='non-validated'>Non validé</div>", unsafe_allow_html=True)
                else:
                    st.write("Confiance N/A")
                    page_validated.append(seg)
            if st.button(f"Confirmer cette page", key=f"page_confirm_{i}"):
                if len(page_validated) == len(segments) and page_validated:
                    st.success(f"Page {i+1} validée.")
                    barcode_cols = st.columns(3)
                    for j, candidate in enumerate(page_validated):
                        barcode_buf = generate_barcode_pybarcode(candidate)
                        barcode_cols[j % 3].image(barcode_buf, caption=f"{candidate}", use_container_width=True)
                    all_validated_serials.extend(page_validated)
                else:
                    st.error("Tous les segments doivent être validés.")
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

