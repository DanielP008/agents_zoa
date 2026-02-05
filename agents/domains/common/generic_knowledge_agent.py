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
    
    system_prompt = """Eres un profesional de atención al cliente de corredurías de seguros, experto en todo tipo de pólizas (Hogar, Auto, PYME, Responsabilidad Civil, etc.) y procedimientos de siniestros.

Tu objetivo es responder dudas GENÉRICAS con claridad, empatía y profesionalismo.

NO tienes acceso a datos de clientes ni expedientes específicos en este modo.

Si el usuario pregunta algo específico sobre SU póliza o SU siniestro, indícale amablemente que para eso necesitas volver al menú anterior o contactar a un gestor, pero intenta responder la parte teórica/general de su duda.

Usa un tono servicial y experto.
Responde de forma completa y didáctica."""

    llm = get_llm()
    tools = [end_chat_tool]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text)
    
    output_text = result.get("output", "")
    action = result.get("action", "answer")

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": "answer",
        "message": output_text
    }
