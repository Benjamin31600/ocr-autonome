import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# --- Injection de CSS personnalisé pour une interface ultra moderne ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
    body {
        background: linear-gradient(135deg, #f4f4f4, #ffffff);
        font-family: 'Roboto', sans-serif;
    }
    .stApp {
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
    }
    .stTextArea textarea {
        border-radius: 8px;
        padding: 10px;
        font-size: 16px;
        border: 1px solid #ccc;
    }
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
st.title("Daher Aerospace – Reception & Serial Processing")
st.write("Capture the reception document. The system extracts text, identifies serial numbers, and generates their barcodes. It continuously learns from user feedback.")

# --- Connexion à la base de données SQLite pour stocker le feedback ---
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

# --- Téléversement de l'image ---
uploaded_file = st.file_uploader("Upload an image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    # Affichage de l'image uploadée
    image = Image.open(uploaded_file)
    st.image(image, caption="Reception document", use_column_width=True)
    
    # --- Extraction du texte avec un spinner pour indiquer l'avancement ---
    with st.spinner("Extracting text..."):
        reader = easyocr.Reader(['fr', 'en'])  # Langues français et anglais
        results = reader.readtext(uploaded_file.getvalue())
    detected_text = " ".join([text for (_, text, _) in results])
    
    st.subheader("Detected Text:")
    st.write(detected_text)
    
    # --- Extraction ciblée des numéros de série ---
    # Cette regex couvre : 
    # - "numéro de série", "numéros de série", "n° de série", "serial number", "serial no"
    # - et "pièce serialisée" avec ou sans accent, au singulier ou au pluriel
    pattern = re.compile(
        r'(?:(?:num(?:éro)?(?:s)?\s*(?:de\s*)?(?:s[ée]rie(?:s)?|series))'
        r'|(?:n°\s*(?:de\s*)?(?:s[ée]rie(?:s)?|series))'
        r'|(?:serial\s*(?:number|no\.?))'
        r'|(?:pi[eè]ce(?:s)?\s*(?:serialis[eé]e?s?)))\s*[:\-]?\s*'
        r'((?:[A-Za-z0-9]+\s?)+)',
        re.IGNORECASE
    )
    
    matches = pattern.findall(detected_text)
    
    if matches:
        st.subheader("Extracted Serial Numbers & Barcodes:")
        serial_numbers = []
        for match in matches:
            sn = match.strip()
            sn = re.sub(r'\s+', '', sn)  # Supprime les espaces inutiles
            serial_numbers.append(sn)
        # Éliminer les doublons
        serial_numbers = list(dict.fromkeys(serial_numbers))
        
        # Affichage des numéros et codes-barres dans des colonnes pour un rendu moderne
        for sn in serial_numbers:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"**{sn}**")
            with col2:
                try:
                    CODE128 = barcode.get_barcode_class('code128')
                    barcode_img = CODE128(sn, writer=ImageWriter())
                    buffer = io.BytesIO()
                    barcode_img.write(buffer)
                    buffer.seek(0)
                    st.image(buffer, caption=f"Barcode for {sn}", use_column_width=True)
                except Exception as e:
                    st.error(f"Error generating barcode for {sn}: {str(e)}")
    else:
        st.warning("No serial numbers detected. Ensure the document includes labels such as 'numéro de série', 'n° de série', 'serial number', or 'pièce serialisée'.")
    
    # --- Zone de feedback pour améliorer le système ---
    final_text = st.text_area("Adjust the extracted text if needed", value=detected_text)
    
    if st.button("Submit Feedback"):
        image_bytes = uploaded_file.getvalue()
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_text) VALUES (?, ?, ?)",
                  (image_bytes, detected_text, final_text))
        conn.commit()
        st.success("Thank you! Your feedback will help the system learn and improve over time.")
