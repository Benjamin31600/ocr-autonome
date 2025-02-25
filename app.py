import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# --- Injection de CSS ultra moderne pour une interface SaaS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
    
    /* Arrière-plan et typographie */
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
    /* Boutons */
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
    /* Zone de saisie */
    .stTextInput input {
        border-radius: 8px;
        padding: 10px;
        font-size: 16px;
        border: 1px solid #ccc;
    }
    /* Style des images de codes-barres */
    .barcode-img {
        margin-top: 10px;
        border: 1px solid #eee;
        padding: 10px;
        border-radius: 8px;
        background: #fff;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Titre et description ---
st.title("Daher Aerospace – Réception & Traitement des Numéros")
st.write("Prenez en photo le bordereau de réception. L'application extrait et affiche uniquement les numéros de série ou de pièces détectés, avec leur code-barres associé. Vous pouvez modifier chaque numéro si nécessaire.")

# --- Connexion à la base de données SQLite pour le feedback ---
conn = sqlite3.connect("feedback.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image BLOB,
        ocr_text TEXT,
        corrected_text TEXT
    )
''')
conn.commit()

# --- Mise en cache du modèle OCR et fonctions d'optimisation ---
@st.cache(allow_output_mutation=True)
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])

@st.cache(show_spinner=False)
def perform_ocr(image_bytes):
    reader = load_ocr_model()
    return reader.readtext(image_bytes)

@st.cache(show_spinner=False)
def generate_barcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_img = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_img.write(buffer)
    buffer.seek(0)
    return buffer

# --- Téléversement de l'image ---
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    # Redimensionner l'image pour accélérer l'OCR (optionnel)
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau de réception", use_column_width=True)
    
    with st.spinner("Extraction du texte..."):
        results = perform_ocr(uploaded_file.getvalue())
    # Concaténer uniquement le texte OCR pour l'extraction
    ocr_text = " ".join([text for (_, text, _) in results])
    
    # --- Extraction ciblée des numéros ---
    # Cette regex couvre différentes variantes (français et anglais) telles que :
    # "numéro de série", "n° de série", "serial number", "part number", "pièce serialisée", etc.
    pattern = re.compile(
        r'(?:(?:num(?:éro)?s?\s*de\s*(?:s[ée]rie(?:s)?|series))'
        r'|(?:n°\s*de\s*(?:s[ée]rie(?:s)?|series))'
        r'|(?:serial\s*(?:number|no\.?))'
        r'|(?:part\s*(?:number|no\.?))'
        r'|(?:pi[eè]ce(?:s)?\s*serialis[eé]e?s?))'
        r'\s*[:\-]?\s*'
        r'((?:[A-Za-z0-9]+\s?)+)',
        re.IGNORECASE
    )
    matches = pattern.findall(ocr_text)
    
    if matches:
        st.subheader("Numéros détectés et Codes-barres associés")
        # Conserver les numéros avec leurs espaces internes (sans suppression totale)
        serial_numbers = [match.strip() for match in matches]
        serial_numbers = list(dict.fromkeys(serial_numbers))  # Éliminer les doublons
        
        updated_numbers = []
        # Pour chaque numéro, afficher un champ modifiable et le code-barres associé
        for i, sn in enumerate(serial_numbers):
            col1, col2 = st.columns([1, 1])
            with col1:
                num_input = st.text_input(f"Numéro {i+1}", value=sn, key=f"num_{i}")
                updated_numbers.append(num_input)
            with col2:
                try:
                    buffer = generate_barcode(num_input)
                    st.image(buffer, caption=f"Code-barres pour {num_input}", use_column_width=True)
                except Exception as e:
                    st.error(f"Erreur pour {num_input} : {str(e)}")
    else:
        st.warning("Aucun numéro n'a été détecté. Vérifiez que le bordereau contient des libellés tels que 'numéro de série', 'n° de série', 'serial number', 'part number', ou 'pièce serialisée'.")
    
    # --- Zone de feedback pour l'auto-amélioration (en option) ---
    if st.button("Enregistrer le feedback"):
        image_bytes = uploaded_file.getvalue()
        # On enregistre uniquement le texte OCR complet pour référence, ainsi que les numéros modifiés (joint en une chaîne)
        corrected_text = " | ".join(updated_numbers)
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_text) VALUES (?, ?, ?)",
                  (image_bytes, ocr_text, corrected_text))
        conn.commit()
        st.success("Feedback enregistré !")
