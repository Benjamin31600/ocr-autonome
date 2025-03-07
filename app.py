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
st.set_page_config(page_title="Daher – Multi Code-barres (Indus)", page_icon="✈️", layout="wide")

st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        font-family: sans-serif;
        color: #ffffff;
        margin: 0; padding: 0;
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
        background-color: #0d1b2a; color: #fff; border: none; border-radius: 30px;
        padding: 14px 40px; font-size: 16px; font-weight: 600;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
        transition: background-color 0.3s ease, transform 0.2s ease;
    }
    .stButton button:hover {
        background-color: #415a77; transform: translateY(-3px);
    }
    .stTextInput input {
        border-radius: 8px;
        padding: 10px;
        font-size: 14px;
        border: 1px solid #ccc;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR : Validation multi code‑barres (Rapide)")

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
# Fonction pour générer un code-barres
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
    st.write("Sélectionnez la zone contenant les numéros (dessinez une boîte avec la souris) :")
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

    # Séparation automatique (format libre) : on sépare par 2 espaces ou plus
    # + retours à la ligne
    temp_text = extracted_text.replace('\n', ' ')
    blocks_auto = re.split(r"\s{2,}", temp_text)
    blocks_auto = [b.strip() for b in blocks_auto if b.strip()]

    st.subheader("Blocs détectés automatiquement")
    if blocks_auto:
        st.write(blocks_auto)
    else:
        st.write("Aucun bloc détecté automatiquement. Vous pouvez compléter manuellement ci-dessous.")

    # On propose un champ pour ajouter d'autres blocs manuellement
    st.subheader("Complément / Séparation manuelle (optionnel)")
    manual_text = st.text_area("Un bloc par ligne :", value="", height=80)
    lines_manual = [l.strip() for l in manual_text.split('\n') if l.strip()]

    # Fusion auto + manuel
    combined = list(set(blocks_auto + lines_manual))

    st.write("---")
    st.write("### Validation / Correction finale")
    st.write("Modifiez si besoin et cochez 'Valider' pour chaque bloc que vous voulez garder.")

    # On va utiliser un formulaire unique pour tout valider
    with st.form("validation_form"):
        corrected_values = {}
        validated_values = {}

        for i, sn in enumerate(combined):
            col1, col2 = st.columns([3,1])
            with col1:
                corrected_sn = st.text_input(f"Bloc {i+1}", value=sn, key=f"txt_{i}")
            with col2:
                valider = st.checkbox("Valider", key=f"chk_{i}", value=True)
            corrected_values[i] = corrected_sn
            validated_values[i] = valider

        submitted = st.form_submit_button("Générer codes-barres")
    
    # Si on a soumis le formulaire
    validated_serials = []
    if submitted:
        for i, sn in enumerate(combined):
            if validated_values[i]:
                validated_serials.append(corrected_values[i])
        
        if validated_serials:
            st.write("### Codes‑barres générés")
            cols = st.columns(3)
            idx = 0
            for vsn in validated_serials:
                barcode_buffer = generate_barcode(vsn)
                cols[idx].image(barcode_buffer, caption=f"{vsn}", use_column_width=True)
                idx = (idx + 1) % 3
        else:
            st.warning("Aucun bloc validé, aucun code-barres généré.")

    # Bouton pour enregistrer le feedback
    if st.button("Enregistrer le feedback"):
        if not validated_serials:
            st.warning("Aucun bloc validé, rien à enregistrer.")
        else:
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


