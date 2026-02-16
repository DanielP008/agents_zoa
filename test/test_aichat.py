import streamlit as st
import requests
import uuid
import json
import os
import time
from dotenv import load_dotenv
from datetime import datetime

# Load env variables
load_dotenv()

# --- CONFIGURATION ---
st.set_page_config(
    page_title="ZOA AiChat Test",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
API_URL = "http://localhost:8080" # Local
DEFAULT_USER_ID = "aichat_test_user"
DEFAULT_COMPANY_ID = "521783407682043"
DEFAULT_USER_NAME = "Web User"

# --- SESSION STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Configuración AiChat")
    
    st.subheader("Datos de Sesión")
    user_id = st.text_input("User ID (wa_id)", value=DEFAULT_USER_ID)
    user_name = st.text_input("User Name", value=DEFAULT_USER_NAME)
    company_id = st.text_input("Company ID", value=DEFAULT_COMPANY_ID)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Limpiar Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
            
    with col2:
        if st.button("🔄 Reset Memory", type="primary", use_container_width=True, help="Reinicia la sesión en la base de datos"):
            try:
                payload = {
                    "wa_id": user_id,
                    "mensaje": "BORRAR TODO",
                    "phone_number_id": company_id,
                    "source": "ai-chat"
                }
                requests.post(API_URL, json=payload)
                st.session_state.messages = []
                st.success("Memoria reiniciada")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.info(f"API Endpoint: `{API_URL}`")
    st.caption("Este test simula el canal **ai-chat**.")

# --- MAIN CHAT INTERFACE ---
st.title("💬 ZOA AiChat Interface")
st.caption(f"Conversando como: **{user_name}** ({user_id})")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        if "agent" in message:
            st.caption(f"🤖 {message['agent']}")
        if "latency_ms" in message:
            latency_ms = float(message["latency_ms"])
            st.caption(f"⏱️ Total: {latency_ms/1000:.2f}s ({latency_ms:.0f}ms)")
        st.markdown(message["content"])

# Chat Input
if prompt := st.chat_input("Escribe tu mensaje de chat aquí..."):
    # 1. Prepare Payload for AiChat
    payload = {
        "wa_id": user_id,
        "mensaje": prompt,
        "phone_number_id": company_id,
        "name": user_name,
        "source": "ai-chat" # Crucial for routing to aichat_handler
    }

    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "👤"})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # 2. Call API
    try:
        with st.spinner("Sofía está pensando..."):
            request_start = time.perf_counter()
            response = requests.post(API_URL, json=payload)
            request_elapsed_ms = (time.perf_counter() - request_start) * 1000
            response.raise_for_status()
            data = response.json()
            
            # Handle Session Reset response
            if data.get("action") == "session_reset":
                st.warning("⚠️ La sesión ha sido reiniciada por el sistema.")
                st.stop()

            # Parse Agent Response
            # The aichat_handler returns {"status": "ok", "response": orchestrator_response, ...}
            agent_response = data.get("response", {})
            
            # Default values
            agent_name = "unknown"
            message_text = "No response"
            
            if isinstance(agent_response, dict):
                agent_name = agent_response.get("agent") or agent_response.get("next_agent") or "Sofía (AiChat)"
                message_text = agent_response.get("message", "")
                
                # Check for completion
                if agent_response.get("status") == "completed":
                    message_text += "\n\n*🔒 Conversación finalizada*"
            else:
                agent_name = "Sofía (AiChat)"
                message_text = str(agent_response)

        # 3. Display Assistant Message
        st.session_state.messages.append({
            "role": "assistant", 
            "content": message_text, 
            "agent": agent_name,
            "latency_ms": request_elapsed_ms,
            "avatar": "🤖"
        })
        
        with st.chat_message("assistant", avatar="🤖"):
            st.caption(f"🤖 {agent_name}")
            st.caption(f"⏱️ Total: {request_elapsed_ms/1000:.2f}s ({request_elapsed_ms:.0f}ms)")
            st.markdown(message_text)

    except requests.exceptions.ConnectionError:
        st.error("❌ No se pudo conectar a la API. Asegúrate de que el servidor esté corriendo en el puerto 8080.")
    except Exception as e:
        st.error(f"❌ Error: {e}")
