from fastapi import FastAPI
from pydantic import BaseModel
import requests
import json
from datetime import datetime

# =========================================================
# CONFIGURACIÓN
# =========================================================

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
BUTLER_CARTA_URL = "http://147.96.81.252:8000/carta"
MODEL = "mistral"

app = FastAPI(title="Agente 51")

# =========================================================
# MODELO DE ESTADO
# =========================================================

class ButlerState(BaseModel):
    Alias: list[str] | None = None
    Recursos: dict
    Objetivo: dict
    Buzon: dict | None = None

# =========================================================
# PROMPT PARA EL LLM (MEJORADO)
# =========================================================

def construir_prompt(estado: ButlerState) -> str:
    return f"""
Eres un agente autónomo dentro de un sistema de intercambio de recursos
basado exclusivamente en mensajes (cartas).

Tu comportamiento debe ser racional, claro y orientado a cumplir el objetivo.

REGLAS OBLIGATORIAS:
- No puedes inventar recursos.
- No puedes asumir información que no esté en el estado.
- No puedes acceder a recursos de otros agentes sin acordarlo.
- La única forma de interactuar es enviando cartas.
- Si no hay ninguna acción razonable, debes esperar.

CONTEXTO ACTUAL:

Recursos que posees:
{json.dumps(estado.Recursos, indent=2)}

Objetivo que necesitas alcanzar:
{json.dumps(estado.Objetivo, indent=2)}

Mensajes recibidos (si los hay):
{json.dumps(estado.Buzon or {}, indent=2)}

CRITERIOS DE DECISIÓN:

1. Si no tienes contacto previo con otros agentes y necesitas recursos
   para avanzar hacia tu objetivo:
   - Debes iniciar contacto solicitando claramente lo que necesitas.
   - El mensaje debe indicar qué recursos tienes disponibles
     y qué recursos necesitas.

2. Si recibes una carta:
   - Evalúa si puedes satisfacerla total o parcialmente.
   - Si te conviene, propone un intercambio razonable.
   - Si no te conviene, espera.

3. No repitas pedidos inútiles.
4. No envíes mensajes vacíos.
5. Prioriza intercambios que acerquen directamente al objetivo.

FORMATO DE RESPUESTA (OBLIGATORIO):
Debes devolver UNA sola acción en JSON ESTRICTO.
No escribas texto adicional.
No expliques el razonamiento.

Acciones posibles:

{{"accion":"esperar"}}

{{"accion":"pedir","recurso":"<nombre>","cantidad":<numero>}}

{{"accion":"ofrecer","ofrezco":{{"recurso":cantidad}}, "pido":{{"recurso":cantidad}}}}

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

def enviar_carta(alias: str, mensaje: str):
    print("\nENVIANDO CARTA A:", alias)
    print("MENSAJE:", mensaje)

    r = requests.post(
        BUTLER_CARTA_URL,
        json={
            "alias": alias,
            "mensaje": mensaje
        }
    )

    print("RESPUESTA BUTLER:", r.status_code, r.text)

# =========================================================
# EJECUCIÓN DE LA DECISIÓN
# =========================================================

def ejecutar_decision(decision: dict, alias: str):
    accion = decision.get("accion")

    print("\nEJECUTANDO DECISIÓN:", decision)

    if accion == "esperar":
        return {"estado": "esperando"}

    if accion == "pedir":
        recurso = decision.get("recurso")
        cantidad = decision.get("cantidad")

        if recurso and cantidad:
            mensaje = (
                f"Tengo disponibles los siguientes recursos: "
                f"{decision.get('ofrezco', 'ver estado actual')}. "
                f"Necesito {cantidad} unidades de {recurso}."
            )
            enviar_carta(alias, mensaje)
            return {"estado": "pedido_enviado"}

    if accion == "ofrecer":
        ofrezco = decision.get("ofrezco", {})
        pido = decision.get("pido", {})
        mensaje = f"Ofrezco {ofrezco} a cambio de {pido}"
        enviar_carta(alias, mensaje)
        return {"estado": "oferta_enviada"}

    print("Acción no válida. Se espera.")
    return {"estado": "esperando"}

# =========================================================
# ENDPOINT PRINCIPAL
# =========================================================

@app.post("/generate")
def generate(estado: ButlerState):
    timestamp = datetime.now().strftime("%H:%M:%S")
    alias = estado.Alias[0] if estado.Alias else "agente"

    print("\n======================================")
    print(f"NUEVA LLAMADA /generate [{timestamp}]")
    print("ALIAS:", alias)

    prompt = construir_prompt(estado)
    decision = consultar_ollama(prompt)
    resultado = ejecutar_decision(decision, alias)

    return {
        "decision": decision,
        "resultado": resultado
    }
