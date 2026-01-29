import json
from langchain_core.prompts import ChatPromptTemplate
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.llm import get_llm
from tools.communication.end_chat_tool import end_chat_tool

def generic_knowledge_agent(payload: dict) -> dict:
    """
    Agente experto en conocimientos generales de seguros.
    Puede ser instanciado por otros agentes para responder dudas genéricas.
    """
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    # No history needed from the caller strictly, but good to have context if passed
    # usually payload has 'session' which has 'agent_memory'.
    
    # We can use a simplified history or just the current query if it's a one-off answer.
    # However, to maintain conversation flow, we might want to treat it as a standard agent.
    
    system_prompt = (
        "Eres un profesional de atención al cliente de corredurías de seguros, experto en todo tipo de pólizas "
        "(Hogar, Auto, PYME, Responsabilidad Civil, etc.) y procedimientos de siniestros.\n"
        "Tu objetivo es responder dudas GENÉRICAS con claridad, empatía y profesionalismo.\n"
        "NO tienes acceso a datos de clientes ni expedientes específicos en este modo.\n"
        "Si el usuario pregunta algo específico sobre SU póliza o SU siniestro, indícale amablemente "
        "que para eso necesitas volver al menú anterior o contactar a un gestor, "
        "pero intenta responder la parte teórica/general de su duda.\n"
        "Usa un tono servicial y experto.\n"
        "Responde de forma completa y didáctica."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{user_text}"),
        ]
    )

    # Use the powerful model for expert knowledge as requested previously
    llm = get_llm(model_name="gemini-3-flash-preview")
    
    # This agent mainly answers, but could potentially end chat if needed
    tools = [end_chat_tool] 
    
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "answer") # Default to answer, not ask, usually

    # If the sub-agent decides to end chat, propagate it.
    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": "answer", # Or 'ask' if it needs clarification, but usually it just answers
        "message": output_text
    }
