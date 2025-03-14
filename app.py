import streamlit as st
from streamlit_cropper import st_cropper
import easyocr
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ExifTags
import io
import sqlite3
import threading
import time
import os
import tempfile
from fpdf import FPDF

# --- Paramètres de sécurité ---
SUPERVISOR_CODE = "SUP1234"  # Code superviseur requis pour valider les numéros suspects

# --- Paires de confusion fréquentes (caractères à risque) ---
confusion_pairs = {
    'S': '8',
    '8': 'S',
    'O': '0',
    '0': 'O',
    'I': '1',
    '1': 'I',
    'B': '8',
    'Z': '2',
}

# --- Fonction pour mettre en évidence les caractères à risque ---
def highlight_confusions(num):
    result_html = ""
    for char in num:
        if char in confusion_pairs or char in confusion_pairs.values():
            result_html += f"<span style='color:red; font-weight:bold;'>{char}</span>"
        else:
            result_html += char
    return result_html

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
    .validation-box {
        padding: 8px;
        margin: 4px 0;
        border: 2px solid #00FF00;
        border-radius: 8px;
        background-color: rgba(0,255,0,0.1);
        font-size: 16px;
        font-weight: 600;
        color: #000;
        text-align: center;
    }
    .non-validation-box {
        padding: 8px;
        margin: 4px 0;
        border: 2px solid #FF0000;
        border-radius: 8px;
        background-color: rgba(255,0,0,0.1);
        font-size: 16px;
        font-weight: 600;
        color: #000;
        text-align: center;
    }
    .low-confidence {
        color: red;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("Téléversez les pages de votre bordereau. Pour chaque page, sélectionnez la zone (cadre rouge), vérifiez le texte extrait, et séparez les numéros (un par ligne). Les caractères suspects sont surlignés en rouge. Pour valider un numéro, cliquez sur la case correspondante. Pour les numéros suspects, une validation superviseur est requise en saisissant le code superviseur dans le champ dédié.")

# --- Connexion à la base SQLite ---
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

# --- Charger EasyOCR ---
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# --- Téléversement multiple de pages ---
uploaded_files = st.file_uploader("Téléchargez les pages de votre BL (png, jpg, jpeg)",
                                    type=["png", "jpg", "jpeg"],
                                    accept_multiple_files=True)

if uploaded_files:
    overall_start = time.time()
    all_validated_serials = []  # Stocke tous les numéros validés
    st.write("### Traitement des pages")
    
    for i, uploaded_file in enumerate(uploaded_files):
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone contenant les numéros (cadre rouge) :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR..."):
                ocr_results = ocr_reader.readtext(cropped_bytes)
            # On récupère le texte et le score OCR
            ocr_items = [(res[1], res[2]) for res in ocr_results]
            extracted_text = " ".join([text for text, conf in ocr_items])
            st.markdown("**Texte extrait :**")
            st.write(extracted_text)
            
            st.subheader("Séparez les numéros (un par ligne)")
            manual_text = st.text_area("Un numéro par ligne :", value=extracted_text, height=150, key=f"manual_{i}")
            lines = [" ".join(l.split()) for l in manual_text.split('\n') if l.strip()]
            
            st.subheader("Validation des numéros")
            confirmed_numbers = []
            with st.form(key=f"validation_form_{i}"):
                for idx, num in enumerate(lines):
                    col1, col2, col3, col4 = st.columns([4,2,2,3])
                    with col1:
                        user_num = st.text_input(f"Numéro {idx+1}", value=num, key=f"num_{i}_{idx}")
                    with col2:
                        # Affichage de l'indice OCR si disponible, sinon N/A
                        if idx < len(ocr_items):
                            orig_text, conf = ocr_items[idx]
                            if user_num != orig_text:
                                st.markdown("<span class='low-confidence'>Modifié - vérifiez manuellement</span>", unsafe_allow_html=True)
                            else:
                                if conf < confidence_threshold:
                                    st.markdown(f"<span class='low-confidence'>Confiance: {conf:.2f}</span>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"<span style='color:green; font-weight:bold;'>Confiance: {conf:.2f}</span>", unsafe_allow_html=True)
                        else:
                            st.write("Confiance N/A")
                    with col3:
                        # Affichage du numéro avec surbrillance des caractères à risque
                        st.markdown(highlight_confusions(user_num), unsafe_allow_html=True)
                    with col4:
                        # Bouton de validation. Pour les numéros avec risque, on peut exiger un code superviseur.
                        if any(ch in confusion_pairs or ch in confusion_pairs.values() for ch in user_num):
                            st.write("Numéro Suspect!")
                            supervisor_val = st.text_input("Code superviseur", type="password", key=f"supervisor_{i}_{idx}")
                            valid = st.checkbox("Confirmer", key=f"confirm_{i}_{idx}") and (supervisor_val == SUPERVISOR_CODE)
                        else:
                            valid = st.checkbox("Confirmer", key=f"confirm_{i}_{idx}")
                        if valid:
                            st.markdown(f'<div class="validation-box">Confirmé : {user_num}</div>', unsafe_allow_html=True)
                            confirmed_numbers.append(user_num)
                        else:
                            st.markdown(f'<div class="non-validation-box">Non confirmé : {user_num}</div>', unsafe_allow_html=True)
                form_submitted = st.form_submit_button("Valider tous les numéros de cette page")
            
            if form_submitted:
                if len(confirmed_numbers) == len(lines) and confirmed_numbers:
                    st.success(f"Tous les numéros de la page {i+1} sont confirmés.")
                    st.write("Codes‑barres générés pour cette page :")
                    cols = st.columns(3)
                    idx = 0
                    for number in confirmed_numbers:
                        barcode_buffer = generate_barcode_pybarcode(number)
                        cols[idx].image(barcode_buffer, caption=f"{number}", use_container_width=True)
                        idx = (idx + 1) % 3
                    all_validated_serials.extend(confirmed_numbers)
                else:
                    st.error("Tous les numéros doivent être confirmés pour valider cette page.")
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    # --- Génération du PDF regroupant tous les codes‑barres validés ---
    if all_validated_serials and st.button("Générer PDF de tous les codes‑barres"):
        st.write("Début de la génération du PDF...")
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
    
    # --- Enregistrement global du feedback ---
    if st.button("Valider et Enregistrer le Feedback global"):
        with st.spinner("Enregistrement du feedback..."):
            combined_text = ""
            for file in uploaded_files:
                combined_text += "\n---\n"
                img = Image.open(file)
                img = correct_image_orientation(img)
                img.thumbnail((1500, 1500))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                page_bytes = buf.getvalue()
                with st.spinner("Extraction OCR..."):
                    results = ocr_reader.readtext(page_bytes)
                combined_text += " ".join([res[1] for res in results])
            def save_feedback():
                c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                          (b"Multiple pages", combined_text, " | ".join(all_validated_serials)))
                conn.commit()
            threading.Thread(target=save_feedback).start()
            st.success("Feedback global enregistré avec succès !")
    
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")



