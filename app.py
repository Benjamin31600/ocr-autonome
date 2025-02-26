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
st.write("Téléchargez une image de bordereau. Le système extrait les fragments de texte via OCR, identifie les libellés (ex. 'Part Number', 'Serial Number') et recherche la valeur associée située en dessous ou à côté. Vous pouvez ensuite valider ou rejeter chaque extraction.")

# -----------------------------------------------------------
# Base de données SQLite pour enregistrer le feedback utilisateur
# -----------------------------------------------------------
conn = sqlite3.connect("feedback.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image BLOB,
        ocr_text TEXT,
        validated_fields TEXT,
        rejected_fields TEXT
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
# Fonction pour générer un code‑barres pour un champ donné
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
# Fonction pour calculer les métriques d'une bounding box
# -----------------------------------------------------------
def get_bbox_metrics(bbox):
    # bbox est une liste de 4 points [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    top = min(ys)
    bottom = max(ys)
    left = min(xs)
    right = max(xs)
    center_x = (left + right) / 2
    return top, bottom, left, right, center_x

# -----------------------------------------------------------
# Téléversement de l'image du bordereau
# -----------------------------------------------------------
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau de réception", use_container_width=True)
    
    # -----------------------------------------------------------
    # Extraction OCR
    # -----------------------------------------------------------
    with st.spinner("Extraction du texte via OCR..."):
        ocr_results = ocr_reader.readtext(uploaded_file.getvalue())
    candidate_fields = []
    for result in ocr_results:
        bbox, text, conf = result
        candidate_fields.append({"bbox": bbox, "text": text})
    
    # Calculer les métriques de chaque bounding box
    for cand in candidate_fields:
        top, bottom, left, right, center_x = get_bbox_metrics(cand["bbox"])
        cand["top"] = top
        cand["bottom"] = bottom
        cand["left"] = left
        cand["right"] = right
        cand["center_x"] = center_x

    # -----------------------------------------------------------
    # Extraire les paires "libellé" / "valeur"
    # -----------------------------------------------------------
    header_pattern = re.compile(r"(part\s*number|serial\s*(number|no)|n°\s*de\s*série|serie)", re.IGNORECASE)
    extracted_fields = []
    # Pour chaque fragment qui correspond à un header, chercher la valeur associée
    for i, cand in enumerate(candidate_fields):
        if header_pattern.search(cand["text"]):
            header = cand
            header_bottom = header["bottom"]
            header_center = header["center_x"]
            # Chercher le fragment avec le top le plus proche du header et aligné horizontalement
            candidate_value = None
            min_distance = float("inf")
            for j, other in enumerate(candidate_fields):
                if j == i:
                    continue
                # On cherche uniquement les fragments situés en dessous du header
                if other["top"] >= header_bottom:
                    # Vérifier l'alignement horizontal (marge de 100 pixels)
                    if abs(other["center_x"] - header_center) < 100:
                        distance = other["top"] - header_bottom
                        if distance < min_distance:
                            min_distance = distance
                            candidate_value = other["text"].strip()
            if candidate_value:
                extracted_fields.append(candidate_value)
    
    # -----------------------------------------------------------
    # Si aucun header n'est trouvé, on utilise une alternative : extraire tous les fragments contenant des chiffres
    # -----------------------------------------------------------
    if not extracted_fields:
        for cand in candidate_fields:
            if re.search(r"\d", cand["text"]):
                extracted_fields.append(cand["text"].strip())
    
    # -----------------------------------------------------------
    # Validation par l'utilisateur
    # -----------------------------------------------------------
    if extracted_fields:
        st.subheader("Champs extraits et Codes‑barres associés")
        validated_fields = []
        rejected_fields = []
        for idx, field in enumerate(extracted_fields):
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                user_field = st.text_input(f"Champ {idx+1}", value=field, key=f"field_{idx}")
            with col2:
                try:
                    barcode_buffer = generate_barcode(user_field)
                    st.image(barcode_buffer, caption=f"Code‑barres pour {user_field}", use_container_width=True)
                except Exception as e:
                    st.error(f"Erreur pour {user_field} : {str(e)}")
            with col3:
                status = st.radio("Statut", options=["Valider", "Rejeter", "Neutre"], key=f"status_{idx}")
            if status == "Valider":
                validated_fields.append(user_field)
            elif status == "Rejeter":
                rejected_fields.append(user_field)
        
        # -----------------------------------------------------------
        # Enregistrement du feedback utilisateur
        # -----------------------------------------------------------
        if st.button("Enregistrer le feedback"):
            image_bytes = uploaded_file.getvalue()
            full_ocr_text = " ".join([r["text"] for r in candidate_fields])
            # On enregistre les champs validés et rejetés
            c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                      (image_bytes, full_ocr_text, " | ".join(validated_fields)))
            c.execute("INSERT INTO feedback (image, ocr_text, validated_fields) VALUES (?, ?, ?)",
                      (image_bytes, full_ocr_text, " | ".join(rejected_fields)))
            conn.commit()
            st.success("Feedback enregistré !")
    else:
        st.warning("Aucun champ pertinent n'a été extrait.")


