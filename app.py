import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3
from transformers import LayoutLMv3Tokenizer, LayoutLMv3ForTokenClassification
import torch

# --- Chargement du CSS pour une interface ultra moderne ---
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
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – Extraction Automatique des Champs")
st.write("Prenez en photo un bordereau. Le système utilise l'OCR et le modèle ML pour extraire automatiquement les champs importants (ex : Part Number, Serial Number) et génère leur code‑barres.")

# --- Charger le modèle ML LayoutLMv3 entraîné ---
@st.cache_resource
def load_ml_model():
    tokenizer = LayoutLMv3Tokenizer.from_pretrained("my_layoutlmv3_model")
    model = LayoutLMv3ForTokenClassification.from_pretrained("my_layoutlmv3_model")
    model.eval()
    return tokenizer, model

tokenizer_ml, model_ml = load_ml_model()

# --- Charger le modèle OCR EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])

ocr_reader = load_ocr_model()

# --- Fonction pour générer un code‑barres pour un numéro donné ---
@st.cache_data(show_spinner=False)
def generate_barcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Connexion à la base de données SQLite pour le feedback ---
conn = sqlite3.connect("feedback.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image BLOB,
        ocr_text TEXT,
        corrected_fields TEXT
    )
''')
conn.commit()

# --- Téléversement de l'image du bordereau ---
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau", use_container_width=True)
    
    # --- Extraction OCR avec EasyOCR ---
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(uploaded_file.getvalue())
    # Concaténer le texte de chaque bounding box et garder les coordonnées
    ocr_data = [{"bbox": res[0], "text": res[1]} for res in ocr_results]
    
    # --- Ici, vous pourriez ajouter une étape d'annotation manuelle pour générer des feedbacks ---
    # Pour la démo, nous allons simplement afficher le texte OCR
    full_ocr_text = " ".join([item["text"] for item in ocr_data])
    st.subheader("Texte OCR complet (pour référence)")
    st.write(full_ocr_text)
    
    # --- Utilisation du modèle ML pour prédire les labels sur les bounding boxes ---
    # Vous devrez normaliser les coordonnées (par exemple, entre 0 et 1000) si nécessaire.
    # Ici, nous créons une liste simplifiée pour simuler l'inférence.
    # Pour chaque bounding box, on envoie le texte au modèle ML.
    predicted_fields = []
    for item in ocr_data:
        # Préparer une "entrée" pour le modèle
        # Dans un cas réel, vous fourniriez le texte, les coordonnées normalisées, etc.
        # Ici, nous utilisons simplement le texte.
        inputs = tokenizer_ml(item["text"], return_tensors="pt", truncation=True, padding="max_length", max_length=128)
        with torch.no_grad():
            outputs = model_ml(**inputs)
        logits = outputs.logits
        predicted_label_id = torch.argmax(logits, dim=-1)[0].item()
        # Supposons que le modèle renvoie 1 pour PART_NUMBER et 2 pour SERIAL_NUMBER, 0 pour rien.
        if predicted_label_id in [1, 2]:
            predicted_fields.append(item["text"])
    
    if predicted_fields:
        st.subheader("Champs extraits et Codes-barres associés")
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
    
    # --- Option pour enregistrer le feedback (image, texte OCR complet et champs corrigés) ---
    if st.button("Enregistrer le feedback"):
        image_bytes = uploaded_file.getvalue()
        corrected_fields = " | ".join(updated_fields) if predicted_fields else ""
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_fields) VALUES (?, ?, ?)",
                  (image_bytes, full_ocr_text, corrected_fields))
        conn.commit()
        st.success("Feedback enregistré !")
