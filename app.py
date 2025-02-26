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
st.write("Téléchargez une image de bordereau. Le système extrait les fragments de texte via OCR, regroupe les lignes, identifie les libellés (ex. 'Part Number', 'Serial Number', 'Designation Class') et tente d'extraire le(s) numéro(s) associé(s) qui se trouvent soit à côté, soit en dessous. Vous pouvez ensuite corriger et valider chaque extraction.")

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
        validated_fields TEXT
    )
""")
conn.commit()

# -----------------------------------------------------------
# Chargement d'EasyOCR
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
# Fonction de regroupement par ligne basée sur la position verticale
# -----------------------------------------------------------
def group_by_line(candidate_fields, threshold=15):
    # Trie par la coordonnée y minimale (du haut vers le bas)
    sorted_fields = sorted(candidate_fields, key=lambda x: x["bbox"][0][1])
    groups = []
    current_group = []
    current_y = None
    for field in sorted_fields:
        y = field["bbox"][0][1]
        if current_y is None:
            current_y = y
            current_group.append(field)
        else:
            if abs(y - current_y) < threshold:
                current_group.append(field)
            else:
                groups.append(current_group)
                current_group = [field]
                current_y = y
    if current_group:
        groups.append(current_group)
    return groups

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
    ocr_texts = []  # Pour sauvegarder le texte complet
    for result in ocr_results:
        bbox, text, conf = result
        candidate_fields.append({"bbox": bbox, "text": text})
        ocr_texts.append(text)
    
    # Regrouper par lignes
    groups = group_by_line(candidate_fields, threshold=15)
    
    # -----------------------------------------------------------
    # Extraction des paires "libellé" / "valeur" basée sur la position
    # -----------------------------------------------------------
    header_pattern = re.compile(r"(part\s*number|serial\s*(number|no)|n°\s*de\s*série|designation\s*class|serie)", re.IGNORECASE)
    extracted_fields = []
    # Parcourir les groupes pour trouver un header et la valeur associée
    for i, group in enumerate(groups):
        group_text = " ".join([field["text"] for field in group])
        if header_pattern.search(group_text):
            # Si le header contient ":", la valeur est sur la même ligne
            if ":" in group_text:
                parts = group_text.split(":")
                value = parts[1].strip()
                if value:
                    extracted_fields.append(value)
                    continue
            # Sinon, on cherche le groupe suivant pour la valeur
            if i + 1 < len(groups):
                next_group_text = " ".join([field["text"] for field in groups[i+1]]).strip()
                if next_group_text:
                    extracted_fields.append(next_group_text)
    
    # Si aucun header n'a été trouvé, utiliser une alternative pour extraire les fragments contenant des chiffres
    if not extracted_fields:
        for group in groups:
            group_text = " ".join([field["text"] for field in group]).strip()
            if re.search(r"\d", group_text):
                extracted_fields.append(group_text)
    
    # -----------------------------------------------------------
    # Validation par l'utilisateur
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
                # Utilisation d'un bouton radio pour validation : Valider / Rejeter / Neutre
                status = st.radio("Statut", options=["Valider", "Rejeter", "Neutre"], key=f"status_{idx}")
            if status == "Valider":
                validated_fields.append(user_field)
        # -----------------------------------------------------------
        # Enregistrement du feedback utilisateur
        # -----------------------------------------------------------
        if st.button("Enregistrer le feedback"):
            image_bytes = uploaded_file.getvalue()
            full_ocr_text = " ".join(ocr_texts)
            c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                      (image_bytes, full_ocr_text, " | ".join(validated_fields)))
            conn.commit()
            st.success("Feedback enregistré !")
    else:
        st.warning("Aucun champ pertinent n'a été extrait.")


