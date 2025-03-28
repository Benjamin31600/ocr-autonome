import streamlit as st
import easyocr
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ExifTags
import io
import os
import re
import tempfile
from fpdf import FPDF
import time
import pandas as pd

# --- Fonction de nettoyage renforcé ---
def sanitize_number(num: str) -> str:
    """
    Nettoie le texte en supprimant les préfixes 'S/N' ou 'SER' (insensible à la casse)
    ainsi que tous les caractères non alphanumériques (espaces, tirets, ponctuation, etc.)
    """
    num = num.upper()
    num = re.sub(r'(SER|S\s*/\s*N)[\s:,\-\.]*', '', num)
    num = re.sub(r'[^0-9A-Z]', '', num)
    return num

# --- Fonction pour générer un code‑barres (Code128) ---
def generate_barcode_pybarcode(sn: str) -> io.BytesIO:
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Correction d'orientation de l'image ---
def correct_image_orientation(image: Image.Image) -> Image.Image:
    try:
        exif = image._getexif()
        if exif:
            orientation = exif.get(274)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except Exception as e:
        st.warning(f"Erreur d'orientation : {e}")
    return image

# --- Configuration de la page ---
st.set_page_config(page_title="Daher – OCR & Code‑barres (Tableau éditable)", page_icon="✈️", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        font-family: 'Poppins', sans-serif;
        color: #fff;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255,255,255,0.92);
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1400px;
        margin: 2rem auto;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    </style>
""", unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres (Tableau éditable)")
st.write("""
Téléversez vos pages de bordereau. L’application extrait les numéros via OCR, les nettoie automatiquement 
(en supprimant "S/N", "SER", espaces, tirets, etc.) et affiche le tout dans un tableau interactif. 
Vous pouvez rapidement corriger les numéros dans ce tableau. 
Ensuite, cliquez sur « Valider la table » pour enregistrer vos modifications, afficher un aperçu des codes‑barres, 
et enfin générer un PDF regroupant tous les codes‑barres validés.
""")

# --- Chargement du modèle OCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement des images ---
uploaded_files = st.file_uploader("Téléchargez vos pages (PNG, JPG, JPEG) :", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files:
    overall_start = time.time()
    all_validated_numbers = []
    extracted_data = []  # Liste pour stocker les données OCR sous forme de dict
    st.write("### Traitement des pages")
    
    for idx, file in enumerate(uploaded_files):
        st.subheader(f"Page {idx+1}")
        image = Image.open(file)
        image = correct_image_orientation(image)
        image.thumbnail((1500,1500))
        st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
        
        # Utilisez st_cropper pour sélectionner la zone d'intérêt
        st.write("Sélectionnez la zone d'intérêt (cadre rouge) :")
        from streamlit_cropper import st_cropper  # Assurez-vous que streamlit-cropper est installé
        cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"crop_{idx}")
        st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
        
        # Convertir l'image recadrée en bytes
        buf = io.BytesIO()
        cropped_img.save(buf, format="PNG")
        cropped_bytes = buf.getvalue()
        
        with st.spinner("Extraction OCR..."):
            ocr_results = ocr_reader.readtext(cropped_bytes)
        
        # Pour simplifier, nous considérons chaque mot OCR comme un segment
        for res in ocr_results:
            text = res[1]
            conf = res[2]
            # Nettoyage automatique
            clean_text = sanitize_number(text)
            extracted_data.append({
                "OCR_Result": text,
                "Proposition": clean_text,
                "Confiance (%)": int(conf*100)
            })
    
    # Créer un DataFrame à partir des données extraites
    df = pd.DataFrame(extracted_data)
    
    st.write("### Tableaux des numéros extraits")
    st.write("Vous pouvez modifier directement la colonne 'Proposition' si une correction est nécessaire.")
    
    # Utiliser l'éditeur de données interactif
    edited_df = st.experimental_data_editor(df, num_rows="dynamic", use_container_width=True)
    
    # Bouton pour valider la table
    if st.button("Valider la table"):
        # Extraire la colonne validée
        final_numbers = edited_df["Proposition"].tolist()
        st.success("Table validée.")
        all_validated_numbers.extend(final_numbers)
        
        # Afficher un aperçu des codes‑barres
        st.write("### Aperçu des codes‑barres")
        cols = st.columns(3)
        for i, num in enumerate(final_numbers):
            barcode_buffer = generate_barcode_pybarcode(num)
            cols[i % 3].image(barcode_buffer, caption=num, use_container_width=True)
        
        # Générer le PDF final
        if st.button("Générer le PDF de tous les codes‑barres"):
            with st.spinner("Génération du PDF..."):
                try:
                    pdf = FPDF()
                    pdf.set_auto_page_break(0, margin=10)
                    temp_dir = tempfile.gettempdir()
                    for num in final_numbers:
                        buf = generate_barcode_pybarcode(num)
                        fname = os.path.join(temp_dir, f"barcode_{num}.png")
                        with open(fname, "wb") as f:
                            f.write(buf.getvalue())
                        pdf.add_page()
                        pdf.image(fname, x=10, y=10, w=pdf.w - 20)
                    pdf_path = os.path.join(temp_dir, "barcodes.pdf")
                    pdf.output(pdf_path, "F")
                    with open(pdf_path, "rb") as f:
                        pdf_data = f.read()
                    st.download_button("Télécharger le PDF", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
                except Exception as e:
                    st.error(f"Erreur lors de la génération du PDF : {e}")
    
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")

