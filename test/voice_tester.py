import streamlit as st
import requests
import os
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
st.set_page_config(
    page_title="ZOA Voice Tester",
    page_icon="🔊",
    layout="centered"
)

# ElevenLabs Configuration
ELVNLABS_API_KEY = os.getenv("ELVNLABS_API_KEY")
VOICE_ID = "ERYLdjEaddaiN9sDjaMX"  # Gabriela Sainz - Bright and Professional
MODEL_ID = "eleven_multilingual_v2"

def text_to_speech(text, speed=1.0, stability=50, similarity=75, style=0, seed=None):
    """
    Converts text to audio bytes using ElevenLabs API (Gabriela voice).
    Returns (audio bytes, seed) on success, (None, None) on failure.
    """
    if not ELVNLABS_API_KEY:
        return None, None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELVNLABS_API_KEY
    }

    # If no seed is provided, generate a random one ourselves
    # This ensures we always know which seed was used even if the API doesn't return it
    if seed is None or seed == 0:
        seed = random.randint(1, 4294967295)

    data = {
        "text": text,
        "model_id": MODEL_ID,
        "seed": seed,
        "voice_settings": {
            "stability": stability / 100,
            "similarity_boost": similarity / 100,
            "style": style / 100,
            "use_speaker_boost": True,
            "speed": speed
        }
    }

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        print(seed) # Print only the seed to terminal
        return response.content, seed
    else:
        st.error(f"API Error ({response.status_code}): {response.text}")
        return None, None

# --- SIDEBAR: Voice Settings ---
with st.sidebar:
    st.title("🎙️ Configuración de Voz")
    st.caption("Gabriela Sainz - Bright and Professional")

    st.divider()

    voice_speed = st.slider("Velocidad", 0.70, 1.20, 1.00, 0.05)
    voice_stability = st.slider("Estabilidad (%)", 0, 100, 40)
    voice_similarity = st.slider("Similitud (%)", 0, 100, 90)
    voice_style = st.slider("Exageración de estilo (%)", 0, 100, 0)
    
    st.divider()
    manual_seed = st.number_input("Seed Manual (0 para aleatorio)", min_value=0, value=2606200870)

    if not ELVNLABS_API_KEY:
        st.warning("⚠️ ELVNLABS_API_KEY no encontrada en .env")

# --- MAIN INTERFACE ---
st.title("🔊 ZOA Voice Tester")
st.caption("Escribe cualquier texto y escúchalo con la voz de Gabriela")

# Text input
text_input = st.text_area(
    "Texto a convertir en voz",
    placeholder="Escribe aquí el texto que quieres escuchar...",
    height=150
)

# Generate button
if st.button("🎤 Generar Audio", type="primary", use_container_width=True, disabled=not text_input):
    with st.spinner("🔊 Generando voz..."):
        audio_bytes, seed = text_to_speech(
            text=text_input,
            speed=voice_speed,
            stability=voice_stability,
            similarity=voice_similarity,
            style=voice_style,
            seed=manual_seed if manual_seed > 0 else None
        )

    if audio_bytes:
        st.audio(audio_bytes, format="audio/mpeg", autoplay=True)
        st.success(f"Audio generado correctamente ({len(audio_bytes) / 1024:.1f} KB)")
        if seed:
            st.code(f"Seed: {seed}", language="text")
            st.info("💡 Anota este Seed si te gusta el resultado para usarlo siempre.")
    else:
        st.error("No se pudo generar el audio.")
