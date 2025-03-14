import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ExifTags
import io
import sqlite3
import threading
import time
import os
import tempfile
from fpdf import FPDF

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
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Configuration de la page et styles modernes ---
st.set_page_config(page_title="Daher – OCR & Code‑barres Sécurisé", page_icon="✈️", layout="wide")
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
    .validation-box {
        padding: 8px;
        margin: 4px 0;
        border: 2px solid #00FF00;
        border-radius: 8px;
        background-color: rgba(0,255,0,0.1);
        font-size: 16px;
        font-weight: 600;
        color: #000;
        text-align: center;
    }
    .non-validation-box {
        padding: 8px;
        margin: 4px 0;
        border: 2px solid #FF0000;
        border-radius: 8px;
        background-color: rgba(255,0,0,0.1);
        font-size: 16px;
        font-weight: 600;
        color: #000;
        text-align: center;
    }
    .low-confidence {
        background-color: rgba(255, 200, 200, 0.6);
        border: 2px solid #FF0000;
        padding: 4px;
        border-radius: 4px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Sécurisé")
st.write("Téléversez les pages de votre BL. Pour chaque page, sélectionnez la zone (cadre rouge), vérifiez le texte extrait et séparez les numéros (un par ligne). Vérifiez bien les numéros signalés à faible confiance (affichés en rouge) avant de confirmer en saisissant 'OK' dans le champ dédié. Seuls les numéros confirmés seront utilisés pour générer les codes‑barres et le PDF.")

# --- Connexion à la base SQLite ---
conn = sqlite3.connect("feedback.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image BLOB,
    ocr_text TEXT,
    validated_fields TEXT
)
""")
conn.commit()

# --- Charger EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement multiple de pages ---
uploaded_files = st.file_uploader("Téléchargez les pages de votre BL (png, jpg, jpeg)", 
                                    type=["png", "jpg", "jpeg"], 
                                    accept_multiple_files=True)

# Seuil de confiance pour alerter
confidence_threshold = 0.80

if uploaded_files:
    overall_start = time.time()
    all_validated_serials = []  # Liste globale pour stocker les numéros confirmés
    st.write("### Traitement des pages")
    
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone contenant les numéros (le cadre sera en rouge) :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR..."):
                ocr_results = ocr_reader.readtext(cropped_bytes)
            
            # Afficher les détails OCR avec confiance
            st.markdown("**Détails OCR (texte et score de confiance) :**")
            ocr_details = []
            for result in ocr_results:
                text = result[1]
                conf = result[2]
                ocr_details.append(text)
                if conf < confidence_threshold:
                    st.markdown(f"<span class='low-confidence'>Alerte : '{text}' (Confiance: {conf:.2f})</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:green;'>'{text}' (Confiance: {conf:.2f})</span>", unsafe_allow_html=True)
            # Pré-remplir le champ de séparation avec le texte extrait complet
            extracted_text = " ".join(ocr_details)
            st.markdown("**Texte extrait :**")
            st.write(extracted_text)
            
            st.subheader("Séparez les numéros (un par ligne)")
            manual_text = st.text_area("Un numéro par ligne :", value=extracted_text, height=150, key=f"manual_{i}")
            # Nettoyage : suppression des espaces en début/fin et réduction des espaces multiples
            lines = [" ".join(l.split()) for l in manual_text.split('\n') if l.strip()]
            
            st.subheader("Validation des numéros")
            confirmed_numbers = []
            with st.form(key=f"validation_form_{i}"):
                for idx, num in enumerate(lines):
                    col1, col2 = st.columns([4,2])
                    with col1:
                        current_num = st.text_input(f"Numéro {idx+1}", value=num, key=f"num_{i}_{idx}")
                    with col2:
                        # L'opérateur doit saisir "OK" pour confirmer
                        confirm = st.text_input(f"Confirmez ('OK')", value="", key=f"confirm_{i}_{idx}")
                    if confirm.strip().upper() == "OK":
                        st.markdown(f'<div class="validation-box">Confirmé : {current_num}</div>', unsafe_allow_html=True)
                        confirmed_numbers.append(current_num)
                    else:
                        st.markdown(f'<div class="non-validation-box">Non confirmé : {current_num}</div>', unsafe_allow_html=True)
                form_submitted = st.form_submit_button("Confirmer les numéros de cette page")
            
            if form_submitted:
                if len(confirmed_numbers) == len(lines) and confirmed_numbers:
                    st.success(f"Tous les numéros de la page {i+1} sont confirmés.")
                    st.write("Codes‑barres générés pour cette page :")
                    cols = st.columns(3)
                    idx = 0
                    for number in confirmed_numbers:
                        barcode_buffer = generate_barcode_pybarcode(number)
                        cols[idx].image(barcode_buffer, caption=f"{number}", use_container_width=True)
                        idx = (idx + 1) % 3
                    all_validated_serials.extend(confirmed_numbers)
                else:
                    st.error("Veuillez saisir 'OK' pour CONFIRMER TOUS les numéros de cette page.")
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    # --- Génération du PDF regroupant tous les codes‑barres validés ---
    if all_validated_serials and st.button("Générer PDF de tous les codes‑barres"):
        st.write("Début de la génération du PDF...")
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            st.write("Dossier temporaire utilisé :", temp_dir)
            for vsn in all_validated_serials:
                st.write("Traitement du numéro :", vsn)
                barcode_buffer = generate_barcode_pybarcode(vsn)
                file_name = f"barcode_{vsn.replace(' ', '_')}.png"
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
    
    # --- Enregistrement global du feedback ---
    if st.button("Valider et Enregistrer le Feedback global"):
        with st.spinner("Enregistrement du feedback..."):
            combined_text = ""
            for file in uploaded_files:
                combined_text += "\n---\n"
                img = Image.open(file)
                img = correct_image_orientation(img)
                img.thumbnail((1500, 1500))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                page_bytes = buf.getvalue()
                with st.spinner("Extraction OCR..."):
                    results = ocr_reader.readtext(page_bytes)
                combined_text += " ".join([res[1] for res in results])
            def save_feedback():
                c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                          (b"Multiple pages", combined_text, " | ".join(all_validated_serials)))
                conn.commit()
            threading.Thread(target=save_feedback).start()
            st.success("Feedback global enregistré avec succès !")
    
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")



