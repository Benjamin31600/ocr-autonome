import streamlit as st
import easyocr
from PIL import Image
import sqlite3
import pickle
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences

# --- Chargement du modèle de correction et des tokenizers ---
try:
    correction_model = load_model("correction_model.h5")
    with open("tokenizer_in.pkl", "rb") as f:
        tokenizer_in = pickle.load(f)
    with open("tokenizer_out.pkl", "rb") as f:
        tokenizer_out = pickle.load(f)
    model_loaded = True
except Exception as e:
    st.warning("Modèle de correction non disponible. Utilisation du texte OCR brut.")
    model_loaded = False

# --- Initialisation de la base de données SQLite ---
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

st.title("Application OCR avec apprentissage autonome")
st.write("Téléchargez une image. Le système extrait le texte, propose une correction automatique et vous permet d’ajuster le résultat.")

uploaded_file = st.file_uploader("Choisissez une image (png, jpg, jpeg)", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Image téléchargée", use_column_width=True)
    
    st.write("Traitement de l'image en cours...")
    
    reader = easyocr.Reader(['fr'])
    results = reader.readtext(uploaded_file.getvalue())
    detected_text = " ".join([text for (_, text, _) in results])
    
    st.write("Texte détecté (OCR) :")
    st.write(detected_text)
    
    corrected_generated = ""
    if model_loaded:
        # Convertir le texte OCR en séquence
        seq = tokenizer_in.texts_to_sequences([detected_text])
        seq = pad_sequences(seq, maxlen=50, padding='post')  # maxlen fixé pour cet exemple
        
        # On initialise le décodeur avec le token de début (ici '\t' est utilisé)
        start_token_index = tokenizer_out.word_index.get('\t', 1)
        decoder_input = [[start_token_index]]
        
        # On définit le token de fin (ici '\n')
        stop_token_index = tokenizer_out.word_index.get('\n', 0)
        max_decoder_seq_length = 50
        
        for i in range(max_decoder_seq_length):
            decoder_seq = pad_sequences(decoder_input, maxlen=max_decoder_seq_length, padding='post')
            output_tokens = correction_model.predict([seq, decoder_seq])
            sampled_token_index = output_tokens[0, i, :].argmax()
            if sampled_token_index == stop_token_index:
                break
            # Trouver le mot correspondant à l'index
            sampled_word = [word for word, index in tokenizer_out.word_index.items() if index == sampled_token_index]
            sampled_word = sampled_word[0] if sampled_word else ""
            corrected_generated += " " + sampled_word
            decoder_input[0].append(sampled_token_index)
    
    st.write("Texte après correction automatique :")
    st.write(corrected_generated.strip() if model_loaded else detected_text)
    
    # Zone pour ajuster le texte final
    final_text = st.text_area("Modifiez le texte si nécessaire", value=(corrected_generated.strip() if model_loaded else detected_text))
    
    if st.button("Envoyer les corrections"):
        image_bytes = uploaded_file.getvalue()
        c.execute("INSERT INTO feedback (image, ocr_text, corrected_text) VALUES (?, ?, ?)",
                  (image_bytes, detected_text, final_text))
        conn.commit()
        st.success("Merci pour votre retour !")
