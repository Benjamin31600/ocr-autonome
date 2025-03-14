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

# --- Fonction pour générer un code‑barres avec python‑barcode (sans add_checksum) ---
def generate_barcode_pybarcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())  # Paramètre add_checksum supprimé
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

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

st.title("Daher Aerospace – OCR Multi Page & Code‑barres")
st.write("Téléversez les pages de votre bordereau. Pour chaque page, sélectionnez la zone d'intérêt (le cadre sera affiché en rouge), vérifiez le texte extrait, et séparez les numéros (un par ligne). Ensuite, générez un code‑barres pour chaque numéro et créez un PDF regroupant tous les codes‑barres.")

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

if uploaded_files:
    overall_start = time.time()
    all_validated_serials = []  # Liste globale pour stocker les numéros validés de toutes les pages
    st.write("### Traitement des pages")
    
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone contenant les numéros (le cadre sera affiché en rouge) :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR..."):
                ocr_results = ocr_reader.readtext(cropped_bytes)
            extracted_text = " ".join([res[1] for res in ocr_results])
            st.markdown("**Texte extrait :**")
            st.write(extracted_text)
            
            st.subheader("Séparez les numéros (un par ligne)")
            manual_text = st.text_area("Entrez chaque numéro sur une nouvelle ligne :", value=extracted_text, height=150, key=f"manual_{i}")
            # Nettoyage : suppression des espaces superflus en début et fin et réduction des espaces multiples internes
            lines = [" ".join(l.split()) for l in manual_text.split('\n') if l.strip()]
            
            if st.button(f"Générer les codes‑barres pour la page {i+1}", key=f"gen_{i}"):
                if lines:
                    st.write("Codes‑barres générés pour cette page :")
                    cols = st.columns(3)
                    idx = 0
                    for line in lines:
                        barcode_buffer = generate_barcode_pybarcode(line)
                        cols[idx].image(barcode_buffer, caption=f"{line}", use_container_width=True)
                        idx = (idx + 1) % 3
                    all_validated_serials.extend(lines)
                else:
                    st.warning("Aucun numéro séparé sur cette page.")
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
