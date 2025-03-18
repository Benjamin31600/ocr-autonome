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
    sanitized = re.sub(r'(?i)S\s*/\s*N\s*[:,\-]?', '', num)
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

# --- Fonction pour surligner les caractères ambigus ---
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

# --- Interface et styles ---
st.set_page_config(page_title="Daher – OCR & Barcode Validation", page_icon="✈️", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    body { background: #f0f2f6; font-family: 'Poppins', sans-serif; color: #333; margin: 0; padding: 0; }
    [data-testid="stAppViewContainer"] { background: #fff; border-radius: 20px; padding: 2rem 3rem; max-width: 1400px; margin: 2rem auto; box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin-bottom: 1rem; }
    .validated { border: 2px solid green; background-color: #e6ffe6; padding: 8px; border-radius: 8px; }
    .nonvalidated { border: 2px solid red; background-color: #ffe6e6; padding: 8px; border-radius: 8px; }
    .confidence { font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Barcode Validation")
st.write("Téléversez vos pages. L'outil extrait les segments et affiche l'indice de confiance. Pour les segments douteux (< 99%), vous devez valider via un bouton de correction (choix rapide parmi suggestions). Pour les segments fiables, un simple appui sur 'Confirmer' suffit.")

# --- Charger le modèle OCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement des images ---
uploaded_files = st.file_uploader("Téléchargez les pages (png, jpg, jpeg)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
validated_segments = []

if uploaded_files:
    for i, file in enumerate(uploaded_files):
        st.subheader(f"Page {i+1}")
        image = Image.open(file)
        image = correct_image_orientation(image)
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
        
        # Simuler une segmentation en fonction des espaces (à adapter selon le layout)
        segments = [sanitize_number(seg) for seg in ocr_text.split()]
        page_validated = []
        for j, seg in enumerate(segments):
            st.markdown(f"**Segment {j+1} :** {highlight_confusions(seg)}")
            conf = confidences[j] if j < len(confidences) else 1.0
            conf_pct = conf * 100
            st.progress(int(conf_pct))
            st.markdown(f"<div class='confidence'>Confiance : {conf_pct:.0f}%</div>", unsafe_allow_html=True)
            
            if conf_pct < 99:
                # Pour les segments douteux, proposer une correction via menu déroulant
                suggestions = generate_candidates(seg)
                suggestions = [s for s in suggestions if s != seg]
                if not suggestions:
                    suggestions = [seg]  # fallback
                st.markdown("<span style='color:red'>Segment douteux. Veuillez choisir une correction différente.</span>", unsafe_allow_html=True)
                choice = st.selectbox("Correction proposée", options=suggestions, key=f"corr_{i}_{j}")
                if choice == seg:
                    st.error("La correction doit être différente du résultat initial.")
                    valid = False
                else:
                    valid = True
                    final_seg = sanitize_number(choice)
            else:
                # Pour segments fiables, proposer simplement une confirmation
                if st.button("Confirmer", key=f"conf_{i}_{j}"):
                    valid = True
                    final_seg = seg
                else:
                    valid = False
            
            if valid:
                st.markdown(f"<div class='validated'>Segment validé : {final_seg}</div>", unsafe_allow_html=True)
                page_validated.append(final_seg)
            else:
                st.markdown(f"<div class='nonvalidated'>Segment non validé</div>", unsafe_allow_html=True)
        if st.button(f"Confirmer page {i+1}", key=f"page_{i}"):
            if len(page_validated) == len(segments) and page_validated:
                st.success(f"Page {i+1} validée.")
                validated_segments.extend(page_validated)
            else:
                st.error("Tous les segments doivent être validés.")
    
    if st.button("Générer PDF"):
        with st.spinner("Génération du PDF..."):
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            for seg in validated_segments:
                buf = generate_barcode_pybarcode(seg)
                fname = os.path.join(temp_dir, f"barcode_{seg}.png")
                with open(fname, "wb") as f:
                    f.write(buf.getvalue())
                pdf.add_page()
                pdf.image(fname, x=10, y=10, w=pdf.w - 20)
            pdf_path = os.path.join(temp_dir, "barcodes.pdf")
            pdf.output(pdf_path, "F")
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            st.download_button("Télécharger le PDF", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
