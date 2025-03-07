import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3
import threading
import time

st.set_page_config(page_title="Daher – Multi Codes-barres", page_icon="✈️", layout="wide")

st.title("Daher Aerospace – OCR : Un code‑barres par numéro")
st.write("Sélectionnez la zone sur l'image, laissez l'OCR extraire le texte, puis séparez manuellement chaque numéro (un par ligne).")

# Base SQLite
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

# Charger EasyOCR
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# Génération de code-barres
@st.cache_data(show_spinner=False)
def generate_barcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

uploaded_file = st.file_uploader("Téléchargez une image", type=["png", "jpg", "jpeg"])
if uploaded_file:
    start_time = time.time()
    image = Image.open(uploaded_file)
    st.image(image, caption="Image originale", use_column_width=True)
    
    st.write("Sélectionnez la zone contenant les numéros (dessinez une boîte avec la souris).")
    cropped_img = st_cropper(image, realtime_update=True, box_color="#0d1b2a", aspect_ratio=None)
    st.image(cropped_img, caption="Zone sélectionnée", use_column_width=True)
    
    # Convertir l'image recadrée en bytes
    buf = io.BytesIO()
    cropped_img.save(buf, format="PNG")
    cropped_bytes = buf.getvalue()
    
    # Extraction OCR
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(cropped_bytes)
    extracted_text = " ".join([res[1] for res in ocr_results])
    
    st.markdown("**Texte extrait :**")
    st.write(extracted_text)
    
    # Séparation manuelle
    st.subheader("Séparez chaque numéro sur une nouvelle ligne :")
    manual_text = st.text_area("Un numéro par ligne :", value=extracted_text, height=150)
    
    # Génération de plusieurs codes-barres
    if st.button("Générer plusieurs codes‑barres"):
        lines = [l.strip() for l in manual_text.split('\n') if l.strip()]
        if lines:
            st.write("Codes‑barres individuels :")
            for line in lines:
                barcode_buffer = generate_barcode(line)
                st.image(barcode_buffer, caption=f"Code‑barres : {line}", use_container_width=True)
        else:
            st.warning("Aucun numéro trouvé.")
    
    # Enregistrement du feedback
    if st.button("Valider et Enregistrer le Feedback"):
        with st.spinner("Enregistrement du feedback..."):
            image_bytes = uploaded_file.getvalue()
            def save_feedback():
                c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                          (image_bytes, extracted_text, manual_text))
                conn.commit()
            threading.Thread(target=save_feedback).start()
            st.success("Feedback enregistré !")
    
    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")

