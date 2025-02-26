import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# -----------------------------------------------------------
# CSS & Style : Interface moderne et marketing
# -----------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
    body {
        background: linear-gradient(135deg, #e0eafc, #cfdef3);
        font-family: 'Roboto', sans-serif;
    }
    [data-testid="stAppViewContainer"] {
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
        transition: background-color 0.3s ease;
    }
    .stButton button:hover {
        background-color: #002244;
    }
    .stTextInput input {
        border-radius: 8px;
        padding: 10px;
        font-size: 16px;
        border: 1px solid #ccc;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("Daher Aerospace – Extraction et Validation des Champs")
st.write("Téléchargez une image de bordereau. Le système extrait les fragments de texte et tente de repérer les libellés (ex. 'Part Number', 'Serial Number'). Pour chaque libellé, il recherche ensuite la valeur associée (le numéro) qui se trouve généralement en dessous ou à côté. Vous pourrez ensuite valider ou corriger ces extractions.")

# -----------------------------------------------------------
# Base de données SQLite pour enregistrer le feedback
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
# Chargement d'EasyOCR
# -----------------------------------------------------------
@st.cache_resource
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])
ocr_reader = load_ocr_model()

# -----------------------------------------------------------
# Fonction pour générer un code‑barres
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
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau de réception", use_container_width=True)
    
    # -----------------------------------------------------------
    # Extraction OCR avec EasyOCR
    # -----------------------------------------------------------
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(uploaded_file.getvalue())
    candidate_fields = []
    for result in ocr_results:
        bbox, text, conf = result
        candidate_fields.append({"bbox": bbox, "text": text})
    
    # -----------------------------------------------------------
    # Calcul de positions pour chaque fragment
    # -----------------------------------------------------------
    def get_bbox_metrics(bbox):
        # bbox est une liste de 4 points: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        top_y = min(ys)
        bottom_y = max(ys)
        center_x = sum(xs) / 4
        return top_y, bottom_y, center_x

    for cand in candidate_fields:
        top_y, bottom_y, center_x = get_bbox_metrics(cand["bbox"])
        cand["top_y"] = top_y
        cand["bottom_y"] = bottom_y
        cand["center_x"] = center_x

    # -----------------------------------------------------------
    # Extraction des paires "libellé" et "valeur"
    # -----------------------------------------------------------
    header_pattern = re.compile(r"(part\s*number|serial\s*(number|no)|n°\s*de\s*série|serie)", re.IGNORECASE)
    extracted_fields = []
    # Pour chaque fragment qui ressemble à un header, on cherche une valeur en dessous ou à côté.
    for i, cand in enumerate(candidate_fields):
        txt = cand["text"]
        if header_pattern.search(txt):
            # Si le header contient déjà un ":", on suppose que la valeur est sur la même ligne.
            if ":" in txt:
                parts = txt.split(":")
                header = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""
                if value:
                    extracted_fields.append(value)
                    continue
            # Sinon, on cherche le fragment suivant dont le top_y est proche du bottom_y du header 
            # et dont le center_x est proche (dans une marge de 50 pixels)
            header_bottom = cand["bottom_y"]
            header_center = cand["center_x"]
            candidate_value = None
            min_distance = float("inf")
            for j, other in enumerate(candidate_fields):
                if j == i:
                    continue
                # Considérer uniquement les fragments situés en dessous du header
                if other["top_y"] > header_bottom:
                    # Vérifier l'alignement horizontal
                    if abs(other["center_x"] - header_center) < 50:
                        distance = other["top_y"] - header_bottom
                        if distance < min_distance:
                            min_distance = distance
                            candidate_value = other["text"].strip()
            if candidate_value:
                extracted_fields.append(candidate_value)
    
    # Option : si aucune extraction par header n'est trouvée, utiliser les fragments filtrés
    if not extracted_fields:
        # Filtrer les fragments qui contiennent des chiffres (pour avoir une valeur)
        for cand in candidate_fields:
            if re.search(r"\d", cand["text"]):
                extracted_fields.append(cand["text"].strip())
    
    # -----------------------------------------------------------
    # Affichage des champs extraits et génération des codes‑barres associés
    # -----------------------------------------------------------
    if extracted_fields:
        st.subheader("Champs extraits et Codes‑barres associés")
        validated_fields = []
        for idx, field in enumerate(extracted_fields):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                user_field = st.text_input(f"Champ {idx+1}", value=field, key=f"field_{idx}")
            with col2:
                try:
                    barcode_buffer = generate_barcode(user_field)
                    st.image(barcode_buffer, caption=f"Code‑barres pour {user_field}", use_container_width=True)
                except Exception as e:
                    st.error(f"Erreur pour {user_field} : {str(e)}")
            with col3:
                valid = st.checkbox("Valider", key=f"check_{idx}")
            if valid:
                validated_fields.append(user_field)
        
        # -----------------------------------------------------------
        # Enregistrement du feedback utilisateur
        # -----------------------------------------------------------
        if st.button("Enregistrer le feedback"):
            image_bytes = uploaded_file.getvalue()
            full_ocr_text = " ".join([r["text"] for r in candidate_fields])
            validated_text = " | ".join(validated_fields)
            c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                      (image_bytes, full_ocr_text, validated_text))
            conn.commit()
            st.success("Feedback enregistré !")
    else:
        st.warning("Aucun champ pertinent n'a été extrait.")

