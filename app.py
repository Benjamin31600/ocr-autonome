import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# --- Injection de CSS ultra moderne avec hero section et style marketing ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
    
    /* Background plein écran avec image et overlay */
    body {
        background: url('https://source.unsplash.com/1600x900/?technology,office') no-repeat center center fixed;
        background-size: cover;
        font-family: 'Roboto', sans-serif;
    }
    /* Overlay sur le container principal */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, rgba(224,234,252,0.9), rgba(207,222,243,0.9));
    }
    /* Hero section */
    .hero {
        text-align: center;
        padding: 120px 20px 80px;
        color: #003366;
    }
    .hero h1 {
        font-size: 3.5rem;
        margin-bottom: 20px;
        font-weight: 700;
    }
    .hero p {
        font-size: 1.5rem;
        margin-bottom: 40px;
    }
    .cta-button {
        background: linear-gradient(90deg, #003366, #002244);
        border: none;
        border-radius: 30px;
        padding: 15px 40px;
        font-size: 1.2rem;
        color: #fff;
        cursor: pointer;
        transition: background 0.3s ease;
    }
    .cta-button:hover {
        background: linear-gradient(90deg, #002244, #001122);
    }
    /* Style pour les cartes d'affichage */
    .card {
        background-color: #ffffff;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        padding: 20px;
        margin: 20px auto;
        max-width: 800px;
    }
    /* Style des boutons Streamlit natifs */
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
    </style>
    """, unsafe_allow_html=True)

# --- Hero Section Ultra Marketing ---
st.markdown("""
    <div class="hero">
        <h1>Daher Aerospace</h1>
        <p>Réception & Traitement Intelligent des Numéros<br>Extrait, identifie et génère automatiquement vos codes-barres.</p>
        <button class="cta-button" onclick="window.scrollTo(0, document.body.scrollHeight)">Commencer</button>
    </div>
    """, unsafe_allow_html=True)

# --- Zone de contenu principale dans une "carte" moderne ---
st.markdown('<div class="card">', unsafe_allow_html=True)

st.subheader("Téléversez votre bordereau de réception")
st.write("Prenez en photo ou téléchargez une image de votre bordereau. L'application extrait le texte et identifie les numéros de série et de pièces (avec ou sans espaces, quelle que soit leur position, en français ou en anglais).")

# --- Connexion à la base de données SQLite pour le feedback ---
conn = sqlite3.connect("feedback.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image BLOB,
        ocr_text TEXT,
        corrected_text TEXT
    )
''')
conn.commit()

# --- Optimisations : Mise en cache du modèle OCR et génération de codes-barres ---
@st.cache(allow_output_mutation=True)
def load_ocr_model():
    return easyocr.Reader(['fr', 'en'])

@st.cache(show_spinner=False)
def perform_ocr(image_bytes):
    reader = load_ocr_model()
    return reader.readtext(image_bytes)

@st.cache(show_spinner=False)
def generate_barcode(sn):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_img = CODE128(sn, writer=ImageWriter())
    buffer = io.BytesIO()
    barcode_img.write(buffer)
    buffer.seek(0)
    return buffer

# --- Téléversement de l'image ---
uploaded_file = st.file_uploader("Téléchargez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    # Redimensionnement de l'image pour accélérer l'OCR
    image = Image.open(uploaded_file)
    image.thumbnail((1024, 1024))
    st.image(image, caption="Bordereau de réception", use_column_width=True)
    
    with st.spinner("Extraction du texte..."):
        results = perform_ocr(uploaded_file.getvalue())
    detected_text = " ".join([text for (_, text, _) in results])
    
    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("Texte détecté")
    st.write(detected_text)
    
    # --- Extraction ciblée des numéros (séries & pièces) ---
    pattern = re.compile(
        r'(?:(?:num(?:éro)?s?\s*de\s*(?:s[ée]rie(?:s)?|series))'
        r'|(?:n°\s*de\s*(?:s[ée]rie(?:s)?|series))'
        r'|(?:serial\s*(?:number|no\.?))'
        r'|(?:part\s*(?:number|no\.?))'
        r'|(?:pi[eè]ce(?:s)?\s*serialis[eé]e?s?))'
        r'\s*[:\-]?\s*'
        r'((?:[A-Za-z0-9]+\s?)+)',
        re.IGNORECASE
    )
    
    matches = pattern.findall(detected_text)
    
    if matches:
        st.subheader("Numéros extraits et Codes-barres")
        serial_numbers = [match.strip() for match in matches]  # Conserve les espaces internes
        serial_numbers = list(dict.fromkeys(serial_numbers))  # Élimine les doublons
        
        for sn in serial_numbers:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"**{sn}**")
            with col2:
                try:
                    buffer = generate_barcode(sn)
                    st.image(buffer, caption=f"Code-barres pour {sn}", use_column_width=True)
                except Exception as e:
                    st.error(f"Erreur lors de la génération du code-barres pour {sn} : {str(e)}")
    else:
        st.warning("Aucun numéro détecté. Vérifiez que le bordereau contient des libellés tels que 'numéro de série', 'n° de série', 'serial number', 'part number', ou 'pièce serialisée'.")
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # --- Zone de feedback pour l'auto-amélioration ---
    st.subheader("Ajustez le texte extrait si nécessaire")
    final_text = st.text_area("Modifiez le texte ci-dessous", value=detected_text)
    
    if st.button("Envoyer le feedback"):
        image_bytes = uploaded_file.getvalue()
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_text) VALUES (?, ?, ?)",
                  (image_bytes, detected_text, final_text))
        conn.commit()
        st.success("Merci ! Votre feedback contribuera à l'amélioration continue du système.")

st.markdown("</div>", unsafe_allow_html=True)

     
    
