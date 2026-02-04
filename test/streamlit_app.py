import streamlit as st
import requests
import uuid
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(
    page_title="ZOA Agents Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
API_URL = "http://localhost:8080"
DEFAULT_USER_ID = "+34777666999"
DEFAULT_COMPANY_ID = "606338959237848"
DEFAULT_USER_NAME = "Juan Pérez"

# --- SESSION STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Configuración")
    
    st.subheader("Datos de Sesión")
    user_id = st.text_input("User Phone (wa_id)", value=DEFAULT_USER_ID)
    user_name = st.text_input("User Name", value=DEFAULT_USER_NAME)
    company_id = st.text_input("Company ID", value=DEFAULT_COMPANY_ID)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Limpiar Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
            
    with col2:
        if st.button("🔄 Reset Memory", type="primary", use_container_width=True, help="Envía 'BORRAR TODO' para reiniciar la base de datos"):
            # Send reset command to backend
            try:
                payload = {
                    "wa_id": user_id,
                    "mensaje": "BORRAR TODO",
                    "phone_number_id": company_id,
                    "name": user_name,
                }
                requests.post(API_URL, json=payload)
                st.session_state.messages = []
                st.success("Memoria reiniciada")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.info(f"API Endpoint: `{API_URL}`")

# --- MAIN CHAT INTERFACE ---
st.title("💬 ZOA Agents Interface")
st.caption(f"Conversando como: **{user_name}** ({user_id})")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        if "agent" in message:
            st.caption(f"🤖 {message['agent']}")
        st.markdown(message["content"])

# Chat Input
if prompt := st.chat_input("Escribe tu mensaje aquí..."):
    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "👤"})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # 2. Call API
    payload = {
        "wa_id": user_id,
        "mensaje": prompt,
        "phone_number_id": company_id,
        "name": user_name,
    }

    try:
        with st.spinner("Pensando..."):
            response = requests.post(API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Handle Session Reset response
            if data.get("action") == "session_reset":
                st.warning("⚠️ La sesión ha sido reiniciada por el sistema.")
                st.stop()

            # Parse Agent Response
            agent_response = data.get("response", {})
            
            # Default values
            agent_name = "unknown"
            message_text = "No response"
            
            if isinstance(agent_response, dict):
                agent_name = agent_response.get("agent") or agent_response.get("next_agent") or "System"
                message_text = agent_response.get("message", "")
                
                # Check for completion
                if agent_response.get("status") == "completed":
                    message_text += "\n\n*🔒 Conversación finalizada*"
            else:
                message_text = str(agent_response)

        # 3. Display Assistant Message
        st.session_state.messages.append({
            "role": "assistant", 
            "content": message_text, 
            "agent": agent_name,
            "avatar": "🤖"
        })
        
        with st.chat_message("assistant", avatar="🤖"):
            st.caption(f"🤖 {agent_name}")
            st.markdown(message_text)

    except requests.exceptions.ConnectionError:
        st.error("❌ No se pudo conectar a la API. Asegúrate de que Docker esté corriendo.")
    except Exception as e:
        st.error(f"❌ Error: {e}")
