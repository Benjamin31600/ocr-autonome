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

########################################
# 1) FONCTIONS DE NETTOYAGE ET GÉNÉRATION
########################################

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
    Nettoie le texte pour enlever :
    - Les préfixes 'SER', 'S/N', etc.
    - Espaces, tirets, et tout caractère non alphanumérique.
    """
    num = num.upper()
    num = re.sub(r'(SER|S\s*/\s*N)[\s:\-,]*', '', num)  # supprime SER, S/N
    num = re.sub(r'[^0-9A-Z]', '', num)                # supprime tout ce qui n'est pas chiffres ou lettres
    return num

def generate_barcode_pybarcode(sn: str) -> io.BytesIO:
    """Génère un code‑barres Code128 pour la chaîne sn."""
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

########################################
# 2) INTERFACE STREAMLIT
########################################

st.set_page_config(page_title="Daher – OCR & Code‑barres Ultra Ergonomique", page_icon="✈️", layout="wide")

st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        color: #ffffff;
    }
    [data-testid="stAppViewContainer"] {
        background: rgba(255,255,255,0.92);
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1400px;
        margin: 2rem auto;
    }
    .segment-box {
        background-color: rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .validated {
        border: 2px solid #00FF00;
        background-color: rgba(0,255,0,0.1);
        padding: 8px;
        border-radius: 8px;
        margin-top: 8px;
    }
    .nonvalidated {
        border: 2px solid #FF0000;
        background-color: rgba(255,0,0,0.1);
        padding: 8px;
        border-radius: 8px;
        margin-top: 8px;
    }
    .column-container {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
    }
    .column {
        background-color: rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 1rem;
        flex: 1;
        min-width: 300px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres (Colonne)")

@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr','en'])
ocr_reader = load_ocr_model()

uploaded_files = st.file_uploader(
    "Téléchargez vos pages (png, jpg, jpeg) :",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

# Pour stocker les segments validés globalement
global_validated_segments = []

if uploaded_files:
    st.write("### Traitement des pages")

    for idx_file, file in enumerate(uploaded_files):
        with st.expander(f"Page {idx_file+1}", expanded=True):
            image = Image.open(file)
            image = correct_image_orientation(image)
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone d'intérêt :")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"crop_{idx_file}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            # Récupération des bounding boxes via EasyOCR
            with st.spinner("Extraction OCR..."):
                ocr_results = ocr_reader.readtext(cropped_bytes, detail=1)
                # ocr_results : liste de [ [x0,y0], [x1,y1], texte, conf ]
            
            # Tri par coordonnée X (pour un affichage en colonnes)
            # On prend la moyenne (x0 + x1)/2 pour l'axe X
            for r in ocr_results:
                # on insère un champ 'midX' pour pouvoir trier
                box = r[0]
                midX = (box[0][0] + box[1][0])/2
                r.append(midX)  # r[4] = midX
            # On trie par r[4] (midX)
            ocr_results.sort(key=lambda x: x[4])
            
            # On affiche en "colonnes" : on peut séparer en 2-3 colonnes en fonction de la distance X
            # Pour la démo, on va juste les afficher dans l'ordre, regroupés si < X + tol
            col_container = st.container()
            columns_data = []
            current_col = []
            # On choisit un threshold pour distinguer les colonnes
            # ex: si la différence de midX > 100 px, on change de colonne
            threshold_col = 150
            
            if len(ocr_results) > 0:
                current_x = ocr_results[0][4]
                current_col.append(ocr_results[0])
                for r in ocr_results[1:]:
                    if abs(r[4] - current_x) > threshold_col:
                        # On change de colonne
                        columns_data.append(current_col)
                        current_col = [r]
                        current_x = r[4]
                    else:
                        current_col.append(r)
                # on ajoute la dernière col
                if current_col:
                    columns_data.append(current_col)
            
            # columns_data est une liste de colonnes, chaque colonne est une liste de segments OCR
            validated_in_page = []
            
            # On affiche chaque colonne
            col_container.write("#### Segments en mode colonne")
            col_container.markdown('<div class="column-container">', unsafe_allow_html=True)
            
            for col_index, col_data in enumerate(columns_data):
                col_container.markdown('<div class="column">', unsafe_allow_html=True)
                col_container.write(f"**Colonne {col_index+1}**")
                local_validated = []
                
                for seg_idx, res in enumerate(col_data):
                    box_coords = res[0]
                    text_ocr  = res[1]
                    conf      = res[2]
                    midX      = res[4]
                    
                    # Nettoyage
                    cleaned = sanitize_number(text_ocr)
                    
                    # Affichage
                    col_container.markdown(f"<div class='segment-box'><strong>OCR brut :</strong> {text_ocr}<br/><strong>Proposition nettoyée :</strong> {cleaned}<br/>Confiance : {conf*100:.0f}%</div>", unsafe_allow_html=True)
                    
                    # Correction rapide
                    corrected = col_container.text_input("Corriger si besoin :", value=cleaned, key=f"correct_{idx_file}_{col_index}_{seg_idx}")
                    
                    # Bouton pour afficher code-barres
                    show_code = col_container.button(f"Afficher code-barres (Col {col_index+1}, seg {seg_idx+1})", key=f"show_{idx_file}_{col_index}_{seg_idx}")
                    if show_code:
                        code_buf = generate_barcode_pybarcode(corrected)
                        col_container.image(code_buf, caption=f"Code-barres : {corrected}", use_container_width=True)
                    
                    # Bouton pour confirmer
                    confirm = col_container.button(f"Confirmer (Col {col_index+1}, seg {seg_idx+1})", key=f"conf_{idx_file}_{col_index}_{seg_idx}")
                    if confirm:
                        final_seg = sanitize_number(corrected)
                        col_container.markdown(f"<div class='validated'>Segment validé : {final_seg}</div>", unsafe_allow_html=True)
                        local_validated.append(final_seg)
                    else:
                        col_container.markdown("<div class='nonvalidated'>En attente de validation</div>", unsafe_allow_html=True)
                
                # On stocke localement
                validated_in_page.extend(local_validated)
                col_container.markdown('</div>', unsafe_allow_html=True)  # fin de la div colonne
            
            col_container.markdown('</div>', unsafe_allow_html=True)  # fin du container de colonnes
            
            # Bouton pour valider la page
            if st.button(f"Valider la page {idx_file+1}", key=f"validatepage_{idx_file}"):
                if len(validated_in_page) < sum(len(c) for c in columns_data):
                    st.error("Tous les segments ne sont pas validés.")
                else:
                    st.success(f"Page {idx_file+1} validée avec {len(validated_in_page)} segments.")
                    global_validated_segments.extend(validated_in_page)
    
    # Génération PDF final
    if global_validated_segments and st.button("Générer PDF global"):
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(0, margin=10)
            temp_dir = tempfile.gettempdir()
            for seg in global_validated_segments:
                buf = generate_barcode_pybarcode(seg)
                fname = os.path.join(temp_dir, f"barcode_{seg}.png")
                with open(fname, "wb") as f:
                    f.write(buf.getvalue())
                pdf.add_page()
                pdf.image(fname, x=10, y=10, w=pdf.w - 20)
            pdf_path = os.path.join(temp_dir, "barcodes.pdf")
            pdf.output(pdf_path, "F")
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            st.download_button("Télécharger le PDF complet", data=pdf_data, file_name="barcodes.pdf", mime="application/pdf")
        except Exception as e:
            st.error(f"Erreur lors de la génération du PDF : {str(e)}")

