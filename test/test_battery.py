"""
Battery test - 10 use cases per specialist agent, all run concurrently.
Run: python test/test_battery.py

Requires Docker container running on localhost:8080.
Each test case uses a unique wa_id to avoid session collisions.
"""

import requests
import json
import time
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

API_URL = "http://localhost:8080"
COMPANY_ID = "521783407682043"
TEST_NIF = "Z1549612S"
MAX_TURNS = 20  # Safety limit per conversation
TIMEOUT = 60    # HTTP timeout per request

# ─── Colors ───
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ─────────────────────────────────────────────────────────
# TEST CASES
# Each case: list of messages to send sequentially.
# The script waits for the agent response before sending next.
# If the agent asks something unexpected, the script sends
# the next message in the list regardless.
# ─────────────────────────────────────────────────────────

TELEFONOS_ASISTENCIA_CASES = [
    {
        "name": "Grúa urgente M-40",
        "messages": [
            "Necesito una grúa urgente, me quedé tirado en la M-40",
            "no, nada más gracias",
        ],
    },
    {
        "name": "Batería descargada",
        "messages": [
            "Mi coche no arranca, creo que es la batería",
            "no gracias, eso es todo",
        ],
    },
    {
        "name": "Pinchazo en autopista",
        "messages": [
            "Tengo un pinchazo en la A-6 kilómetro 30",
            "no, gracias",
        ],
    },
    {
        "name": "Cerrajero coche",
        "messages": [
            "Me he dejado las llaves dentro del coche, necesito un cerrajero",
            "no, eso es todo",
        ],
    },
    {
        "name": "Asistencia en carretera genérica",
        "messages": [
            "Necesito asistencia en carretera",
            "no gracias",
        ],
    },
    {
        "name": "Coche no arranca frío",
        "messages": [
            "Mi coche no enciende, hace mucho frío y no arranca",
            "no, nada más",
        ],
    },
    {
        "name": "Remolque necesario",
        "messages": [
            "Necesito un remolque, el coche echa humo y no puedo moverlo",
            "no gracias, eso es todo",
        ],
    },
    {
        "name": "Teléfono emergencia hogar",
        "messages": [
            "Necesito el teléfono de emergencias del hogar, tengo una fuga de agua",
            "no, nada más",
        ],
    },
    {
        "name": "Auxilio nocturno",
        "messages": [
            "Me he quedado tirado a las 3 de la mañana en una carretera secundaria",
            "no gracias",
        ],
    },
    {
        "name": "Asistencia pinchazo y grúa",
        "messages": [
            "Se me reventó una rueda y el coche tiene daños, necesito grúa",
            "no, eso es todo gracias",
        ],
    },
]

APERTURA_SINIESTRO_CASES = [
    {
        "name": "Accidente auto simple",
        "messages": [
            "Tuve un accidente de coche ayer",
            "De auto",
            "Ayer a las 15:00",
            "En la calle Gran Vía de Madrid",
            "Me chocaron por detrás en un semáforo",
            "No, el otro conductor fue el culpable",
            "No, no tenemos parte amistoso",
            "La matrícula es 1234 ABC",
            "Al taller del barrio, Talleres López",
            "El lunes me viene bien",
            "Sí, es correcto",
            "no, nada más gracias",
        ],
    },
    {
        "name": "Robo de vehículo",
        "messages": [
            "Me han robado el coche esta mañana",
            "Es un seguro de auto",
            "Hoy a las 8:00 de la mañana",
            "Estaba aparcado en la calle Serrano 45, Madrid",
            "Cuando llegué al parking el coche no estaba, ya puse denuncia",
            "La matrícula es 5678 DEF",
            "Sí todo correcto",
            "no gracias",
        ],
    },
    {
        "name": "Daños por agua hogar",
        "messages": [
            "Tengo una inundación en casa por rotura de tubería",
            "Hogar",
            "Hace unas 2 horas",
            "En la cocina, se ha roto la tubería debajo del fregadero",
            "El agua ha dañado el suelo y los muebles bajos de la cocina",
            "Calle Alcalá 120, 3ºB, Madrid",
            "No tengo fotos ahora pero puedo hacer luego",
            "Sí, es correcto",
            "no nada más",
        ],
    },
    {
        "name": "Incendio garaje",
        "messages": [
            "Ha habido un incendio en mi garaje",
            "Es seguro de hogar",
            "Esta madrugada sobre las 4:00",
            "En el garaje de mi vivienda",
            "Se quemaron cajas almacenadas y parte de la estructura del techo",
            "Avenida de la Constitución 50, Sevilla",
            "Sí, correcto",
            "no gracias, eso es todo",
        ],
    },
    {
        "name": "Colisión en rotonda",
        "messages": [
            "Acabo de tener un accidente en una rotonda",
            "Auto",
            "Hace 30 minutos",
            "En la rotonda de la Plaza de España",
            "Otro coche entró en la rotonda sin ceder el paso y me golpeó en el lateral",
            "No está claro quién tiene la culpa",
            "Sí, tenemos parte amistoso firmado",
            "Mi matrícula es 9012 GHI",
            "Todavía no sé qué taller",
            "Sí, todo correcto",
            "no, eso es todo",
        ],
    },
    {
        "name": "Daños comunidad vecinos",
        "messages": [
            "Hay una fuga en la bajante del edificio que está dañando varios pisos",
            "Es del seguro de comunidades de vecinos",
            "Lo detectamos hace dos días",
            "En zona común, la bajante principal que pasa por la fachada interior",
            "Sí, hay dos vecinos del segundo piso afectados con humedades",
            "Los daños son humedades en paredes y techos de los pisos 2ºA y 2ºB",
            "Calle Mayor 15, Madrid",
            "Sí es correcto todo",
            "no, nada más",
        ],
    },
    {
        "name": "Siniestro PYME comercio",
        "messages": [
            "Han entrado a robar en mi tienda anoche",
            "Es un seguro de PYME comercio",
            "Anoche entre las 2 y las 5 de la madrugada",
            "Reventaron la puerta principal y se llevaron mercancía",
            "No puedo abrir el negocio porque la puerta está destrozada",
            "Sí, se llevaron bastante stock de electrónica",
            "El local ha quedado desprotegido con la puerta rota",
            "No, no han dañado bienes de clientes",
            "Sí, todo correcto",
            "no gracias",
        ],
    },
    {
        "name": "Responsabilidad civil daños tercero",
        "messages": [
            "Mi perro mordió a un vecino y quiere reclamar",
            "Es responsabilidad civil",
            "Fue ayer por la tarde sobre las 18:00",
            "En el parque del Retiro, Madrid",
            "Mi perro le mordió en la pierna y tuvo que ir a urgencias",
            "Se llama Antonio García, su teléfono es 612345678 y su correo es antonio@email.com",
            "No hay denuncias por ahora pero dice que va a denunciar",
            "No, no había testigos",
            "Sí, es correcto",
            "no, eso es todo",
        ],
    },
    {
        "name": "Atropello leve auto",
        "messages": [
            "He atropellado a un peatón que cruzó en rojo",
            "Auto",
            "Hoy a las 9:30 de la mañana",
            "En el cruce de la calle Goya con Serrano",
            "Un peatón cruzó en rojo y no pude frenar a tiempo, le golpeé levemente",
            "No está claro, él cruzó en rojo pero yo iba un poco rápido",
            "No hay parte amistoso, vino la policía",
            "Mi matrícula es 3456 JKL",
            "Sí todo correcto",
            "no nada más",
        ],
    },
    {
        "name": "Goteras hogar temporal",
        "messages": [
            "Tengo goteras en el salón por las lluvias de ayer",
            "Hogar",
            "Desde ayer por la noche",
            "En el salón, en la esquina del techo",
            "Se ha formado una mancha de humedad grande y gotea cuando llueve",
            "Calle Valencia 80, 5ºA, Barcelona",
            "Sí puedo enviar fotos después",
            "Sí correcto",
            "no, eso es todo gracias",
        ],
    },
]

CONSULTA_ESTADO_CASES = [
    {
        "name": "Estado siniestro genérico",
        "messages": [
            "Quiero saber cómo va mi siniestro",
            "no, nada más",
        ],
    },
    {
        "name": "Seguimiento expediente",
        "messages": [
            "¿En qué estado está mi expediente de siniestro?",
            "no gracias",
        ],
    },
    {
        "name": "Parte abierto hace semanas",
        "messages": [
            "Abrí un parte hace tres semanas y no sé nada",
            "no, eso es todo",
        ],
    },
    {
        "name": "Perito pendiente",
        "messages": [
            "¿Ya vino el perito a valorar los daños de mi siniestro?",
            "no, nada más gracias",
        ],
    },
    {
        "name": "Resolución siniestro",
        "messages": [
            "¿Se ha resuelto ya mi siniestro del accidente del mes pasado?",
            "no gracias, eso es todo",
        ],
    },
    {
        "name": "Documentación pendiente",
        "messages": [
            "Me dijeron que faltaba documentación para mi siniestro, ¿ya está completo?",
            "no, nada más",
        ],
    },
    {
        "name": "Pago indemnización",
        "messages": [
            "¿Cuándo me van a pagar la indemnización de mi siniestro?",
            "no, eso es todo gracias",
        ],
    },
    {
        "name": "Siniestro hogar estado",
        "messages": [
            "Quiero consultar el estado del siniestro de mi hogar por la inundación",
            "no gracias",
        ],
    },
    {
        "name": "Reparación autorizada",
        "messages": [
            "¿Ya autorizaron la reparación de mi coche del siniestro?",
            "no, nada más",
        ],
    },
    {
        "name": "Referencia expediente",
        "messages": [
            "Tengo el número de expediente 2025-4321, ¿pueden ver el estado?",
            "no, eso es todo",
        ],
    },
]

DEVOLUCION_CASES = [
    {
        "name": "Cobro duplicado",
        "messages": [
            "Me cobraron dos veces el recibo del seguro",
            "no, nada más",
        ],
    },
    {
        "name": "Cobro indebido",
        "messages": [
            "Me están cobrando un seguro que ya cancelé",
            "no, eso es todo",
        ],
    },
    {
        "name": "Devolución por anulación",
        "messages": [
            "Quiero la devolución porque anulé la póliza hace un mes y me siguen cobrando",
            "no gracias",
        ],
    },
    {
        "name": "Reembolso importe excesivo",
        "messages": [
            "El recibo de este mes es más alto de lo normal, quiero un reembolso",
            "no, nada más gracias",
        ],
    },
    {
        "name": "Cobro tras baja",
        "messages": [
            "Di de baja el seguro del coche y me cobraron otro mes",
            "no, eso es todo",
        ],
    },
    {
        "name": "Error en cobro",
        "messages": [
            "Hubo un error en el cobro de mi póliza, necesito que me devuelvan el dinero",
            "no gracias",
        ],
    },
    {
        "name": "Devolución parcial",
        "messages": [
            "Cambié de plan y me cobraron el precio anterior, necesito la diferencia",
            "no, nada más",
        ],
    },
    {
        "name": "Cobro sin autorización",
        "messages": [
            "Me cobraron un seguro que nunca contraté, quiero mi dinero de vuelta",
            "no, eso es todo gracias",
        ],
    },
    {
        "name": "Doble recibo diferentes meses",
        "messages": [
            "Me han pasado dos recibos en el mismo mes de mi seguro de hogar",
            "no gracias, eso es todo",
        ],
    },
    {
        "name": "Reembolso franquicia",
        "messages": [
            "Pagué una franquicia pero luego se determinó que yo no tuve culpa, quiero la devolución",
            "no, nada más",
        ],
    },
]

CONSULTAR_POLIZA_CASES = [
    {
        "name": "Ver coberturas",
        "messages": [
            "Quiero ver qué cubre mi seguro de coche",
            "no, nada más",
        ],
    },
    {
        "name": "Fecha vencimiento",
        "messages": [
            "¿Cuándo vence mi póliza de hogar?",
            "no gracias",
        ],
    },
    {
        "name": "Ver póliza completa",
        "messages": [
            "Quiero ver toda la información de mi póliza",
            "no, eso es todo",
        ],
    },
    {
        "name": "Precio actual",
        "messages": [
            "¿Cuánto estoy pagando por mi seguro?",
            "no, nada más gracias",
        ],
    },
    {
        "name": "Coberturas específicas",
        "messages": [
            "¿Mi seguro de coche cubre robo?",
            "no gracias, eso es todo",
        ],
    },
    {
        "name": "Datos del contrato",
        "messages": [
            "Necesito los datos de mi contrato de seguro",
            "no, nada más",
        ],
    },
    {
        "name": "Capital asegurado",
        "messages": [
            "¿Cuál es el capital asegurado de mi póliza de hogar?",
            "no, eso es todo",
        ],
    },
    {
        "name": "Documento póliza",
        "messages": [
            "Necesito que me envíen una copia de mi póliza",
            "no gracias",
        ],
    },
    {
        "name": "Renovación próxima",
        "messages": [
            "¿Cuándo se renueva mi seguro de auto?",
            "no, nada más",
        ],
    },
    {
        "name": "Asistencia incluida",
        "messages": [
            "¿Tengo asistencia en carretera incluida en mi póliza?",
            "no, eso es todo gracias",
        ],
    },
]

MODIFICAR_POLIZA_CASES = [
    {
        "name": "Cambiar IBAN",
        "messages": [
            "Quiero cambiar el IBAN de mi seguro",
            "ES76 2100 0418 4502 0005 1332",
            "Sí, correcto",
            "no, nada más",
        ],
    },
    {
        "name": "Cambiar matrícula",
        "messages": [
            "He cambiado de coche y necesito actualizar la matrícula",
            "La nueva matrícula es 4567 MNO",
            "Sí",
            "no gracias",
        ],
    },
    {
        "name": "Actualizar domicilio",
        "messages": [
            "Necesito cambiar mi dirección del seguro de hogar",
            "Calle Princesa 25, 2ºA, 28008 Madrid",
            "Sí, es correcto",
            "no, eso es todo",
        ],
    },
    {
        "name": "Cambiar teléfono",
        "messages": [
            "Quiero actualizar mi número de teléfono en la póliza",
            "El nuevo es 634567890",
            "Sí",
            "no, nada más",
        ],
    },
    {
        "name": "Cambiar email",
        "messages": [
            "Necesito cambiar mi correo electrónico",
            "Mi nuevo correo es nuevo@email.com",
            "Sí correcto",
            "no gracias",
        ],
    },
    {
        "name": "Cambiar beneficiario",
        "messages": [
            "Quiero cambiar el beneficiario de mi seguro de vida",
            "El nuevo beneficiario es María López García con DNI 12345678A",
            "Sí, es correcto",
            "no, eso es todo",
        ],
    },
    {
        "name": "Actualizar datos conductor",
        "messages": [
            "Necesito añadir un segundo conductor a mi póliza de auto",
            "Se llama Pedro Martínez, tiene 35 años y carnet desde 2010",
            "Sí, correcto",
            "no gracias, nada más",
        ],
    },
    {
        "name": "Cambiar forma de pago",
        "messages": [
            "Quiero cambiar de pago anual a pago trimestral",
            "Sí, es correcto",
            "no, eso es todo",
        ],
    },
    {
        "name": "Actualizar datos personales",
        "messages": [
            "Necesito actualizar mi apellido en la póliza porque me he casado",
            "Mi nuevo apellido es González-Pérez",
            "Sí",
            "no, nada más",
        ],
    },
    {
        "name": "Cambiar dirección correspondencia",
        "messages": [
            "Necesito modificar la dirección donde me envían la correspondencia",
            "Apartado de correos 345, 28001 Madrid",
            "Sí, es correcto",
            "no, eso es todo gracias",
        ],
    },
]


# ─────────────────────────────────────────────────────────
# ALL TEST SUITES
# ─────────────────────────────────────────────────────────

ALL_SUITES = [
    ("telefonos_asistencia", TELEFONOS_ASISTENCIA_CASES),
    ("apertura_siniestro", APERTURA_SINIESTRO_CASES),
    ("consulta_estado", CONSULTA_ESTADO_CASES),
    ("devolucion", DEVOLUCION_CASES),
    ("consultar_poliza", CONSULTAR_POLIZA_CASES),
    ("modificar_poliza", MODIFICAR_POLIZA_CASES),
]


# ─────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────

def reset_session(wa_id: str):
    """Reset session before test."""
    payload = {
        "wa_id": wa_id,
        "mensaje": "BORRAR TODO",
        "phone_number_id": COMPANY_ID,
        "name": "Test Battery",
    }
    try:
        requests.post(API_URL, json=payload, timeout=10)
    except Exception:
        pass


def send_message(wa_id: str, message: str) -> dict:
    """Send a message and return parsed response."""
    payload = {
        "wa_id": wa_id,
        "mensaje": message,
        "phone_number_id": COMPANY_ID,
        "name": "Test Battery",
    }
    resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def run_test_case(suite_name: str, case_idx: int, case: dict) -> dict:
    """Run a single test case through the full conversation flow."""
    case_name = case["name"]
    messages = case["messages"]
    wa_id = f"+34900{suite_name[:3].upper()}{case_idx:03d}"

    result = {
        "suite": suite_name,
        "case": case_name,
        "wa_id": wa_id,
        "status": "unknown",
        "turns": 0,
        "total_ms": 0,
        "agents_seen": [],
        "error": None,
        "conversation": [],
    }

    try:
        # Reset session
        reset_session(wa_id)
        time.sleep(0.3)

        # Phase 1: Bootstrap - send first message to trigger welcome, then provide NIF
        # Turn 0: First message triggers the welcome + NIF request
        t0 = time.time()
        data = send_message(wa_id, "Hola")
        elapsed = (time.time() - t0) * 1000
        result["total_ms"] += elapsed
        result["turns"] += 1
        resp = data.get("response", {})
        if isinstance(resp, dict):
            agent = resp.get("agent") or resp.get("next_agent") or "orchestrator"
            if agent not in result["agents_seen"]:
                result["agents_seen"].append(agent)
            result["conversation"].append({
                "turn": 1, "user": "Hola", "agent": agent,
                "response": (resp.get("message", "") or "")[:120], "ms": round(elapsed),
            })

        # Turn 1: Provide NIF
        t0 = time.time()
        data = send_message(wa_id, TEST_NIF)
        elapsed = (time.time() - t0) * 1000
        result["total_ms"] += elapsed
        result["turns"] += 1
        resp = data.get("response", {})
        if isinstance(resp, dict):
            agent = resp.get("agent") or resp.get("next_agent") or "orchestrator"
            if agent not in result["agents_seen"]:
                result["agents_seen"].append(agent)
            result["conversation"].append({
                "turn": 2, "user": TEST_NIF, "agent": agent,
                "response": (resp.get("message", "") or "")[:120], "ms": round(elapsed),
            })

        # Phase 2: Send the actual test messages
        msg_idx = 0
        completed = False
        turn_offset = 3

        for turn in range(MAX_TURNS):
            if msg_idx >= len(messages):
                break

            user_msg = messages[msg_idx]
            t0 = time.time()

            data = send_message(wa_id, user_msg)
            elapsed = (time.time() - t0) * 1000

            result["total_ms"] += elapsed
            result["turns"] += 1

            agent_response = data.get("response", {})
            if isinstance(agent_response, dict):
                agent = agent_response.get("agent") or agent_response.get("next_agent") or "unknown"
                resp_msg = agent_response.get("message", "")
                status = agent_response.get("status")

                if agent not in result["agents_seen"]:
                    result["agents_seen"].append(agent)

                result["conversation"].append({
                    "turn": turn + turn_offset,
                    "user": user_msg,
                    "agent": agent,
                    "response": (resp_msg or "")[:120],
                    "ms": round(elapsed),
                })

                if status == "completed":
                    completed = True
                    break
            else:
                result["conversation"].append({
                    "turn": turn + turn_offset,
                    "user": user_msg,
                    "agent": "raw",
                    "response": str(agent_response)[:120],
                    "ms": round(elapsed),
                })

            msg_idx += 1

        result["status"] = "completed" if completed else "finished_messages"
        result["total_ms"] = round(result["total_ms"])

    except requests.exceptions.ConnectionError:
        result["status"] = "connection_error"
        result["error"] = "Could not connect to API"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def print_result(r: dict):
    """Print a single test result."""
    status_color = GREEN if r["status"] == "completed" else (YELLOW if r["status"] == "finished_messages" else RED)
    status_icon = "PASS" if r["status"] == "completed" else ("WARN" if r["status"] == "finished_messages" else "FAIL")

    print(f"  {status_color}[{status_icon}]{RESET} {r['suite']}/{r['case']}")
    print(f"        Turns: {r['turns']} | Total: {r['total_ms']}ms | Avg: {r['total_ms'] // max(r['turns'], 1)}ms/turn")
    print(f"        Agents: {' -> '.join(r['agents_seen'])}")

    if r["error"]:
        print(f"        {RED}Error: {r['error']}{RESET}")


def print_summary(results: list):
    """Print final summary."""
    total = len(results)
    completed = sum(1 for r in results if r["status"] == "completed")
    finished = sum(1 for r in results if r["status"] == "finished_messages")
    errors = sum(1 for r in results if r["status"] in ("error", "connection_error"))

    total_time = sum(r["total_ms"] for r in results)
    total_turns = sum(r["turns"] for r in results)
    avg_turn = total_time / max(total_turns, 1)

    print(f"\n{'='*60}")
    print(f"{BOLD}BATTERY TEST SUMMARY{RESET}")
    print(f"{'='*60}")
    print(f"  Total cases:     {total}")
    print(f"  {GREEN}Completed:       {completed}{RESET}")
    print(f"  {YELLOW}Finished msgs:   {finished}{RESET}")
    print(f"  {RED}Errors:          {errors}{RESET}")
    print(f"")
    print(f"  Total time:      {total_time / 1000:.1f}s")
    print(f"  Total turns:     {total_turns}")
    print(f"  Avg per turn:    {avg_turn:.0f}ms")
    print(f"{'='*60}")

    # Per-suite breakdown
    suites = {}
    for r in results:
        s = r["suite"]
        if s not in suites:
            suites[s] = {"total": 0, "completed": 0, "ms": 0, "turns": 0}
        suites[s]["total"] += 1
        suites[s]["completed"] += 1 if r["status"] == "completed" else 0
        suites[s]["ms"] += r["total_ms"]
        suites[s]["turns"] += r["turns"]

    print(f"\n{BOLD}Per-Suite:{RESET}")
    for name, stats in suites.items():
        avg = stats["ms"] / max(stats["turns"], 1)
        color = GREEN if stats["completed"] == stats["total"] else YELLOW
        print(f"  {color}{name:.<30s} {stats['completed']}/{stats['total']} passed | {stats['ms']}ms total | {avg:.0f}ms/turn{RESET}")


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}ZOA AGENTS - BATTERY TEST{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"  API:      {API_URL}")
    print(f"  Workers:  {workers}")
    print(f"  Suites:   {len(ALL_SUITES)}")
    print(f"  Cases:    {sum(len(cases) for _, cases in ALL_SUITES)}")
    print(f"{'='*60}\n")

    # Check API is reachable
    try:
        requests.get(API_URL, timeout=5)
    except Exception:
        print(f"{RED}ERROR: Cannot reach {API_URL}. Is Docker running?{RESET}")
        sys.exit(1)

    # Build all tasks
    tasks = []
    for suite_name, cases in ALL_SUITES:
        for i, case in enumerate(cases):
            tasks.append((suite_name, i, case))

    results = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_test_case, suite, idx, case): (suite, case["name"])
            for suite, idx, case in tasks
        }

        for future in as_completed(futures):
            suite, name = futures[future]
            try:
                result = future.result()
                results.append(result)
                print_result(result)
            except Exception as e:
                print(f"  {RED}[FAIL]{RESET} {suite}/{name} - Exception: {e}")

    elapsed = time.time() - t_start
    print(f"\n{CYAN}Wall clock: {elapsed:.1f}s{RESET}")

    print_summary(results)

    # Save detailed results to JSON
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "timings")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "battery_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed results saved to {out_path}")


if __name__ == "__main__":
    main()
