import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# -----------------------------------------------------------
# CSS & Style : Interface ultra moderne et marketing
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

st.title("Daher Aerospace – Extraction Intelligente des Champs")
st.write("Téléchargez une image de bordereau. Le système utilise l'OCR pour extraire le texte, puis applique une logique heuristique pour identifier les champs pertinents (par exemple, des numéros de série ou de pièces). Un code‑barres associé est généré pour chaque champ, et vous pouvez corriger les valeurs si nécessaire.")

# -----------------------------------------------------------
# Base de données SQLite pour enregistrer le feedback utilisateur
# -----------------------------------------------------------
conn = sqlite3.connect("feedback.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image BLOB,
        ocr_text TEXT,
        corrected_fields TEXT
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
# Téléversement de l'image du bordereau
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
    # Filtrage heuristique des fragments
    # -----------------------------------------------------------
    def is_candidate(text):
        # Le fragment doit être suffisamment long
        if len(text.strip()) < 5:
            return False
        # Doit contenir au moins une lettre et un chiffre
        if not re.search(r"[A-Za-z]", text):
            return False
        if not re.search(r"\d", text):
            return False
        # Éventuellement, rejeter les fragments contenant certains mots non pertinents
        if re.search(r"(delivery|fax|tel|contact|date|order|quantity|adress|carrier|shipping|customer)", text, re.IGNORECASE):
            return False
        return True
    
    predicted_fields = []
    for candidate in candidate_fields:
        txt = candidate["text"]
        if is_candidate(txt):
            predicted_fields.append(txt)
    
    # -----------------------------------------------------------
    # Affichage des champs détectés et génération des codes‑barres associés
    # -----------------------------------------------------------
    if predicted_fields:
        st.subheader("Champs détectés et Codes‑barres associés")
        updated_fields = []
        for idx, field in enumerate(predicted_fields):
            col1, col2 = st.columns(2)
            with col1:
                user_field = st.text_input(f"Champ {idx+1}", value=field, key=f"field_{idx}")
                updated_fields.append(user_field)
            with col2:
                try:
                    barcode_buffer = generate_barcode(user_field)
                    st.image(barcode_buffer, caption=f"Code‑barres pour {user_field}", use_container_width=True)
                except Exception as e:
                    st.error(f"Erreur pour {user_field} : {str(e)}")
    else:
        st.warning("Aucun champ pertinent n'a été détecté.")
    
    # -----------------------------------------------------------
    # Enregistrement du feedback utilisateur
    # -----------------------------------------------------------
    if st.button("Enregistrer le feedback"):
        image_bytes = uploaded_file.getvalue()
        full_ocr_text = " ".join([r["text"] for r in candidate_fields])
        corrected_fields = " | ".join(updated_fields) if predicted_fields else ""
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_fields) VALUES (?, ?, ?)",
                  (image_bytes, full_ocr_text, corrected_fields))
        conn.commit()
        st.success("Feedback enregistré !")


