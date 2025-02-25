import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# --- Injection de CSS personnalisé pour une interface moderne aux couleurs Daher Aerospace ---
st.markdown("""
    <style>
    /* Fond et style global */
    body {
        background-color: #f4f4f4;
        font-family: 'Arial', sans-serif;
    }
    .stApp {
        background-color: #f4f4f4;
    }
    /* Titres et textes */
    h1, h2, h3 {
        color: #003366;
    }
    /* Boutons personnalisés */
    .stButton button {
        background-color: #003366;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 10px 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Titre et description ---
st.title("Daher Aerospace – Reception & Serial Number Processing")
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
    # Afficher l'image uploadée
    image = Image.open(uploaded_file)
    st.image(image, caption="Reception document", use_column_width=True)
    
    st.write("**Extracting text...**")
    reader = easyocr.Reader(['fr', 'en'])  # Inclut français et anglais
    results = reader.readtext(uploaded_file.getvalue())
    detected_text = " ".join([text for (_, text, _) in results])
    
    st.write("**Detected text:**")
    st.write(detected_text)
    
    # --- Extraction des numéros de série avec de nombreuses variantes ---
    # La regex ci-dessous tente de couvrir un maximum de cas, en français et en anglais.
    pattern = re.compile(
        r'(?:(?:num(?:éro)?s?\s*(?:de\s*)?(?:s[ée]rie(?:s)?|series))'    # ex: "numéro(s) de série(s)" ou "series"
        r'|(?:n°\s*(?:de\s*)?(?:s[ée]rie(?:s)?|series))'                  # ex: "n° de série(s)"
        r'|(?:serial\s*(?:number|no\.?))'                                  # ex: "serial number", "serial no"
        r'|(?:serie\s*number))'                                           # ex: "serie number"
        r'\s*[:\-]?\s*'
        r'((?:[A-Za-z0-9]+\s?)+)',                                        # Capture le ou les numéros (avec ou sans espace)
        re.IGNORECASE
    )
    
    matches = pattern.findall(detected_text)
    
    if matches:
        st.write("**Extracted Serial Numbers:**")
        serial_numbers = []
        for match in matches:
            # Nettoyer la chaîne extraite (supprimer les espaces superflus)
            sn = match.strip()
            sn = re.sub(r'\s+', '', sn)
            serial_numbers.append(sn)
        
        # Éliminer les doublons
        serial_numbers = list(dict.fromkeys(serial_numbers))
        
        # Afficher les numéros et générer les codes-barres
        for sn in serial_numbers:
            st.markdown(f"**{sn}**")
            try:
                CODE128 = barcode.get_barcode_class('code128')
                barcode_img = CODE128(sn, writer=ImageWriter())
                buffer = io.BytesIO()
                barcode_img.write(buffer)
                buffer.seek(0)
                st.image(buffer, caption=f"Barcode for {sn}", use_column_width=False)
            except Exception as e:
                st.error(f"Error generating barcode for {sn}: {str(e)}")
    else:
        st.write("No serial numbers detected. Please check the document format and ensure it includes labels such as 'numéro de série', 'n° de série', 'serial number', etc.")
    
    # --- Zone pour permettre à l'opérateur d'ajuster le texte final (feedback) ---
    final_text = st.text_area("Adjust the extracted text if necessary", value=detected_text)
    
    if st.button("Submit feedback"):
        image_bytes = uploaded_file.getvalue()
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_text) VALUES (?, ?, ?)",
                  (image_bytes, detected_text, final_text))
        conn.commit()
        st.success("Thank you! Your feedback will be used to further improve the system over time.")
