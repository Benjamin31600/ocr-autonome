import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3
import threading
import time

# -----------------------------------------------------------
# Configuration de la page et Style Ultra Moderne
# -----------------------------------------------------------
st.set_page_config(page_title="Daher – Multi Code-barres (Industriel)", page_icon="✈️", layout="wide")

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
    h1 {
        color: #0d1b2a;
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
    .stTextInput input {
        border-radius: 8px;
        padding: 10px;
        font-size: 14px;
        border: 1px solid #ccc;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR Multi Code‑barres")
st.write("1) Téléversez une image. 2) Sélectionnez la zone avec la souris. 3) Laissez l'OCR extraire le texte. 4) Séparez manuellement les numéros (un par ligne). 5) Génèrez et enregistrez les codes‑barres.")

# -----------------------------------------------------------
# Base SQLite pour feedback
# -----------------------------------------------------------
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

# -----------------------------------------------------------
# Charger EasyOCR
# -----------------------------------------------------------
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# -----------------------------------------------------------
# Fonction pour générer un code‑barres (Code128)
# -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def generate_barcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# -----------------------------------------------------------
# Téléversement de l'image
# -----------------------------------------------------------
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    start_time = time.time()
    
    # Ouvrir l'image
    image = Image.open(uploaded_file)
    
    # Réduction de la résolution pour éviter les plantages (par exemple, max 2000x2000)
    image.thumbnail((2000, 2000))
    st.image(image, caption="Image originale (redimensionnée)", use_column_width=True)
    
    # -----------------------------------------------------------
    # Sélection interactive de la zone avec st_cropper
    # -----------------------------------------------------------
    st.write("Sélectionnez la zone contenant les numéros (dessinez une boîte avec la souris) :")
    cropped_img = st_cropper(image, realtime_update=True, box_color="#0d1b2a", aspect_ratio=None)
    st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
    
    # Convertir l'image recadrée en bytes pour l'OCR
    buf = io.BytesIO()
    cropped_img.save(buf, format="PNG")
    cropped_bytes = buf.getvalue()
    
    # -----------------------------------------------------------
    # Extraction OCR sur la zone recadrée
    # -----------------------------------------------------------
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(cropped_bytes)
    extracted_text = " ".join([res[1] for res in ocr_results])
    st.markdown("**Texte extrait :**")
    st.write(extracted_text)
    
    # -----------------------------------------------------------
    # Séparation manuelle : l'opérateur doit placer un numéro par ligne
    # -----------------------------------------------------------
    st.subheader("Séparez les numéros (un par ligne)")
    manual_text = st.text_area("Un numéro par ligne :", value=extracted_text, height=150)
    
    # Ici, nous faisons un split par retour à la ligne
    lines = [l.strip() for l in manual_text.split('\n') if l.strip()]
    
    # -----------------------------------------------------------
    # Génération des codes‑barres multiples
    # -----------------------------------------------------------
    if st.button("Générer les codes‑barres"):
        if lines:
            st.write("Codes‑barres générés :")
            cols = st.columns(3)
            idx = 0
            for line in lines:
                barcode_buffer = generate_barcode(line)
                cols[idx].image(barcode_buffer, caption=f"{line}", use_column_width=True)
                idx = (idx + 1) % 3
        else:
            st.warning("Aucun numéro détecté ou séparé.")
    
    # -----------------------------------------------------------
    # Enregistrement du feedback
    # -----------------------------------------------------------
    if st.button("Valider et Enregistrer le Feedback"):
        with st.spinner("Enregistrement du feedback..."):
            image_bytes = uploaded_file.getvalue()
            def save_feedback():
                c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                          (image_bytes, extracted_text, " | ".join(lines)))
                conn.commit()
            threading.Thread(target=save_feedback).start()
            st.success("Feedback enregistré avec succès !")
    
    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")

