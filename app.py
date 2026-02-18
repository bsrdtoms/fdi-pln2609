from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
import requests
import json
import threading
import time
from datetime import datetime

# =========================================================
# CONFIGURACIÓN
# =========================================================

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
BUTLER_BASE_URL = "http://147.96.81.252:7719"
MODEL = "mistral"
POLL_INTERVAL = 10  # secondes entre chaque vérification

# =========================================================
# MODELO DE ESTADO
# =========================================================

class ButlerState(BaseModel):
    Alias: str = ""
    Recursos: dict
    Objetivo: dict
    Buzon: dict | None = None

# =========================================================
# FUNCIONES UTILITARIAS
# =========================================================

def obtener_estado() -> ButlerState:
    r = requests.get(f"{BUTLER_BASE_URL}/info", timeout=10)
    return ButlerState(**r.json())

def obtener_otros_agentes(mi_alias: str) -> list[str]:
    try:
        r = requests.get(f"{BUTLER_BASE_URL}/gente", timeout=10)
        gente = r.json()
        return [g.get("Alias", g.get("alias", "")) for g in gente
                if g.get("Alias", g.get("alias", "")) != mi_alias]
    except Exception as e:
        print("Error obteniendo agentes:", e)
        return []

def calcular_faltan_sobran(recursos: dict, objetivo: dict) -> tuple[dict, dict]:
    faltan = {}
    for rec, cant in objetivo.items():
        tengo = recursos.get(rec, 0)
        if cant > tengo:
            faltan[rec] = cant - tengo
    sobran = {}
    for rec, cant in recursos.items():
        necesito = objetivo.get(rec, 0)
        if cant > necesito:
            sobran[rec] = cant - necesito
        elif rec not in objetivo:
            sobran[rec] = cant
    return faltan, sobran


# =========================================================
# PROMPTS
# =========================================================

def construir_prompt_nueva_carta(estado: ButlerState, carta: dict) -> str:
    faltan, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)
    return f"""
Eres un agente autónomo llamado "{estado.Alias}" dentro de un sistema de intercambio de recursos.

ESTADO ACTUAL:
- Recursos que posees: {json.dumps(estado.Recursos)}
- Objetivo: {json.dumps(estado.Objetivo)}
- Recursos que te FALTAN (necesitas conseguir): {json.dumps(faltan)}
- Recursos que te SOBRAN (puedes ofrecer): {json.dumps(sobran)}

REGLA ABSOLUTA: Solo puedes ofrecer lo que está en "SOBRAN": {json.dumps(sobran)}.
Los ÚNICOS recursos que puedes dar son: {', '.join(f'{v} de {k}' for k, v in sobran.items())}.
NUNCA ofrezcas un recurso que esté en "FALTAN". Esos son los que NECESITAS recibir.

Acabas de recibir esta carta:
- De: {carta.get("remi", "?")}
- Asunto: {carta.get("asunto", "")}
- Cuerpo: {carta.get("cuerpo", "")}

INSTRUCCIONES:
1. ANALIZA la carta: ¿el remitente ofrece algo que te FALTA?
2. Si el remitente ACEPTA un intercambio o OFRECE enviarte recursos que te FALTAN:
   USA "aceptar" para enviarle un paquete con los recursos de SOBRAN que pidió.
   En "envio" pon SOLO recursos de SOBRAN con cantidades que NO excedan lo disponible.
3. Si el remitente propone un intercambio pero aún no lo confirma, responde con "ofrecer".
4. Si el remitente solo pide cosas y no ofrece nada que te falte, responde "esperar".
5. NUNCA envíes recursos que no están en SOBRAN.

FORMATO (JSON estricto, sin texto adicional):

{{"accion":"esperar"}}

{{"accion":"ofrecer","dest":"{carta.get("remi", "")}","asunto":"Propuesta de intercambio","cuerpo":"Te propongo: te doy N de [recurso de SOBRAN] a cambio de M de [recurso de FALTAN]."}}

{{"accion":"aceptar","dest":"{carta.get("remi", "")}","envio":{{"recurso":cantidad}}}}

Ejemplo de aceptar: {{"accion":"aceptar","dest":"agente1","envio":{{"piedra":1,"oro":5}}}}

Devuelve SOLO el JSON.
"""


# =========================================================
# CONSULTA A OLLAMA
# =========================================================

def consultar_ollama(prompt: str) -> dict:
    print("\n===== CONSULTANDO OLLAMA =====")

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    ).json()

    texto = response.get("response", "").strip()

    print("RESPUESTA OLLAMA CRUDA:")
    print(texto)

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        print("JSON inválido. Fallback a esperar.")
        return {"accion": "esperar"}

# =========================================================
# ENVÍO DE CARTAS A BUTLER
# =========================================================

def enviar_carta(remi: str, dest: str, asunto: str, cuerpo: str):
    print(f"\nENVIANDO CARTA DE '{remi}' A '{dest}'", flush=True)
    print("ASUNTO:", asunto, flush=True)
    print("CUERPO:", cuerpo, flush=True)

    r = requests.post(
        f"{BUTLER_BASE_URL}/carta",
        json={
            "remi": remi,
            "dest": dest,
            "asunto": asunto,
            "cuerpo": cuerpo
        }
    )

    print("RESPUESTA BUTLER:", r.status_code, r.text, flush=True)

def enviar_paquete(dest: str, recursos: dict):
    print(f"\nENVIANDO PAQUETE A '{dest}': {recursos}", flush=True)

    r = requests.post(
        f"{BUTLER_BASE_URL}/paquete/{dest}",
        json=recursos
    )

    print("RESPUESTA BUTLER PAQUETE:", r.status_code, r.text, flush=True)

# =========================================================
# EJECUCIÓN DE LA DECISIÓN
# =========================================================

def validar_envio(envio: dict) -> dict | None:
    """Vérifie qu'on a les ressources et qu'on n'envoie pas ce qu'on a besoin."""
    estado = obtener_estado()
    _, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)

    envio_valido = {}
    for rec, cant in envio.items():
        if not isinstance(cant, int) or cant <= 0:
            continue
        disponible = sobran.get(rec, 0)
        if disponible > 0:
            envio_valido[rec] = min(cant, disponible)

    if not envio_valido:
        return None
    return envio_valido

def ejecutar_decision(decision: dict, mi_alias: str):
    accion = decision.get("accion")

    print("\nEJECUTANDO DECISIÓN:", decision, flush=True)

    if accion == "esperar":
        return {"estado": "esperando"}

    dest = decision.get("dest", "")
    asunto = decision.get("asunto", "")
    cuerpo = decision.get("cuerpo", "")

    if accion == "aceptar" and dest:
        envio = decision.get("envio", {})
        envio_valido = validar_envio(envio)
        if envio_valido:
            enviar_paquete(dest, envio_valido)
            enviar_carta(remi=mi_alias, dest=dest, asunto="Intercambio aceptado",
                         cuerpo=f"Acepto el trato. Te envié: {json.dumps(envio_valido)}. Espero tu parte del intercambio.")
            return {"estado": "aceptado_y_enviado", "paquete": envio_valido}
        print(f"ENVIO BLOQUEADO: {envio} no es válido (no tienes esos recursos de sobra)", flush=True)
        return {"estado": "envio_bloqueado"}

    if accion in ("pedir", "ofrecer") and dest and cuerpo:
        enviar_carta(remi=mi_alias, dest=dest, asunto=asunto, cuerpo=cuerpo)
        return {"estado": f"{accion}_enviado"}

    print("Acción no válida o faltan campos. Se espera.", flush=True)
    return {"estado": "esperando"}

# =========================================================
# BOUCLE DE POLLING AUTOMATIQUE
# =========================================================

cartas_vistas: set[str] = set()

def procesar_nueva_carta(estado: ButlerState, carta: dict):
    alias = estado.Alias or "agente"
    timestamp = datetime.now().strftime("%H:%M:%S")

    print(f"\n====== NUEVA CARTA [{timestamp}] ======")
    print(f"DE: {carta.get('remi')} | ASUNTO: {carta.get('asunto')}")
    print(f"CUERPO: {carta.get('cuerpo')}")

    prompt = construir_prompt_nueva_carta(estado, carta)
    decision = consultar_ollama(prompt)
    resultado = ejecutar_decision(decision, alias)

    print(f"DECISIÓN: {decision}")
    print(f"RESULTADO: {resultado}")

def log(msg: str):
    print(msg, flush=True)

def polling_loop():
    log("\n[POLLING] Boucle de polling démarrée")
    # Marquer les cartas existantes comme déjà vues
    try:
        estado = obtener_estado()
        if estado.Buzon:
            for carta_id in estado.Buzon:
                cartas_vistas.add(carta_id)
        log(f"[POLLING] {len(cartas_vistas)} cartas existantes ignorées")
    except Exception as e:
        log(f"[POLLING] Erreur init: {e}")

    # Broadcast automatique au démarrage
    try:
        broadcast()
        log("[POLLING] Broadcast initial envoyé")
    except Exception as e:
        log(f"[POLLING] Erreur broadcast initial: {e}")

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            estado = obtener_estado()
            buzon = estado.Buzon or {}

            nuevas = {cid: carta for cid, carta in buzon.items() if cid not in cartas_vistas}

            if nuevas:
                log(f"\n[POLLING] {len(nuevas)} nouvelle(s) carta(s) détectée(s)")
                for carta_id, carta in nuevas.items():
                    cartas_vistas.add(carta_id)
                    procesar_nueva_carta(estado, carta)
        except Exception as e:
            log(f"[POLLING] Erreur: {e}")

# =========================================================
# LIFESPAN & APP
# =========================================================

@asynccontextmanager
async def lifespan(a: FastAPI):
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
    yield

app = FastAPI(title="Agente 51", lifespan=lifespan)

# =========================================================
# ENDPOINTS
# =========================================================

@app.post("/broadcast")
def broadcast():
    estado = obtener_estado()
    alias = estado.Alias or "agente"
    otros_agentes = obtener_otros_agentes(alias)
    faltan, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)

    cuerpo = (
        f"Hola, soy {alias}.\n"
        f"Necesito: {', '.join(f'{v} de {k}' for k, v in faltan.items())}.\n"
        f"Ofrezco a cambio: {', '.join(f'{v} de {k}' for k, v in sobran.items())}.\n"
        f"Si te interesa, propón un intercambio concreto."
    )

    resultados = []
    for dest in otros_agentes:
        enviar_carta(remi=alias, dest=dest, asunto="Busco intercambio", cuerpo=cuerpo)
        resultados.append(dest)

    return {
        "enviado_a": resultados,
        "mensaje": cuerpo
    }

@app.post("/aceptar/{dest}")
def aceptar(dest: str, envio: dict):
    """Accepter un échange: envoie un paquete et une carta de confirmation."""
    estado = obtener_estado()
    alias = estado.Alias or "agente"

    # Vérifier qu'on a les ressources
    for rec, cant in envio.items():
        if estado.Recursos.get(rec, 0) < cant:
            return {"error": f"No tienes suficiente {rec} (tienes {estado.Recursos.get(rec, 0)}, quieres enviar {cant})"}

    enviar_paquete(dest, envio)
    enviar_carta(remi=alias, dest=dest, asunto="Intercambio aceptado",
                 cuerpo=f"Acepto el trato. Te envié: {json.dumps(envio)}. Espero tu parte del intercambio.")

    return {"estado": "aceptado_y_enviado", "dest": dest, "paquete": envio}

