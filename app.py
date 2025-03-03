import streamlit as st
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
# Configuration de la page et CSS ultra moderne inspiré de Daher Aerospace & Fiverr
# -----------------------------------------------------------
st.set_page_config(page_title="Daher Aerospace – Annotation OCR", page_icon="✈️", layout="wide")
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
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(8px);
        border-radius: 20px;
        padding: 2rem 3rem;
        box-shadow: 0 12px 30px rgba(0,0,0,0.25);
        margin: 2rem auto;
        max-width: 1400px;
    }
    h1 { font-size: 3rem; color: #0d1b2a; }
    h2 { font-size: 2rem; color: #0d1b2a; }
    .stButton button {
        background-color: #0d1b2a;
        color: #ffffff;
        border: none;
        border-radius: 30px;
        padding: 14px 40px;
        font-size: 18px;
        font-weight: 600;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        transition: background-color 0.3s ease, transform 0.2s ease;
    }
    .stButton button:hover {
        background-color: #415a77;
        transform: translateY(-4px);
    }
    .stTextInput input {
        border-radius: 12px;
        padding: 14px;
        font-size: 16px;
        border: 2px solid #ccc;
        transition: border-color 0.3s ease;
    }
    .stTextInput input:focus { border-color: #0d1b2a; }
    .stRadio label {
        font-size: 16px;
        font-weight: 600;
        margin-right: 10px;
        color: #0d1b2a;
    }
    .stImage > div {
        border: 2px solid #eee;
        padding: 10px;
        border-radius: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – Extraction & Validation des Champs")
st.write("Téléchargez une image de bordereau, recadrez la zone d'intérêt contenant le numéro de série ou de pièce, puis laissez l'OCR extraire le texte. Corrigez et validez le résultat pour améliorer l'apprentissage automatique ultérieur.")

# -----------------------------------------------------------
# Connexion à la base de données SQLite
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
# Fonction de recadrage manuel
# -----------------------------------------------------------
def manual_crop(image):
    st.write("Utilisez les sliders pour sélectionner la zone d'intérêt de l'image.")
    width, height = image.size
    left = st.slider("Position gauche", 0, width, 0)
    top = st.slider("Position haut", 0, height, 0)
    right = st.slider("Position droite", 0, width, width)
    bottom = st.slider("Position bas", 0, height, height)
    if right > left and bottom > top:
        cropped_image = image.crop((left, top, right, bottom))
        st.image(cropped_image, caption="Zone sélectionnée", use_column_width=True)
        # Convertir l'image recadrée en bytes pour l'OCR
        buf = io.BytesIO()
        cropped_image.save(buf, format="PNG")
        return cropped_image, buf.getvalue()
    else:
        st.error("Les valeurs sélectionnées ne permettent pas un recadrage valide.")
        return None, None

# -----------------------------------------------------------
# Téléversement de l'image
# -----------------------------------------------------------
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    start_time = time.time()
    image = Image.open(uploaded_file)
    st.image(image, caption="Image originale", use_column_width=True)
    
    # -----------------------------------------------------------
    # Recadrage manuel via la fonction manual_crop()
    # -----------------------------------------------------------
    cropped_image, cropped_bytes = manual_crop(image)
    
    if cropped_bytes:
        # -----------------------------------------------------------
        # Extraction OCR sur la zone recadrée
        # -----------------------------------------------------------
        with st.spinner("Extraction du texte via OCR..."):
            ocr_results = ocr_reader.readtext(cropped_bytes)
        extracted_text = " ".join([result[1] for result in ocr_results])
        st.markdown("**Texte extrait :**")
        st.write(extracted_text)
        
        # -----------------------------------------------------------
        # Interface de validation du texte extrait
        # -----------------------------------------------------------
        st.subheader("Validation du texte extrait")
        user_text = st.text_area("Corrigez le texte si nécessaire", value=extracted_text, height=150)
        
        # Génération du code‑barres pour le texte validé
        try:
            barcode_buffer = generate_barcode(user_text)
            st.image(barcode_buffer, caption="Code‑barres pour le texte validé", use_container_width=True)
        except Exception as e:
            st.error(f"Erreur lors de la génération du code‑barres : {str(e)}")
        
        # Bouton pour valider et enregistrer le feedback
        if st.button("Valider et Enregistrer le Feedback"):
            with st.spinner("Enregistrement du feedback..."):
                image_bytes = uploaded_file.getvalue()
                full_ocr_text = extracted_text
                validated_text = user_text
                def save_feedback():
                    c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                              (image_bytes, full_ocr_text, validated_text))
                    conn.commit()
                threading.Thread(target=save_feedback).start()
                st.success("Feedback enregistré avec succès !")
    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")


