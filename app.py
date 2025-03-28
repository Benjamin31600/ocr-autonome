import streamlit as st
from streamlit_cropper import st_cropper
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

############################################
# 1) FONCTIONS DE NETTOYAGE & GÉNÉRATION
############################################

def correct_image_orientation(image):
    """Corrige l'orientation EXIF d'une image si nécessaire."""
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
    except:
        pass
    return image

def sanitize_number(num: str) -> str:
    """
    Nettoie le segment :
      - supprime les préfixes 'SER', 'S/N' (insensible à la casse),
      - supprime espaces, tirets, et tout caractère non alphanumérique.
    """
    num = num.upper()
    # Retire 'SER' ou 'S/N' potentiellement suivis de ponctuation ou espaces
    num = re.sub(r'(SER|S\s*/\s*N)\s*[\-:,\.;]*', '', num)
    # Retire tous les caractères non alphanumériques
    num = re.sub(r'[^A-Z0-9]', '', num)
    return num

def generate_barcode_pybarcode(sn: str) -> io.BytesIO:
    """Génère un code‑barres Code128 pour la chaîne sn."""
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

############################################
# 2) INTERFACE STREAMLIT
############################################

st.set_page_config(page_title="Daher – OCR & Code‑barres Ultra Sécurisé", page_icon="✈️", layout="wide")

st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        color: #fff;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255,255,255,0.92);
        backdrop-filter: blur(8px);
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1400px;
        margin: 2rem auto;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    .segment-box {
        background-color: rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .confirmed {
        border: 2px solid #00FF00;
        background-color: rgba(0,255,0,0.1);
        padding: 8px;
        border-radius: 8px;
        margin-top: 8px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("""\
Téléversez les pages de votre bordereau. L'application :

- Corrige l'orientation de l'image si nécessaire,
- Permet de sélectionner la zone d'intérêt (cadre rouge),
- Extrait le texte via OCR,
- **Supprime automatiquement** les préfixes "SER", "S/N", les espaces, tirets, etc.,
- Affiche un champ de correction rapide si besoin,
- Propose un bouton "Afficher code-barres" pour valider visuellement chaque segment,
- Génère un PDF final contenant tous les codes-barres confirmés.
""")

# Chargement du modèle EasyOCR
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr','en'])
ocr_reader = load_ocr_model()

uploaded_files = st.file_uploader(
    "Téléchargez vos pages (png, jpg, jpeg) :",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

validated_segments = []

if uploaded_files:
    overall_start = time.time()
    st.write("### Traitement des pages")
    
    for idx_file, file in enumerate(uploaded_files):
        with st.expander(f"Page {idx_file+1}", expanded=True):
            page_start = time.time()
            image = Image.open(file)
            image = correct_image_orientation(image)
            image.thumbnail((1500,1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone d'intérêt (cadre rouge) :")
            cropped = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"crop_{idx_file}")
            st.image(cropped, caption="Zone sélectionnée", use_container_width=True)
            
            # OCR
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            with st.spinner("Extraction OCR..."):
                results = ocr_reader.readtext(cropped_bytes)
            
            # On concatène le texte
            extracted_text = " ".join([res[1] for res in results])
            st.write("**Texte extrait brut :**", extracted_text)
            
            # On découpe par lignes / espaces
            # On applique sanitize_number pour chaque segment
            raw_segments = extracted_text.split()
            cleaned_segments = [sanitize_number(seg) for seg in raw_segments if seg.strip()]
            
            st.write("### Validation des segments")
            local_validated = []
            
            for idx_seg, seg in enumerate(cleaned_segments):
                # On affiche un container pour chaque segment
                with st.container():
                    st.markdown(f"<div class='segment-box'>**Segment {idx_seg+1}**<br/><strong>Proposition nettoyée :</strong> {seg}</div>", unsafe_allow_html=True)
                    
                    # Champ de correction rapide
                    corrected = st.text_input("Corriger si besoin :", value=seg, key=f"correct_{idx_file}_{idx_seg}")
                    
                    # Bouton pour afficher le code-barres
                    if st.button(f"Afficher code-barres (Segment {idx_seg+1})", key=f"showbarcode_{idx_file}_{idx_seg}"):
                        barcode_buf = generate_barcode_pybarcode(corrected)
                        st.image(barcode_buf, caption=f"Code-barres pour : {corrected}", use_container_width=True)
                    
                    # Bouton pour confirmer
                    confirm = st.button(f"Confirmer le segment {idx_seg+1}", key=f"confirm_{idx_file}_{idx_seg}")
                    
                    if confirm:
                        # On considère la version corrigée
                        final_seg = sanitize_number(corrected)
                        st.markdown(f"<div class='confirmed'>Segment validé : {final_seg}</div>", unsafe_allow_html=True)
                        local_validated.append(final_seg)
            
            # Bouton de validation de la page
            if st.button(f"Valider la page {idx_file+1}", key=f"validatepage_{idx_file}"):
                if len(local_validated) == len(cleaned_segments):
                    st.success(f"Page {idx_file+1} validée avec {len(local_validated)} segments.")
                    validated_segments.extend(local_validated)
                else:
                    st.error("Tous les segments n'ont pas été confirmés !")
            
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    # Génération PDF
    if validated_segments and st.button("Générer le PDF global"):
        with st.spinner("Génération du PDF..."):
            try:
                pdf = FPDF()
                pdf.set_auto_page_break(0, margin=10)
                temp_dir = tempfile.gettempdir()
                
                for seg in validated_segments:
                    barcode_buf = generate_barcode_pybarcode(seg)
                    fname = os.path.join(temp_dir, f"barcode_{seg}.png")
                    with open(fname, "wb") as f:
                        f.write(barcode_buf.getvalue())
                    pdf.add_page()
                    pdf.image(fname, x=10, y=10, w=pdf.w - 20)
                
                pdf_path = os.path.join(temp_dir, "barcodes.pdf")
                pdf.output(pdf_path, "F")
                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()
                st.download_button("Télécharger le PDF", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Erreur lors de la génération du PDF : {str(e)}")
        
        overall_end = time.time()
        st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")

