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
# CSS & Style : Ultra moderne avec effet glassmorphism
# -----------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;500;700&display=swap');
    body {
        background: linear-gradient(135deg, #0c234b, #1b3a6d);
        font-family: 'Poppins', sans-serif;
        color: #ffffff;
        margin: 0;
        padding: 0;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
        margin: 2rem auto;
        max-width: 1200px;
    }
    h1, h2, h3 {
        color: #0c234b;
        font-weight: 700;
    }
    .stButton button {
        background-color: #0c234b;
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
        background-color: #152d4a;
        transform: translateY(-4px);
    }
    .stTextInput input {
        border-radius: 12px;
        padding: 14px;
        font-size: 16px;
        border: 2px solid #e0e0e0;
        width: 100%;
        transition: border-color 0.2s ease;
    }
    .stTextInput input:focus {
        border-color: #0c234b;
    }
    .stRadio label {
        font-size: 16px;
        font-weight: 600;
        margin-right: 10px;
        color: #0c234b;
    }
    .stImage > div {
        border: 2px solid #f0f0f0;
        padding: 10px;
        border-radius: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – Extraction & Validation des Champs")
st.write("Téléchargez une image de bordereau. L'outil extrait les fragments de texte, identifie les libellés (ex. 'Part Number', 'Serial Number', 'Designation Class') et tente d'extraire la valeur associée (souvent le numéro de série). Corrigez, validez ou rejetez chaque extraction pour que le système puisse apprendre automatiquement.")

# -----------------------------------------------------------
# Connexion à la base SQLite pour le feedback
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
# Fonction pour regrouper les fragments par ligne
# -----------------------------------------------------------
def group_by_line(fields, threshold=15):
    sorted_fields = sorted(fields, key=lambda x: x["bbox"][0][1])
    groups = []
    current_group = []
    current_y = None
    for field in sorted_fields:
        y = field["bbox"][0][1]
        if current_y is None or abs(y - current_y) < threshold:
            current_group.append(field)
            current_y = y if current_y is None else (current_y + y) / 2
        else:
            groups.append(current_group)
            current_group = [field]
            current_y = y
    if current_group:
        groups.append(current_group)
    return groups

# -----------------------------------------------------------
# Téléversement de l'image
# -----------------------------------------------------------
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    start_time = time.time()
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau de réception", use_container_width=True)
    
    # Extraction OCR
    with st.spinner("Extraction du texte..."):
        ocr_results = ocr_reader.readtext(uploaded_file.getvalue())
    candidate_fields = []
    ocr_texts = []
    for result in ocr_results:
        bbox, text, conf = result
        candidate_fields.append({"bbox": bbox, "text": text})
        ocr_texts.append(text)
    
    groups = group_by_line(candidate_fields, threshold=15)
    
    # -----------------------------------------------------------
    # Extraction des paires "libellé / valeur" basée sur la position
    # -----------------------------------------------------------
    header_pattern = re.compile(r"(part\s*number|serial\s*(number|no)|n°\s*de\s*série|designation\s*class|serie)", re.IGNORECASE)
    extracted_fields = []
    for i, group in enumerate(groups):
        group_text = " ".join([field["text"] for field in group])
        if header_pattern.search(group_text):
            if ":" in group_text:
                parts = group_text.split(":")
                value = parts[1].strip()
                if value:
                    extracted_fields.append(value)
                    continue
            if i + 1 < len(groups):
                next_group_text = " ".join([field["text"] for field in groups[i+1]]).strip()
                if next_group_text:
                    extracted_fields.append(next_group_text)
    
    if not extracted_fields:
        for group in groups:
            group_text = " ".join([field["text"] for field in group]).strip()
            if re.search(r"\d", group_text):
                extracted_fields.append(group_text)
    
    # -----------------------------------------------------------
    # Affichage, validation et génération des codes‑barres
    # -----------------------------------------------------------
    if extracted_fields:
        st.subheader("Champs extraits et Codes‑barres associés")
        validated_fields = []
        for idx, field in enumerate(extracted_fields):
            col1, col2, col3 = st.columns([3,2,2])
            with col1:
                user_field = st.text_input(f"Champ {idx+1}", value=field, key=f"field_{idx}")
            with col2:
                try:
                    barcode_buffer = generate_barcode(user_field)
                    st.image(barcode_buffer, caption=f"Code‑barres pour {user_field}", use_container_width=True)
                except Exception as e:
                    st.error(f"Erreur pour {user_field} : {str(e)}")
            with col3:
                status = st.radio("Statut", options=["Valider", "Rejeter"], key=f"status_{idx}")
            if status == "Valider":
                validated_fields.append(user_field)
        if st.button("Enregistrer le feedback"):
            with st.spinner("Enregistrement du feedback..."):
                image_bytes = uploaded_file.getvalue()
                full_ocr_text = " ".join(ocr_texts)
                validated_text = " | ".join(validated_fields)
                def save_feedback():
                    c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                              (image_bytes, full_ocr_text, validated_text))
                    conn.commit()
                threading.Thread(target=save_feedback).start()
                st.success("Feedback enregistré !")
    else:
        st.warning("Aucun champ pertinent n'a été extrait.")
    
    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")

    
    end_time = time.time()
    st.write(f"Temps de traitement : {end_time - start_time:.2f} secondes")

