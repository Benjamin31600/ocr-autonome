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
import unicodedata

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

# --- Fonction pour nettoyer et extraire les numéros de série ---
def clean_and_extract_serials(text):
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^A-Za-z0-9\s]', ' ', text)
    text = re.sub(r'\bSER\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    tokens = text.split()
    serials = [t for t in tokens if re.match(r'^[A-Z0-9]{6,}$', t)]
    return "\n".join(sorted(set(serials)))

# --- Fonction pour générer un code-barres (Code128) ---
def generate_barcode_pybarcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Configuration de la page ---
st.set_page_config(page_title="Daher – Multi Page OCR & Code-barres", page_icon="🚀", layout="wide")

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
    all_validated_serials = []
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
            cleaned_serials = clean_and_extract_serials(extracted_text)

            st.markdown("**Numéros de série extraits automatiquement :**")
            manual_text = st.text_area("Confirmez ou modifiez les numéros (1 par ligne) :", value=cleaned_serials, height=150, key=f"manual_{i}")
            lines = [line.strip() for line in manual_text.split('\n') if line.strip()]

            st.subheader("Validez les numéros")
            with st.form(key=f"form_page_{i}"):
                confirmed_lines = []
                for idx, line in enumerate(lines):
                    col1, col2 = st.columns([4,1])
                    with col1:
                        current_line = st.text_input(f"Numéro {idx+1}", value=line, key=f"num_{i}_{idx}")
                    with col2:
                        valid = st.checkbox("Confirmer", key=f"check_{i}_{idx}")
                    if valid:
                        confirmed_lines.append(current_line)
                submit_page = st.form_submit_button("Valider les numéros de cette page")

            if submit_page:
                if confirmed_lines:
                    st.success(f"Page {i+1} validée avec {len(confirmed_lines)} numéro(s) confirmé(s).")
                    st.write("Codes-barres générés pour cette page :")
                    cols = st.columns(3)
                    idx = 0
                    for number in confirmed_lines:
                        barcode_buffer = generate_barcode_pybarcode(number)
                        cols[idx].image(barcode_buffer, caption=f"{number}", use_container_width=True)
                        idx = (idx + 1) % 3
                    all_validated_serials.extend(confirmed_lines)
                else:
                    st.warning(f"Page {i+1} : Aucun numéro confirmé.")
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")

    if all_validated_serials and st.button("Générer PDF de tous les codes-barres"):
        st.write("Début de la génération du PDF...")
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            for vsn in all_validated_serials:
                barcode_buffer = generate_barcode_pybarcode(vsn)
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
            st.download_button("Télécharger le PDF des codes-barres", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
        except Exception as e:
            st.error("Erreur lors de la génération du PDF : " + str(e))

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


