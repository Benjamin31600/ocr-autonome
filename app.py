import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import pytesseract
import difflib
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ExifTags
import io
import os
import tempfile
from fpdf import FPDF
import time

# --- Fonction pour corriger l'orientation de l'image via EXIF ---
def correct_image_orientation(image):
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

# --- Fonction pour générer un code‑barres (Code128) ---
def generate_barcode_pybarcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

# --- Fonction pour comparer deux chaînes et mettre en évidence les différences ---
def highlight_differences(text1, text2):
    # Compare caractere par caractere
    diff = difflib.ndiff(list(text1), list(text2))
    result_html = ""
    for d in diff:
        # '  ' signifie pas de différence
        if d.startswith('  '):
            result_html += d[2:]
        # '-' indique que le caractère figure dans text1 mais pas text2
        elif d.startswith('- '):
            result_html += f"<span style='background-color:yellow; color:red;'>{d[2:]}</span>"
        # '+' indique un caractère ajouté dans text2, on l'affiche en bleu
        elif d.startswith('+ '):
            result_html += f"<span style='background-color:yellow; color:blue;'>{d[2:]}</span>"
    return result_html

# --- Configuration de la page et styles CSS ---
st.set_page_config(page_title="Daher – OCR & Code‑barres Ultra Sécurisé", page_icon="✈️", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        font-family: 'Poppins', sans-serif;
        color: #ffffff;
        margin: 0;
        padding: 0;
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
        background-color: #415a77;
        transform: translateY(-3px);
    }
    .validated {
        border: 2px solid #00FF00;
        padding: 8px;
        border-radius: 8px;
        background-color: rgba(0,255,0,0.1);
        margin-bottom: 4px;
    }
    .non-validated {
        border: 2px solid #FF0000;
        padding: 8px;
        border-radius: 8px;
        background-color: rgba(255,0,0,0.1);
        margin-bottom: 4px;
    }
    .low-confidence {
        color: red;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("Téléversez les pages de votre bordereau. Pour chaque page, sélectionnez la zone d'intérêt (cadre rouge), comparez les extractions OCR d'EasyOCR et Tesseract, et corrigez si nécessaire. Le texte sera séparé ligne par ligne. Les différences entre les deux OCR seront mises en évidence afin que vous puissiez vérifier rapidement les anomalies (ex. un 'S' mal lu en '8'). Validez chaque numéro en cochant la case correspondante. Seuls les numéros validés seront utilisés pour générer les codes‑barres et le PDF final.")

# --- Charger EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement multiple de pages ---
uploaded_files = st.file_uploader("Téléchargez les pages de votre BL (png, jpg, jpeg)",
                                    type=["png", "jpg", "jpeg"],
                                    accept_multiple_files=True)

overall_start = time.time()
all_validated_serials = []

if uploaded_files:
    st.write("### Traitement des pages")
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone d'intérêt (cadre rouge) :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR EasyOCR..."):
                easy_results = ocr_reader.readtext(cropped_bytes)
            with st.spinner("Extraction OCR Tesseract..."):
                tess_text = pytesseract.image_to_string(cropped_img)
            
            st.markdown("**Résultat OCR (EasyOCR) :**")
            easy_text = " ".join([res[1] for res in easy_results])
            st.write(easy_text)
            st.markdown("**Résultat OCR (Tesseract) :**")
            st.write(tess_text)
            
            # Comparaison automatique des deux résultats
            highlighted_diff = highlight_differences(easy_text, tess_text)
            st.markdown("**Comparaison (différences mises en évidence) :**", unsafe_allow_html=True)
            st.markdown(highlighted_diff, unsafe_allow_html=True)
            
            st.markdown("**Texte utilisé pour validation :**")
            st.write(easy_text)
            
            st.subheader("Séparez les numéros (un par ligne)")
            manual_text = st.text_area("Corrigez ou séparez les numéros :", value=easy_text, height=150, key=f"manual_{i}")
            lines = [" ".join(l.split()) for l in manual_text.split('\n') if l.strip()]
            
            st.subheader("Validation des numéros")
            confirmed_numbers = []
            with st.form(key=f"validation_form_{i}"):
                for idx, num in enumerate(lines):
                    cols = st.columns([5,2])
                    with cols[0]:
                        # Affichage du numéro avec surbrillance des différences
                        st.markdown(f"**Numéro {idx+1} :** {highlight_confusions(num)}", unsafe_allow_html=True)
                    with cols[1]:
                        valid = st.checkbox("Valider", key=f"check_{i}_{idx}")
                    if valid:
                        st.markdown(f'<div class="validated">Confirmé : {num}</div>', unsafe_allow_html=True)
                        confirmed_numbers.append(num)
                    else:
                        st.markdown(f'<div class="non-validated">Non validé : {num}</div>', unsafe_allow_html=True)
                form_submitted = st.form_submit_button("Confirmer tous les numéros de cette page")
            
            if form_submitted:
                if len(confirmed_numbers) == len(lines) and confirmed_numbers:
                    st.success(f"Tous les numéros de la page {i+1} sont validés.")
                    st.write("Codes‑barres générés pour cette page :")
                    barcode_cols = st.columns(3)
                    for idx, number in enumerate(confirmed_numbers):
                        barcode_buffer = generate_barcode_pybarcode(number)
                        barcode_cols[idx % 3].image(barcode_buffer, caption=f"{number}", use_container_width=True)
                    all_validated_serials.extend(confirmed_numbers)
                else:
                    st.error("Veuillez valider TOUS les numéros de cette page.")
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    if all_validated_serials and st.button("Générer PDF de tous les codes‑barres"):
        st.write("Génération du PDF en cours...")
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            st.write("Dossier temporaire utilisé :", temp_dir)
            for vsn in all_validated_serials:
                st.write("Traitement du numéro :", vsn)
                barcode_buffer = generate_barcode_pybarcode(vsn)
                file_name = f"barcode_{vsn.replace(' ', '_')}.png"
                image_path = os.path.join(temp_dir, file_name)
                with open(image_path, "wb") as f:
                    f.write(barcode_buffer.getvalue())
                st.write("Image sauvegardée :", image_path)
                pdf.add_page()
                pdf.image(image_path, x=10, y=10, w=pdf.w - 20)
                st.write("Ajouté au PDF :", vsn)
            pdf_path = os.path.join(temp_dir, "barcodes.pdf")
            pdf.output(pdf_path, "F")
            st.write("PDF généré à :", pdf_path)
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            st.download_button("Télécharger le PDF des codes‑barres", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
        except Exception as e:
            st.error("Erreur lors de la génération du PDF : " + str(e))
    
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")

