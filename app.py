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
        background: rgba(255, 255, 255, 0.92);
        backdrop-filter: blur(8px);
        border-radius: 20px;
        padding: 2rem 3rem;
        box-shadow: 0 12px 30px rgba(0,0,0,0.25);
        margin: 2rem auto;
        max-width: 1400px;
    }
    h1 {
        font-size: 3rem;
        color: #0d1b2a;
    }
    h2 {
        font-size: 2rem;
        color: #0d1b2a;
    }
    .stButton button {
        background-color: #0d1b2a;
        color: #ffffff;
        border: none;
        border-radius: 30px;
        padding: 14px 40px;
        font-size: 18px;
        font-weight: 600;
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
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
    .stTextInput input:focus {
        border-color: #0d1b2a;
    }
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

st.title("Daher Aerospace – Annotation OCR & Validation")
st.write("Téléchargez une image de bordereau, sélectionnez directement la zone d'intérêt avec la souris, puis laissez l'OCR extraire le texte. Une détection automatique repère plusieurs numéros de série, que vous pouvez corriger/valider manuellement. Chaque numéro validé génère un code‑barres distinct.")

# -----------------------------------------------------------
# Base SQLite pour le feedback
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
# Fonction pour générer un code‑barres
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
    
    # Affichage de l'image originale
    image = Image.open(uploaded_file)
    st.image(image, caption="Image originale", use_column_width=True)
    
    # Sélection interactive de la zone
    st.write("Sélectionnez la zone contenant les numéros de série ou de pièce (dessinez une boîte avec votre souris) :")
    cropped_img = st_cropper(image, realtime_update=True, box_color="#0d1b2a", aspect_ratio=None)
    st.image(cropped_img, caption="Zone sélectionnée", use_column_width=True)
    
    # Convertir l'image recadrée en bytes pour l'OCR
    buf = io.BytesIO()
    cropped_img.save(buf, format="PNG")
    cropped_bytes = buf.getvalue()
    
    # Extraction OCR sur la zone recadrée
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(cropped_bytes)
    # Concaténer tout le texte détecté
    extracted_text = " ".join([result[1] for result in ocr_results])
    st.markdown("**Texte extrait :**")
    st.write(extracted_text)
    
    # Détection automatique des numéros de série via une regex (exemple)
    # Ajustez le pattern en fonction de votre format (SER CHT \d+ ou autre)
    pattern = r"(SER\s+CHT\s+\d+)"
    auto_detected = re.findall(pattern, extracted_text)
    
    st.subheader("Détection automatique des numéros de série")
    if auto_detected:
        st.write(f"Numéros détectés automatiquement : {auto_detected}")
    else:
        st.write("Aucun numéro détecté automatiquement via le pattern. Vous pouvez toujours corriger manuellement ci-dessous.")
    
    # L'utilisateur peut corriger le texte complet pour y séparer lui-même les numéros
    st.subheader("Texte corrigé / séparé manuellement (optionnel)")
    user_text = st.text_area("Corrigez ou séparez les numéros de série (un par ligne, par exemple)", value=extracted_text, height=150)
    
    # On propose de combiner la détection auto + la saisie manuelle
    # 1. Les numéros auto détectés
    # 2. Les lignes saisies manuellement
    # L'utilisateur valide ou rejette chaque numéro
    st.write("---")
    st.write("### Validation finale des numéros")
    
    # Combiner les deux sources (détection auto + split manuel)
    manual_lines = [l.strip() for l in user_text.split('\n') if l.strip()]
    combined = list(set(auto_detected + manual_lines))  # set() pour éviter doublons
    
    validated_serials = []
    for sn in combined:
        st.write(f"**Numéro détecté :** {sn}")
        # Champ de texte pour corriger ce numéro
        corrected_sn = st.text_input(f"Correction pour {sn}", value=sn, key=sn)
        # Bouton radio pour valider ou rejeter
        status = st.radio(f"Statut pour {sn}", ["Valider", "Rejeter"], key=f"radio_{sn}")
        if status == "Valider":
            validated_serials.append(corrected_sn)
    
    # Affichage des codes-barres pour chaque numéro validé
    if st.button("Générer codes‑barres pour les numéros validés"):
        st.write("Codes‑barres individuels :")
        for vsn in validated_serials:
            barcode_buffer = generate_barcode(vsn)
            st.image(barcode_buffer, caption=f"Code‑barres pour {vsn}", use_column_width=True)
    
    # Enregistrement final du feedback
    if st.button("Enregistrer le feedback dans la base"):
        with st.spinner("Enregistrement du feedback..."):
            image_bytes = uploaded_file.getvalue()
            def save_feedback():
                c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                          (image_bytes, extracted_text, " | ".join(validated_serials)))
                conn.commit()
            threading.Thread(target=save_feedback).start()
            st.success("Feedback enregistré avec succès !")
    
    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")


