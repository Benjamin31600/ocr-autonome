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
CONFIDENCE_THRESHOLD = 0.99  # 99% de confiance

# --- Fonction pour nettoyer un numéro (supprime caractères spéciaux, "S/N:" etc.) ---
def sanitize_number(num):
    # Supprime "S/N:" (insensible à la casse, avec ou sans espaces et ponctuation)
    sanitized = re.sub(r'(?i)S\s*/\s*N\s*[:,\-]?', '', num)
    # Conserve uniquement les lettres et chiffres (supprime espaces et autres ponctuations)
    sanitized = re.sub(r'[^0-9A-Za-z]', '', sanitized)
    return sanitized

# --- Dictionnaire de substitutions classiques (pour surligner, optionnel) ---
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
st.write("Téléversez les pages de votre bordereau. Pour chaque page, sélectionnez la zone d'intérêt (cadre rouge), vérifiez et corrigez le texte extrait, séparez les segments (un par ligne) et validez-les. L'indice de confiance (issu d'EasyOCR) est affiché en pourcentage et sous forme de barre de progression. Pour les segments avec une confiance inférieure à 99%, le champ de saisie sera laissé vide pour forcer une saisie manuelle. Seuls les segments validés seront nettoyés automatiquement avant de générer des codes‑barres et assembler un PDF téléchargeable.")

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

if uploaded_files:
    st.write("### Traitement des pages")
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            # Charger, corriger l'orientation et redimensionner l'image
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
            
            st.subheader("Séparez et nettoyez les segments (un par ligne)")
            manual_text = st.text_area("Chaque ligne doit contenir un segment :", value=extracted_text, height=150, key=f"manual_{i}")
            # Séparer en lignes et nettoyer chaque segment
            lines = [sanitize_number(" ".join(l.split())) for l in manual_text.split('\n') if l.strip()]
            
            st.subheader("Validation des segments")
            validated_page = []  # Liste des segments validés pour cette page
            for idx, num in enumerate(lines):
                st.markdown(f"**Segment {idx+1} :** {highlight_confusions(num)}", unsafe_allow_html=True)
                if idx < len(confidence_list):
                    conf = confidence_list[idx]
                    conf_pct = conf * 100
                    st.progress(int(conf_pct))
                    st.markdown(f"Confiance : {conf_pct:.0f}%", unsafe_allow_html=True)
                    if conf_pct < 99:
                        st.error("Ce segment a une faible confiance (< 99%). Veuillez retaper le segment pour validation.")
                        # Pour forcer l'intervention, on ne pré-remplit pas le champ.
                        user_input = st.text_input("Retapez le segment corrigé :", value="", key=f"input_{i}_{idx}")
                        if user_input.strip() == "":
                            validated = False
                        else:
                            # Même si l'opérateur retape exactement le même résultat, il doit effectuer une action.
                            if sanitize_number(user_input) == num:
                                st.error("Le segment doit être modifié par rapport au résultat OCR.")
                                validated = False
                            else:
                                validated = True
                                final_val = sanitize_number(user_input)
                    else:
                        st.markdown(f"<span class='confidence-high'>Segment avec haute confiance</span>", unsafe_allow_html=True)
                        # Pour segments avec confiance >= 99, le champ est pré-rempli et peut être validé ou modifié.
                        user_input = st.text_input("Confirmez ou modifiez le segment", value=num, key=f"input_{i}_{idx}")
                        if user_input.strip() == "":
                            st.error("Le champ ne peut pas être vide.")
                            validated = False
                        else:
                            validated = True
                            final_val = sanitize_number(user_input)
                else:
                    st.write("Confiance N/A")
                    validated = True
                    final_val = num
                if validated:
                    st.markdown(f'<div class="validated">Confirmé : {final_val}</div>', unsafe_allow_html=True)
                    validated_page.append(final_val)
                else:
                    st.markdown(f'<div class="non-validated">Non validé : {num}</div>', unsafe_allow_html=True)
            if st.button(f"Confirmer cette page", key=f"page_confirm_{i}"):
                if len(validated_page) == len(lines) and validated_page:
                    st.success(f"Tous les segments de la page {i+1} sont validés.")
                    barcode_cols = st.columns(3)
                    for idx, segment in enumerate(validated_page):
                        barcode_buffer = generate_barcode_pybarcode(segment)
                        barcode_cols[idx % 3].image(barcode_buffer, caption=f"{segment}", use_container_width=True)
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
            for segment in all_validated_serials:
                st.write("Traitement du segment :", segment)
                barcode_buffer = generate_barcode_pybarcode(segment)
                file_name = f"barcode_{segment}.png"
                image_path = os.path.join(temp_dir, file_name)
                with open(image_path, "wb") as f:
                    f.write(barcode_buffer.getvalue())
                st.write("Image sauvegardée :", image_path)
                pdf.add_page()
                pdf.image(image_path, x=10, y=10, w=pdf.w - 20)
                st.write("Ajouté au PDF :", segment)
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

