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
import math

############################################
# 1) FONCTIONS DE NETTOYAGE & OCR
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
    num = re.sub(r'(SER|S\s*/\s*N)[\s:,\.\-]*', '', num)
    # Retire tous les caractères qui ne sont pas lettres ou chiffres
    num = re.sub(r'[^0-9A-Z]', '', num)
    return num

def generate_barcode_pybarcode(sn: str) -> io.BytesIO:
    """Génère un code‑barres Code128 pour la chaîne sn."""
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_obj.write(buffer)
    buffer.seek(0)
    return buffer

@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr','en'])

############################################
# 2) FONCTION DE GROUPAGE PAR LIGNE
############################################

def group_by_lines(ocr_results, y_threshold=10):
    """
    Regroupe les segments OCR (bbox, texte, conf) par lignes,
    en se basant sur la coordonnée Y du coin supérieur gauche.
    y_threshold : tolérance verticale pour considérer 2 segments sur la même ligne.
    Retourne une liste de lignes, où chaque ligne est une liste de (texte, conf).
    """
    # On trie d'abord par la coordonnée Y du coin supérieur gauche
    # ocr_results[i] = [ [x0,y0], [x1,y1], [x2,y2], [x3,y3], text, conf ]
    # On récupère y0 minimal
    items = []
    for res in ocr_results:
        bbox = res[0]
        text = res[1]
        conf = res[2]
        y_min = min(bbox[0][1], bbox[1][1], bbox[2][1], bbox[3][1])
        items.append((y_min, text, conf))
    items.sort(key=lambda x: x[0])  # tri par y_min

    lines = []
    current_line = []
    current_y = None

    for (y, text, conf) in items:
        if current_y is None:
            current_line.append((text, conf))
            current_y = y
        else:
            if abs(y - current_y) <= y_threshold:
                # même ligne
                current_line.append((text, conf))
            else:
                # nouvelle ligne
                lines.append(current_line)
                current_line = [(text, conf)]
            current_y = y
    if current_line:
        lines.append(current_line)
    return lines

############################################
# 3) INTERFACE STREAMLIT
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
        border-radius: 20px;
        padding: 2rem 3rem;
        max-width: 1400px;
        margin: 2rem auto;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    .line-box {
        background-color: rgba(255,255,255,0.1);
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 10px;
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
    </style>
""", unsafe_allow_html=True)

st.title("Daher Aerospace – OCR & Code‑barres Ultra Sécurisé")
st.write("""
Téléversez vos pages. L'application :
- Corrige l'orientation EXIF.
- Permet de sélectionner la zone d'intérêt (cadre rouge).
- Détecte les lignes via bounding boxes (pour plus de cohérence en colonne).
- Nettoie automatiquement (supprime "SER", "S/N", espaces, tirets, caractères spéciaux).
- Permet la correction rapide, la visualisation individuelle de code-barres, et la validation ligne par ligne.
- Génère un PDF final avec tous les numéros confirmés.
""")

ocr_reader = load_ocr_model()

uploaded_files = st.file_uploader("Téléchargez vos pages (PNG, JPG, JPEG)", 
                                  type=["png","jpg","jpeg"],
                                  accept_multiple_files=True)

all_validated_serials = []

if uploaded_files:
    overall_start = time.time()
    st.write("## Traitement des pages")
    
    for idx_file, file in enumerate(uploaded_files):
        with st.expander(f"Page {idx_file+1}", expanded=True):
            page_start = time.time()
            
            image = Image.open(file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("### Sélection de la zone d'intérêt")
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"crop_{idx_file}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction OCR..."):
                results = ocr_reader.readtext(cropped_bytes)
            
            # Groupement par lignes
            lines = group_by_lines(results, y_threshold=15)
            
            st.write(f"### Lignes détectées ({len(lines)} lignes)")
            page_validated = []
            
            for line_idx, line_items in enumerate(lines):
                # line_items est une liste de (text, conf)
                # On concatène tous les textes pour affichage
                raw_line = " ".join([x[0] for x in line_items])
                st.markdown(f"<div class='line-box'><strong>Ligne {line_idx+1} :</strong> {raw_line}</div>", unsafe_allow_html=True)
                
                # Proposer un champ unique pour correction
                corrected_line = st.text_input("Corriger / Séparer si besoin :", value=raw_line, key=f"line_{idx_file}_{line_idx}")
                
                # Bouton "Analyser la ligne"
                if st.button(f"Analyser la ligne {line_idx+1}", key=f"analyze_{idx_file}_{line_idx}"):
                    # On découpe la ligne corrigée par espaces ou virgules
                    splitted = re.split(r'[\s,;]+', corrected_line)
                    splitted_clean = [sanitize_number(s) for s in splitted if s.strip()]
                    
                    st.write("**Segments détectés :**", splitted_clean)
                    
                    # Permettre la validation segment par segment
                    local_valids = []
                    for seg_i, seg_val in enumerate(splitted_clean):
                        st.write(f"Segment {seg_i+1} : {seg_val}")
                        # Bouton pour afficher code-barres
                        if st.button(f"Afficher code-barres (ligne {line_idx+1}, segment {seg_i+1})", key=f"showbarcode_{idx_file}_{line_idx}_{seg_i}"):
                            code_buf = generate_barcode_pybarcode(seg_val)
                            st.image(code_buf, caption=f"Code-barres : {seg_val}", use_container_width=True)
                        # Validation segment
                        if st.checkbox(f"Valider segment {seg_i+1}", key=f"check_{idx_file}_{line_idx}_{seg_i}"):
                            local_valids.append(seg_val)
                    
                    # Bouton "Valider la ligne"
                    if st.button(f"Valider la ligne {line_idx+1}", key=f"validline_{idx_file}_{line_idx}"):
                        if len(local_valids) == len(splitted_clean):
                            st.success(f"Ligne {line_idx+1} validée !")
                            page_validated.extend(local_valids)
                        else:
                            st.error("Tous les segments de la ligne doivent être validés !")
            
            # Bouton "Valider la page"
            if st.button(f"Valider la page {idx_file+1}", key=f"page_{idx_file}"):
                if page_validated:
                    st.success(f"Page {idx_file+1} validée avec {len(page_validated)} numéros confirmés.")
                    all_validated_serials.extend(page_validated)
                else:
                    st.warning("Aucun numéro validé pour cette page !")
            
            page_end = time.time()
            st.write(f"Temps de traitement de la page {idx_file+1} : {page_end - page_start:.2f} s")
    
    # Génération PDF final
    if all_validated_serials and st.button("Générer PDF Global"):
        with st.spinner("Génération du PDF..."):
            try:
                pdf = FPDF()
                pdf.set_auto_page_break(0, margin=10)
                temp_dir = tempfile.gettempdir()
                for seg in all_validated_serials:
                    code_buf = generate_barcode_pybarcode(seg)
                    fname = os.path.join(temp_dir, f"barcode_{seg}.png")
                    with open(fname, "wb") as f:
                        f.write(code_buf.getvalue())
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
        st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} s")

