# Téléversement multiple de pages
uploaded_files = st.file_uploader(
    "Téléchargez les pages de votre BL (png, jpg, jpeg)", 
    type=["png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

if uploaded_files:
    overall_start = time.time()
    all_validated_serials = []  # Pour conserver les numéros validés de toutes les pages
    st.write("### Traitement des pages")
    for i, uploaded_file in enumerate(uploaded_files):
        # Utilisez expanded=True pour que l'expander soit ouvert par défaut
        with st.expander(f"Page {i+1}", expanded=True):
            page_start = time.time()
            # Ouvrir l'image et corriger son orientation
            image = Image.open(uploaded_file)
            image = correct_image_orientation(image)
            image.thumbnail((1500, 1500))
            st.image(image, caption="Image originale (redimensionnée)", use_container_width=True)
            
            st.write("Sélectionnez la zone contenant les numéros (le cadre doit être rouge) :")
            # Assurez-vous d'utiliser une clé unique pour chaque st_cropper
            cropped_img = st_cropper(image, realtime_update=True, box_color="#FF0000", aspect_ratio=None, key=f"cropper_{i}")
            st.image(cropped_img, caption="Zone sélectionnée", use_container_width=True)
            
            # Convertir l'image recadrée en bytes pour l'OCR
            buf = io.BytesIO()
            cropped_img.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            
            with st.spinner("Extraction du texte via OCR..."):
                ocr_results = ocr_reader.readtext(cropped_bytes)
            extracted_text = " ".join([res[1] for res in ocr_results])
            st.markdown("**Texte extrait :**")
            st.write(extracted_text)
            
            st.subheader("Séparez les numéros (un par ligne)")
            manual_text = st.text_area("Un numéro par ligne :", value=extracted_text, height=150, key=f"manual_{i}")
            lines = [l.strip() for l in manual_text.split('\n') if l.strip()]
            
            if st.button(f"Générer les codes‑barres pour la page {i+1}", key=f"gen_{i}"):
                if lines:
                    st.write("Codes‑barres générés :")
                    cols = st.columns(3)
                    idx = 0
                    for line in lines:
                        barcode_buffer = generate_barcode(line)
                        cols[idx].image(barcode_buffer, caption=f"{line}", use_container_width=True)
                        idx = (idx + 1) % 3
                    all_validated_serials.extend(lines)
                else:
                    st.warning("Aucun numéro séparé sur cette page.")
            
            page_end = time.time()
            st.write(f"Temps de traitement de cette page : {page_end - page_start:.2f} secondes")
    
    # Suite du traitement global (PDF, enregistrement, etc.)
    # ...
    overall_end = time.time()
    st.write(f"Temps de traitement global : {overall_end - overall_start:.2f} secondes")


