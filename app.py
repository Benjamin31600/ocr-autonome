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

# -----------------------------------------------------------
# Fonction pour corriger l'orientation de l'image via EXIF
# -----------------------------------------------------------
def correct_image_orientation(image):
    try:
        exif = image._getexif()
        if exif is not None:
            for tag, value in exif.items():
                decoded = ExifTags.TAGS.get(tag, tag)
                if decoded == "Orientation":
                    orientation = value
                    if orientation == 3:
                        image = image.rotate(180, expand=True)
                    elif orientation == 6:
                        image = image.rotate(270, expand=True)
                    elif orientation == 8:
                        image = image.rotate(90, expand=True)
                    break
    except Exception as e:
        st.warning(f"Erreur d'orientation : {e}")
    return image

# -----------------------------------------------------------
# Configuration de la page et Style
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

st.title("Daher Aerospace – OCR Multi Code‑barres")
st.write("Téléchargez une image, sélectionnez la zone avec la souris, et laissez l'OCR extraire le texte. Corrigez les numéros de série en les séparant par ligne pour générer un code‑barres par numéro.")

# -----------------------------------------------------------
# Connexion à la base SQLite
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
# Génération de code‑barres
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
    
    # Ouvrir et corriger l'orientation de l'image
    image = Image.open(uploaded_file)
    image = correct_image_orientation(image)
    
    # Réduire la résolution pour éviter des plantages
    image.thumbnail((1500, 1500))
    st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
    
    # Sélection de la zone via st_cropper
    st.write("Sélectionnez la zone contenant les numéros (dessinez une boîte avec la souris) :")
    cropped_img = st_cropper(image, realtime_update=True, box_color="#0d1b2a", aspect_ratio=None)
    st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
    
    # Convertir la zone recadrée en bytes
    buf = io.BytesIO()
    cropped_img.save(buf, format="PNG")
    cropped_bytes = buf.getvalue()
    
    # Extraction OCR
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(cropped_bytes)
    extracted_text = " ".join([res[1] for res in ocr_results])
    st.markdown("**Texte extrait :**")
    st.write(extracted_text)
    
    # Séparation manuelle des numéros (chacun sur une ligne)
    st.subheader("Séparez vos numéros de série (un par ligne)")
    manual_text = st.text_area("Entrez chaque numéro sur une nouvelle ligne :", value=extracted_text, height=150)
    lines = [l.strip() for l in manual_text.split('\n') if l.strip()]
    
    # Génération de codes‑barres multiples
    if st.button("Générer les codes‑barres"):
        if lines:
            st.write("Codes‑barres générés :")
            cols = st.columns(3)
            idx = 0
            for line in lines:
                barcode_buffer = generate_barcode(line)
                cols[idx].image(barcode_buffer, caption=f"{line}", use_container_width=True)
                idx = (idx + 1) % 3
        else:
            st.warning("Aucun numéro trouvé.")
    
    # Enregistrement du feedback
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

