import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# -----------------------------------------------------------
# CSS & Style : Interface moderne et marketing
# -----------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
    body {
        background: linear-gradient(135deg, #e0eafc, #cfdef3);
        font-family: 'Roboto', sans-serif;
    }
    [data-testid="stAppViewContainer"] {
        background: transparent;
    }
    h1, h2, h3 {
        color: #003366;
        font-weight: 700;
    }
    .stButton button {
        background-color: #003366;
        color: #fff;
        border: none;
        border-radius: 12px;
        padding: 12px 30px;
        font-size: 16px;
        box-shadow: 0px 4px 6px rgba(0,0,0,0.1);
        transition: background-color 0.3s ease;
    }
    .stButton button:hover {
        background-color: #002244;
    }
    .stTextInput input {
        border-radius: 8px;
        padding: 10px;
        font-size: 16px;
        border: 1px solid #ccc;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – Extraction & Validation des Champs")
st.write("Téléchargez une image de bordereau. Le système extrait des champs candidats (ex. Part Number, Serial Number). Vous pouvez modifier chaque champ et le valider (via une case à cocher). Seuls les champs validés seront enregistrés pour l'apprentissage.")

# -----------------------------------------------------------
# Base de données SQLite pour le feedback utilisateur
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
# Chargement du modèle OCR EasyOCR
# -----------------------------------------------------------
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# -----------------------------------------------------------
# Fonction pour générer un code‑barres pour un champ donné
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
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau de réception", use_container_width=True)
    
    # -----------------------------------------------------------
    # Extraction OCR avec EasyOCR
    # -----------------------------------------------------------
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(uploaded_file.getvalue())
    candidate_fields = []
    for result in ocr_results:
        bbox, text, conf = result
        candidate_fields.append({"bbox": bbox, "text": text})
    
    # -----------------------------------------------------------
    # Filtrage heuristique des fragments (basé sur des mots clés)
    # -----------------------------------------------------------
    accepted_pattern = re.compile(r"(part\s*number|serial\s*(number|no)|n°\s*de\s*série|serie)", re.IGNORECASE)
    rejected_pattern = re.compile(r"(delivery|fax|tel|contact|date|order|quantity|adress|carrier|shipping|customer)", re.IGNORECASE)
    candidate_fields_filtered = [cand["text"] for cand in candidate_fields
                                 if cand["text"].strip() and
                                 accepted_pattern.search(cand["text"]) and not rejected_pattern.search(cand["text"])]
    
    # -----------------------------------------------------------
    # Validation par l'utilisateur : Affichage des champs candidats
    # -----------------------------------------------------------
    if candidate_fields_filtered:
        st.subheader("Champs candidats détectés")
        validated_fields = []
        for idx, field in enumerate(candidate_fields_filtered):
            col1, col2, col3 = st.columns([2,2,1])
            with col1:
                user_field = st.text_input(f"Champ {idx+1}", value=field, key=f"field_{idx}")
            with col2:
                try:
                    barcode_buffer = generate_barcode(user_field)
                    st.image(barcode_buffer, caption=f"Code‑barres pour {user_field}", use_container_width=True)
                except Exception as e:
                    st.error(f"Erreur pour {user_field} : {str(e)}")
            with col3:
                # Case pour valider le champ
                valid = st.checkbox("Valider", key=f"check_{idx}")
            if valid:
                validated_fields.append(user_field)
        
        # -----------------------------------------------------------
        # Enregistrement du feedback utilisateur (seuls les champs validés)
        # -----------------------------------------------------------
        if st.button("Enregistrer le feedback"):
            image_bytes = uploaded_file.getvalue()
            full_ocr_text = " ".join([r["text"] for r in candidate_fields])
            validated_text = " | ".join(validated_fields)
            c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                      (image_bytes, full_ocr_text, validated_text))
            conn.commit()
            st.success("Feedback enregistré !")
    else:
        st.warning("Aucun champ pertinent détecté par l'OCR.")

