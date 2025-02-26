import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3
import torch
from transformers import LayoutLMv3Tokenizer, LayoutLMv3ForTokenClassification

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

st.title("Daher Aerospace – Extraction Automatique des Champs")
st.write("Téléchargez une image de bordereau. Le système utilise l'OCR pour extraire les champs importants (ex. Part Number, Serial Number) et génère leur code‑barres associé. Vous pouvez modifier chaque valeur si nécessaire.")

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
        corrected_fields TEXT
    )
""")
conn.commit()

# -----------------------------------------------------------
# Chargement des modèles avec mise en cache
# -----------------------------------------------------------
@st.cache_resource
def load_ml_model():
    # Utilise le modèle pré-entraîné public de Microsoft
    tokenizer = LayoutLMv3Tokenizer.from_pretrained("microsoft/layoutlmv3-base")
    model = LayoutLMv3ForTokenClassification.from_pretrained("microsoft/layoutlmv3-base")
    model.eval()  # Mode évaluation
    return tokenizer, model

tokenizer_ml, model_ml = load_ml_model()

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
    # Utilisation d'une approche ML pour identifier les champs pertinents
    # -----------------------------------------------------------
    predicted_fields = []
    max_length = 128  # On fixe la longueur à 128 tokens
    # Créer des dummy boxes fixes, en s'assurant que chaque valeur est un int
    fixed_dummy_boxes = [[int(0), int(0), int(1000), int(1000)] for _ in range(max_length)]
    
    for candidate in candidate_fields:
        txt = candidate["text"]
        # Ignore les textes très courts
        if len(txt.strip()) < 3:
            continue
        try:
            # On encode le texte avec un nombre fixe de dummy boxes
            inputs = tokenizer_ml([txt], boxes=[fixed_dummy_boxes], return_tensors="pt", 
                                    truncation=True, padding="max_length", max_length=max_length)
        except Exception as e:
            st.error(f"Erreur lors de l'encodage pour le texte '{txt}': {str(e)}")
            continue
        with torch.no_grad():
            outputs = model_ml(**inputs)
        logits = outputs.logits  # forme : (1, max_length, num_labels)
        predicted_label_id = torch.argmax(logits, dim=-1)[0, 0].item()
        # Simulation simple : si le texte contient "part" ou "serial", on le considère pertinent
        if re.search(r"(part|serial)", txt, re.IGNORECASE):
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
        st.warning("Aucun champ pertinent n'a été détecté par le modèle ML.")
    
    # -----------------------------------------------------------
    # Enregistrement du feedback utilisateur pour amélioration continue
    # -----------------------------------------------------------
    if st.button("Enregistrer le feedback"):
        image_bytes = uploaded_file.getvalue()
        full_ocr_text = " ".join([r["text"] for r in candidate_fields])
        corrected_fields = " | ".join(updated_fields) if predicted_fields else ""
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_fields) VALUES (?, ?, ?)",
                  (image_bytes, full_ocr_text, corrected_fields))
        conn.commit()
        st.success("Feedback enregistré !")

