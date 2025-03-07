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
# Configuration Streamlit
# -----------------------------------------------------------
st.set_page_config(page_title="Daher – Multi Code-barres (Variante Générique)", page_icon="✈️", layout="wide")

# Un peu de style
st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        font-family: sans-serif;
        color: #ffffff;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255,255,255,0.9);
        backdrop-filter: blur(8px);
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1400px;
        margin: 2rem auto;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    .stButton button {
        background-color: #0d1b2a;
        color: #fff;
        border: none;
        border-radius: 30px;
        padding: 14px 40px;
        font-size: 16px;
        font-weight: 600;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
        transition: background-color 0.3s ease, transform 0.2s ease;
    }
    .stButton button:hover {
        background-color: #415a77; transform: translateY(-3px);
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR Multi Code-barres (Format Libre)")
st.write("Sélectionnez la zone sur l'image, laissez l'OCR extraire le texte, puis la détection auto sépare le texte en blocs (espaces multiples ou sauts de ligne). Vous pouvez corriger manuellement et valider chaque bloc, générant un code‑barres par numéro validé.")

# -----------------------------------------------------------
# Base SQLite
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
# Génération de code-barres
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
    
    image = Image.open(uploaded_file)
    st.image(image, caption="Image originale", use_column_width=True)
    
    # Sélection de la zone
    st.write("Sélectionnez la zone contenant les numéros (dessinez une boîte).")
    cropped_img = st_cropper(image, realtime_update=True, box_color="#0d1b2a", aspect_ratio=None)
    st.image(cropped_img, caption="Zone sélectionnée", use_column_width=True)
    
    # Convertir en bytes pour l'OCR
    buf = io.BytesIO()
    cropped_img.save(buf, format="PNG")
    cropped_bytes = buf.getvalue()
    
    # Extraction OCR
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(cropped_bytes)
    extracted_text = " ".join([res[1] for res in ocr_results])
    
    st.markdown("**Texte extrait :**")
    st.write(extracted_text)
    
    # -----------------------------------------------------------
    # Détection automatique (format générique)
    # On sépare par "espaces multiples" ou "retours à la ligne"
    # -----------------------------------------------------------
    # ex: "SER CHT 1470   SER CHT 1471\nSER CHT 1520" => ["SER CHT 1470", "SER CHT 1471", "SER CHT 1520"]
    
    # 1. Remplacer les retours à la ligne par des espaces
    temp_text = extracted_text.replace('\n', ' ')
    # 2. Split par 2 espaces ou plus
    blocks_auto = re.split(r"\s{2,}", temp_text)
    
    # On retire les blocs vides
    blocks_auto = [b.strip() for b in blocks_auto if b.strip()]
    
    st.subheader("Détection auto (espaces multiples)")
    if blocks_auto:
        st.write("Blocs détectés :", blocks_auto)
    else:
        st.write("Aucun bloc détecté automatiquement. Vous pouvez compléter manuellement ci-dessous.")
    
    # Séparation manuelle (si la détection auto est insuffisante)
    st.subheader("Ajout / Séparation manuelle (optionnel)")
    manual_text = st.text_area("Mettez d'autres blocs (un par ligne) ou réécrivez certains numéros", value="", height=100)
    lines_manual = [l.strip() for l in manual_text.split('\n') if l.strip()]
    
    # Fusion auto + manuel
    combined = list(set(blocks_auto + lines_manual))
    
    # -----------------------------------------------------------
    # Validation / Correction finale
    # -----------------------------------------------------------
    st.write("### Validation finale de chaque bloc / numéro")
    validated_serials = []
    for sn in combined:
        st.write(f"**Bloc détecté** : {sn}")
        corrected_sn = st.text_input(f"Correction pour {sn}", value=sn, key=f"txt_{sn}")
        status = st.radio(f"Statut pour {sn}", ["Valider", "Rejeter"], key=f"radio_{sn}")
        if status == "Valider":
            validated_serials.append(corrected_sn)
    
    # Génération de code-barres multiples
    if st.button("Générer codes-barres multiples"):
        if validated_serials:
            st.write("Codes‑barres individuels :")
            for vsn in validated_serials:
                barcode_buffer = generate_barcode(vsn)
                st.image(barcode_buffer, caption=f"Code‑barres : {vsn}", use_column_width=True)
        else:
            st.warning("Aucun numéro validé.")
    
    # Enregistrement final du feedback
    if st.button("Enregistrer le feedback"):
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


