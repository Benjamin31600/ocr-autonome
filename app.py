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

# -----------------------------------------------------------
# Configuration Streamlit
# -----------------------------------------------------------
st.set_page_config(page_title="Daher – OCR Multi Code-barres (Ultra Simple)", page_icon="✈️", layout="wide")

st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        font-family: sans-serif;
        color: #ffffff;
        margin: 0; padding: 0;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255,255,255,0.9);
        backdrop-filter: blur(8px);
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1200px;
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
        background-color: #415a77; transform: translateY(-3px);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR : Multi Code-Barres (Ultra Simple)")
st.write("1) Sélectionnez la zone à la souris, 2) OCR automatique, 3) Séparez vos numéros de série (un par ligne), 4) Générez tous les codes‑barres et enregistrez.")

# -----------------------------------------------------------
# Base SQLite
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
# Génération de code-barres
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
    image = Image.open(uploaded_file)
    st.image(image, caption="Image originale", use_column_width=True)

    # 1) Sélection de la zone
    st.write("Sélectionnez la zone contenant les numéros de série (dessinez une boîte avec la souris) :")
    cropped_img = st_cropper(image, realtime_update=True, box_color="#0d1b2a", aspect_ratio=None)
    st.image(cropped_img, caption="Zone sélectionnée", use_column_width=True)

    # Convertir la zone recadrée en bytes
    buf = io.BytesIO()
    cropped_img.save(buf, format="PNG")
    cropped_bytes = buf.getvalue()

    # 2) Extraction OCR
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(cropped_bytes)
    extracted_text = " ".join([res[1] for res in ocr_results])

    st.markdown("**Texte extrait :**")
    st.write(extracted_text)

    # 3) Séparation manuelle
    st.subheader("Séparez vos numéros de série : un par ligne")
    manual_text = st.text_area("Un numéro par ligne :", value=extracted_text, height=150)

    # 4) Génération de tous les codes-barres
    if st.button("Générer les codes-barres"):
        lines = [l.strip() for l in manual_text.split('\n') if l.strip()]
        if lines:
            st.write("Codes‑barres générés :")
            # On affiche 3 codes-barres par ligne, par exemple
            cols = st.columns(3)
            idx = 0
            for line in lines:
                barcode_buffer = generate_barcode(line)
                cols[idx].image(barcode_buffer, caption=f"{line}", use_column_width=True)
                idx = (idx + 1) % 3
        else:
            st.warning("Aucun numéro trouvé.")

    # Bouton pour enregistrer le feedback
    if st.button("Valider et Enregistrer le Feedback"):
        with st.spinner("Enregistrement du feedback..."):
            image_bytes = uploaded_file.getvalue()
            def save_feedback():
                c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                          (image_bytes, extracted_text, manual_text))
                conn.commit()
            threading.Thread(target=save_feedback).start()
            st.success("Feedback enregistré avec succès !")

    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")


