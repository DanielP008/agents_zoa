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
    page_title="ZOA Agents Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
API_URL = "http://localhost:8080" # Local
DEFAULT_USER_ID = os.getenv("TEST_PHONE_NUMBER", "34000000000")
DEFAULT_COMPANY_ID = "521783407682043"
DEFAULT_USER_NAME = "Juan Arano"

import base64

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

    st.subheader("📁 Adjuntar Archivos")
    uploaded_file = st.file_uploader("Subir imagen o PDF", type=["png", "jpg", "jpeg", "pdf"])
    
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
        if "latency_ms" in message:
            latency_ms = float(message["latency_ms"])
            st.caption(f"⏱️ Total: {latency_ms/1000:.2f}s ({latency_ms:.0f}ms)")
        st.markdown(message["content"])

# Chat Input
if prompt := st.chat_input("Escribe tu mensaje aquí..."):
    # 1. Prepare Payload
    payload = {
        "wa_id": user_id,
        "mensaje": prompt,
        "phone_number_id": company_id,
        "name": user_name,
    }

    # Handle file upload
    attached_filename = None
    attached_type = None
    if uploaded_file is not None:
        uploaded_file.seek(0)  # Ensure buffer is at start
        file_bytes = uploaded_file.read()
        if file_bytes:
            base64_file = base64.b64encode(file_bytes).decode("utf-8")
            attached_filename = uploaded_file.name
            attached_type = uploaded_file.type
            payload["media"] = [{
                "mime_type": attached_type,
                "data": base64_file,
                "filename": attached_filename,
            }]

    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "👤"})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
        if attached_filename:
            st.caption(f"📎 Archivo adjunto: {attached_filename} ({attached_type})")

    # 2. Call API
    try:
        with st.spinner("Pensando..."):
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
            agent_response = data.get("response", {})
            
            # Default values
            agent_name = "unknown"
            message_text = "No response"
            
            if isinstance(agent_response, dict):
                agent_name = agent_response.get("agent") or agent_response.get("next_agent") or "System"
                
                # Extract model info if available from timing data
                model_info = ""
                try:
                    # We look for the latest trace entry for this agent to find the model
                    # This is a bit of a hack since the API doesn't return it directly in the response
                    # but we can read it from the jsonl file we just wrote
                    with open("timings/request_trace.jsonl", "r") as f:
                        last_trace = json.loads(f.readlines()[-1])
                        for ag in last_trace.get("agents", []):
                            if ag["name"] == agent_name or ag["name"] == agent_response.get("agent"):
                                if ag.get("model"):
                                    model_info = f" ({ag['model']})"
                                break
                except:
                    pass

                message_text = agent_response.get("message", "")
                
                # Check for completion
                if agent_response.get("status") == "completed":
                    message_text += "\n\n*🔒 Conversación finalizada*"
            else:
                agent_name = "unknown"
                model_info = ""
                message_text = str(agent_response)

        # 3. Display Assistant Message
        st.session_state.messages.append({
            "role": "assistant", 
            "content": message_text, 
            "agent": f"{agent_name}{model_info}",
            "latency_ms": request_elapsed_ms,
            "avatar": "🤖"
        })
        
        with st.chat_message("assistant", avatar="🤖"):
            st.caption(f"🤖 {agent_name}{model_info}")
            st.caption(f"⏱️ Total: {request_elapsed_ms/1000:.2f}s ({request_elapsed_ms:.0f}ms)")
            st.markdown(message_text)

    except requests.exceptions.ConnectionError:
        st.error("❌ No se pudo conectar a la API. Asegúrate de que Docker esté corriendo.")
    except Exception as e:
        st.error(f"❌ Error: {e}")
