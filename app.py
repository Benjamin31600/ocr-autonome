import streamlit as st
import easyocr
import re
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import io
import sqlite3

# --- Injection de CSS ultra moderne pour une interface SaaS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
    body {
        background: linear-gradient(135deg, #e0eafc, #cfdef3);
        font-family: 'Roboto', sans-serif;
    }
    .stApp {
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
    .stTextArea textarea {
        border-radius: 8px;
        padding: 10px;
        font-size: 16px;
        border: 1px solid #ccc;
    }
    .barcode-img {
        margin-top: 10px;
        border: 1px solid #eee;
        padding: 10px;
        border-radius: 8px;
        background: #fff;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Titre et description (en français) ---
st.title("Daher Aerospace – Réception & Traitement des Numéros")
st.write("Prenez en photo le bordereau de réception. L'application extrait le texte, identifie les numéros de série et les numéros de pièces, et génère leurs codes-barres. Le système s'améliore au fil des retours utilisateurs.")

# --- Connexion à la base de données SQLite pour le feedback ---
co
