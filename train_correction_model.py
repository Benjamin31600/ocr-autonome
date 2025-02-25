import pandas as pd
import numpy as np
import pickle
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, LSTM, Dense, Embedding
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences

# 1. Charger les données exportées
data = pd.read_csv("feedback_data.csv")
input_texts = data['ocr_text'].astype(str).tolist()
target_texts = data['corrected_text'].astype(str).tolist()

# Ajouter des tokens de début (\t) et de fin (\n) aux textes cibles
target_texts = ['\t' + text + '\n' for text in target_texts]

# 2. Tokenisation des textes d'entrée et de sortie
num_words = 10000
tokenizer_in = Tokenizer(num_words=num_words, filters='')
tokenizer_in.fit_on_texts(input_texts)
input_sequences = tokenizer_in.texts_to_sequences(input_texts)
max_encoder_seq_length = max(len(seq) for seq in input_sequences)
encoder_input_data = pad_sequences(input_sequences, maxlen=max_encoder_seq_length, padding='post')

tokenizer_out = Tokenizer(num_words=num_words, filters='')
tokenizer_out.fit_on_texts(target_texts)
target_sequences = tokenizer_out.texts_to_sequences(target_texts)
max_decoder_seq_length = max(len(seq) for seq in target_sequences)
decoder_input_data = pad_sequences(target_sequences, maxlen=max_decoder_seq_length, padding='post')

# Préparation des données cibles décalées
decoder_target_data = np.zeros_like(decoder_input_data)
decoder_target_data[:, :-1] = decoder_input_data[:, 1:]
decoder_target_data[:, -1] = 0

num_encoder_tokens = len(tokenizer_in.word_index) + 1
num_decoder_tokens = len(tokenizer_out.word_index) + 1

# 4. Construction du modèle seq2seq
latent_dim = 256

# Encodeur
encoder_inputs = Input(shape=(None,))
enc_emb = Embedding(input_dim=num_encoder_tokens, output_dim=latent_dim)(encoder_inputs)
encoder_lstm = LSTM(latent_dim, return_state=True)
encoder_outputs, state_h, state_c = encoder_lstm(enc_emb)
encoder_states = [state_h, state_c]

# Décodeur
decoder_inputs = Input(shape=(None,))
dec_emb_layer = Embedding(input_dim=num_decoder_tokens, output_dim=latent_dim)
dec_emb = dec_emb_layer(decoder_inputs)
decoder_lstm = LSTM(latent_dim, return_sequences=True, return_state=True)
decoder_outputs, _, _ = decoder_lstm(dec_emb, initial_state=encoder_states)
decoder_dense = Dense(num_decoder_tokens, activation='softmax')
decoder_outputs = decoder_dense(decoder_outputs)

model = Model([encoder_inputs, decoder_inputs], decoder_outputs)
model.compile(optimizer='rmsprop', loss='sparse_categorical_crossentropy')

# 5. Entraînement du modèle
model.fit([encoder_input_data, decoder_input_data],
          decoder_target_data[..., None],
          batch_size=64,
          epochs=50,
          validation_split=0.2)

# 6. Sauvegarde du modèle et des tokenizers
model.save("correction_model.h5")
with open("tokenizer_in.pkl", "wb") as f:
    pickle.dump(tokenizer_in, f)
with open("tokenizer_out.pkl", "wb") as f:
    pickle.dump(tokenizer_out, f)

print("Modèle de correction entraîné et sauvegardé.")
