import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import re
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

# --- Fonction pour corriger l'orientation d'une image via EXIF ---
def correct_image_orientation(image):
    try:
        exif = image._getexif()
        if exif:
            for tag, value in exif.items():
                decoded = ExifTags.TAGS.get(tag, tag)
                if decoded == "Orientation":
                    if value == 3:
                        image = image.rotate(180, expand=True)
                    elif value == 6:
                        image = image.rotate(270, expand=True)
                    elif value == 8:
                        image = image.rotate(90, expand=True)
                    break
    except Exception as e:
        st.warning(f"Erreur d'orientation : {e}")
    return image

# --- Configuration de la page ---
st.set_page_config(page_title="Daher – Multi Page OCR & Code‑barres", page_icon="✈️", layout="wide")
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
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – Multi Page OCR & Code‑barres")
st.write("Téléversez toutes les pages de votre bordereau. Pour chaque page, sélectionnez la zone d'intérêt avec la souris (le cadre sera affiché en rouge pour être bien visible), vérifiez le texte extrait, et séparez les numéros de série (un par ligne). Vous pouvez ensuite générer un code‑barres pour chaque numéro et, si besoin, créer un PDF pour les imprimer ou les envoyer.")

# --- Connexion à la base SQLite (pour feedback) ---
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

# --- Fonction pour générer un code‑barres (Code128) ---
@st.cache_data(show_spinner=False)
def generate_barcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Téléversement multiple de pages ---
uploaded_files = st.file_uploader("Téléchargez les pages de votre BL (png, jpg, jpeg)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files:
    overall_start = time.time()
    all_validated_serials = []  # Liste globale pour conserver les numéros validés de toutes les pages
    st.write("### Traitement des pages")
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}"):
            page_start = time.time()
            # Ouvrir l'image et corriger son orientation
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            # Réduire la résolution pour éviter les plantages (par ex. 1500x1500 max)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            # Sélection interactive de la zone avec st_cropper, avec cadre rouge
            st.write("Sélectionnez la zone contenant les numéros (le cadre de sélection sera en rouge) :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            # Convertir l'image recadrée en bytes pour l'OCR
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            # Extraction OCR
            with st.spinner("Extraction OCR en cours..."):
                ocr_results = ocr_reader.readtext(cropped_bytes)
            extracted_text = " ".join([res[1] for res in ocr_results])
            st.markdown("**Texte extrait :**")
            st.write(extracted_text)
            
            # Séparation manuelle des numéros (un numéro par ligne)
            st.subheader("Séparez les numéros de série (un par ligne)")
            manual_text = st.text_area("Réorganisez le texte pour que chaque numéro soit sur une ligne :", value=extracted_text, height=150, key=f"manual_{i}")
            lines = [l.strip() for l in manual_text.split('\n') if l.strip()]
            
            # Génération des codes‑barres pour cette page
            if st.button(f"Générer les codes‑barres de la page {i+1}", key=f"gen_{i}"):
                if lines:
                    st.write("Codes‑barres générés pour cette page :")
                    cols = st.columns(3)
                    idx = 0
                    for line in lines:
                        barcode_buffer = generate_barcode(line)
                        cols[idx].image(barcode_buffer, caption=f"{line}", use_container_width=True)
                        idx = (idx + 1) % 3
                    all_validated_serials.extend(lines)
                else:
                    st.warning("Aucun numéro séparé sur cette page.")
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    # Option : Génération d'un PDF rassemblant tous les codes‑barres validés
    if all_validated_serials and st.button("Générer PDF de tous les codes‑barres"):
        pdf = FPDF()
        pdf.set_auto_page_break(0, margin=10)
        temp_dir = tempfile.gettempdir()
        for vsn in all_validated_serials:
            barcode_buffer = generate_barcode(vsn)
            file_name = f"barcode_{vsn.replace(' ', '_')}.png"
            image_path = os.path.join(temp_dir, file_name)
            with open(image_path, "wb") as f:
                f.write(barcode_buffer.getvalue())
            pdf.add_page()
            pdf.image(image_path, x=10, y=10, w=pdf.w - 20)
        pdf_path = os.path.join(temp_dir, "barcodes.pdf")
        pdf.output(pdf_path, "F")
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        st.download_button("Télécharger le PDF des codes‑barres", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
    
    # Enregistrement global du feedback dans la base SQLite
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


