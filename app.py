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

# --- Paramètres ---
CONFIDENCE_THRESHOLD = 0.99  # Si inférieur à 99%, nécessite double tap

# --- Fonction pour nettoyer un numéro (supprimer caractères spéciaux et S/N:) ---
def sanitize_number(num):
    # Supprime S/N: avec ou sans espaces et d'autres caractères non alphanumériques
    sanitized = re.sub(r'(?i)S\s*/\s*N\s*[:\-]?', '', num)
    sanitized = re.sub(r'[^0-9A-Za-z]', '', sanitized)
    return sanitized

# --- Liste de paires de confusion (pour surligner, optionnelle) ---
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
            result_html += f"<span style='color:red; font-weight:bold;'>{char}</span>"
        else:
            result_html += char
    return result_html

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
    .stButton button {
        background-color: #0d1b2a;
        color: #fff;
        border: none;
        border-radius: 30px;
        padding: 14px 40px;
        font-size: 16px;
        font-weight: 600;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
        transition: background-color 0.3s ease, transform 0.2s ease;
    }
    .stButton button:hover {
        background-color: #415a77;
        transform: translateY(-3px);
    }
    .validated {
        border: 2px solid #00FF00;
        padding: 8px;
        border-radius: 8px;
        background-color: rgba(0,255,0,0.1);
        margin-bottom: 4px;
    }
    .non-validated {
        border: 2px solid #FF0000;
        padding: 8px;
        border-radius: 8px;
        background-color: rgba(255,0,0,0.1);
        margin-bottom: 4px;
    }
    .confidence-low {
        color: red;
        font-weight: bold;
    }
    .confidence-high {
        color: green;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("Téléversez les pages de votre bordereau. Sélectionnez la zone d'intérêt (cadre rouge), vérifiez et corrigez le texte extrait, séparez les numéros (un par ligne) et validez-les via un double tap pour les segments avec indice de confiance < 99%. L'indice de confiance est affiché en pourcentage. Les numéros validés seront nettoyés automatiquement avant de générer les codes‑barres et assembler un PDF.")

# --- Charger EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement multiple de pages ---
uploaded_files = st.file_uploader("Téléchargez les pages de votre BL (png, jpg, jpeg)",
                                    type=["png", "jpg", "jpeg"],
                                    accept_multiple_files=True)

overall_start = time.time()
all_validated_serials = []

# Initialisation de la validation double tap pour chaque segment dans la session
if 'double_tap_counts' not in st.session_state:
    st.session_state.double_tap_counts = {}

if uploaded_files:
    st.write("### Traitement des pages")
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone d'intérêt (cadre rouge) :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR avec EasyOCR..."):
                ocr_results = ocr_reader.readtext(cropped_bytes)
            extracted_text = " ".join([res[1] for res in ocr_results])
            confidence_list = [res[2] for res in ocr_results]
            st.markdown("**Texte extrait (avant nettoyage) :**")
            st.write(extracted_text)
            
            st.subheader("Séparez et nettoyez les numéros (un par ligne)")
            manual_text = st.text_area("Chaque ligne doit contenir un numéro (les caractères spéciaux seront supprimés automatiquement) :", 
                                       value=extracted_text, height=150, key=f"manual_{i}")
            # Séparation en lignes et nettoyage automatique
            lines = [sanitize_number(" ".join(l.split())) for l in manual_text.split('\n') if l.strip()]
            
            st.subheader("Validation des numéros")
            validated_page = []  # pour stocker la validation de cette page
            for idx, num in enumerate(lines):
                cols = st.columns([5,3])
                with cols[0]:
                    highlighted = highlight_confusions(num)
                    st.markdown(f"**Segment {idx+1} :** {highlighted}", unsafe_allow_html=True)
                with cols[1]:
                    # Affichage de l'indice de confiance sous forme de pourcentage
                    if idx < len(confidence_list):
                        conf = confidence_list[idx]
                        conf_pct = conf * 100
                        if conf_pct < 99:
                            st.markdown(f"<span class='confidence-low'>Confiance: {conf_pct:.0f}%</span>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<span class='confidence-high'>Confiance: {conf_pct:.0f}%</span>", unsafe_allow_html=True)
                    else:
                        st.write("Confiance N/A")
                    
                    # Mécanisme de double tap pour les segments avec faible confiance
                    key_btn = f"double_{i}_{idx}"
                    if key_btn not in st.session_state.double_tap_counts:
                        st.session_state.double_tap_counts[key_btn] = 0
                    if confidence_list and idx < len(confidence_list) and confidence_list[idx] * 100 < 99:
                        if st.button("Double Tap pour valider", key=key_btn):
                            st.session_state.double_tap_counts[key_btn] += 1
                        st.write(f"Double Tap Count: {st.session_state.double_tap_counts[key_btn]}")
                        if st.session_state.double_tap_counts[key_btn] >= 2:
                            validated = True
                        else:
                            validated = False
                    else:
                        # Pour les segments avec confiance >= 99, validation automatique
                        validated = True
                if validated:
                    st.markdown(f'<div class="validated">Confirmé : {num}</div>', unsafe_allow_html=True)
                    validated_page.append(num)
                else:
                    st.markdown(f'<div class="non-validated">Non validé : {num}</div>', unsafe_allow_html=True)
            # Bouton de confirmation de la page
            if st.button(f"Confirmer cette page", key=f"page_confirm_{i}"):
                if len(validated_page) == len(lines):
                    st.success(f"Tous les segments de la page {i+1} sont validés.")
                    barcode_cols = st.columns(3)
                    for idx, number in enumerate(validated_page):
                        barcode_buffer = generate_barcode_pybarcode(number)
                        barcode_cols[idx % 3].image(barcode_buffer, caption=f"{number}", use_container_width=True)
                    all_validated_serials.extend(validated_page)
                else:
                    st.error("Veuillez valider TOUS les segments de cette page.")
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    if all_validated_serials and st.button("Générer PDF de tous les codes‑barres"):
        st.write("Génération du PDF en cours...")
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            st.write("Dossier temporaire utilisé :", temp_dir)
            for vsn in all_validated_serials:
                st.write("Traitement du numéro :", vsn)
                barcode_buffer = generate_barcode_pybarcode(vsn)
                file_name = f"barcode_{vsn}.png"
                image_path = os.path.join(temp_dir, file_name)
                with open(image_path, "wb") as f:
                    f.write(barcode_buffer.getvalue())
                st.write("Image sauvegardée :", image_path)
                pdf.add_page()
                pdf.image(image_path, x=10, y=10, w=pdf.w - 20)
                st.write("Ajouté au PDF :", vsn)
            pdf_path = os.path.join(temp_dir, "barcodes.pdf")
            pdf.output(pdf_path, "F")
            st.write("PDF généré à :", pdf_path)
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            st.download_button("Télécharger le PDF des codes‑barres", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
        except Exception as e:
            st.error("Erreur lors de la génération du PDF : " + str(e))
    
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")



