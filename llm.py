"""
llm.py — Couche IA moderne : prompt engineering et interface Ollama.

Ce module construit les prompts envoyés au LLM et parse ses réponses JSON.
Il adapte le prompt au type de carta détecté et à l'état courant de l'agent,
afin de tirer le meilleur parti des capacités (et limites) du modèle utilisé.
"""

import json
import logging
import re

import requests

from config import OLLAMA_URL, MODEL, ButlerState
from agent import calcular_faltan_sobran

logger = logging.getLogger(__name__)


# ── Classification des cartas ──────────────────────────────────────────────────

_KEYWORDS_CONFIRMACION = frozenset(
    [
        "acepto",
        "trato cerrado",
        "de acuerdo",
        "confirmado",
        "te envié",
        "enviado",
        "trato hecho",
        "intercambio aceptado",
    ]
)
_KEYWORDS_PROPUESTA = frozenset(
    [
        "te propongo",
        "te ofrezco",
        "a cambio de",
        "quiero cambiar",
        "intercambio",
    ]
)

_CONTEXTO_POR_TIPO: dict[str, str] = {
    "sistema": (
        "Es una notificación automática del sistema (paquete recibido, recursos generados).\n"
        "No requiere respuesta: devuelve SIEMPRE esperar."
    ),
    "confirmacion": (
        "El remitente CONFIRMA que aceptó tu oferta y ya te envió su parte.\n"
        "DEBES devolver 'aceptar' con:\n"
        "- 'envio': el recurso de SOBRAN que habías prometido (indicado en la carta)\n"
        "- 'recibir': el recurso que el remitente acaba de enviarte"
    ),
    "propuesta": (
        "El remitente hace una propuesta concreta de intercambio.\n"
        "Si pide algo de tus SOBRAN a cambio de cualquier cosa → acepta.\n"
        "Si ofrece algo de tus FALTAN → acepta o contra-propón con 'ofrecer'."
    ),
    "general": (
        "Carta general o broadcast. Evalúa si hay oportunidad de intercambio.\n"
        "Si el remitente tiene recursos de tus FALTAN → usa 'ofrecer' con propuesta concreta."
    ),
}


def _clasificar_carta(carta: dict) -> str:
    """Classifie une carta pour sélectionner la stratégie de prompt adaptée.

    Args:
        carta: La carta reçue avec ses champs remi, asunto, cuerpo.

    Returns:
        Type de carta : 'sistema', 'confirmacion', 'propuesta', ou 'general'.
    """
    remi = (carta.get("remi") or "").lower()
    texto = f"{carta.get('asunto', '')} {carta.get('cuerpo', '')}".lower()

    if remi == "sistema":
        return "sistema"
    if any(k in texto for k in _KEYWORDS_CONFIRMACION):
        return "confirmacion"
    if any(k in texto for k in _KEYWORDS_PROPUESTA):
        return "propuesta"
    return "general"


# ── Construction du prompt ─────────────────────────────────────────────────────


def construir_prompt_nueva_carta(
    estado: ButlerState,
    carta: dict,
    en_cooldown: bool = False,
) -> str:
    """Construit le prompt LLM adapté à l'état actuel et au type de carta.

    Pré-calcule FALTAN/SOBRAN pour réduire la charge cognitive du LLM.
    Adapte les instructions selon le type de carta détecté (sistema, confirmacion,
    propuesta, general) et inclut un avertissement cooldown si nécessaire.

    Args:
        estado:      État actuel de l'agent.
        carta:       La carta reçue à traiter.
        en_cooldown: Si True, le LLM doit éviter d'accepter immédiatement.

    Returns:
        Prompt complet prêt à envoyer à Ollama.
    """
    faltan, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)
    tipo = _clasificar_carta(carta)
    remi = carta.get("remi", "?")

    aviso_cooldown = (
        (
            "\n⚠️ MODO ESPERA ACTIVO: Acabamos de enviar propuestas masivas. "
            "NO aceptes todavía. Responde con 'ofrecer' si el trato es interesante.\n"
        )
        if en_cooldown
        else ""
    )

    faltan_str = ", ".join(f"{v} de {k}" for k, v in faltan.items()) or "ninguno"
    sobran_str = ", ".join(f"{v} de {k}" for k, v in sobran.items()) or "ninguno"

    return f"""Eres un agente autónomo llamado "{estado.Alias}" en un sistema de intercambio de recursos.
Tu misión: alcanzar tu objetivo consiguiendo los recursos que te faltan mediante negociación.

## Estado actual
- Recursos: {json.dumps(estado.Recursos)}
- Objetivo: {json.dumps(estado.Objetivo)}
- FALTAN (necesitas conseguir): {faltan_str}
- SOBRAN (puedes ceder): {sobran_str}

## Reglas absolutas
- Solo puedes dar recursos de SOBRAN: {json.dumps(sobran)}
- Nunca ofrezcas recursos de FALTAN
- El oro es moneda universal (nadie lo necesita como objetivo)
{aviso_cooldown}
## Carta recibida (tipo: {tipo})
- De: {remi}
- Asunto: {carta.get("asunto", "")}
- Cuerpo: {carta.get("cuerpo", "")}

## Contexto para este tipo de carta
{_CONTEXTO_POR_TIPO[tipo]}

## Reglas de decisión (por orden de prioridad)
1. Carta de Sistema → esperar
2. Confirmación de intercambio → aceptar (enviar lo prometido, indicado en la carta)
3. Oferta de ≥2 oro por recursos de SOBRAN → aceptar
4. Cualquier trato donde das SOBRAN y recibes algo → aceptar (todo recurso es re-intercambiable)
5. Remitente menciona tener recursos de FALTAN → ofrecer con propuesta concreta
6. Solo pide sin ofrecer nada → esperar
7. NUNCA envíes recursos de FALTAN

## Formato de respuesta (JSON estricto, sin texto adicional)
{{"accion":"esperar"}}
{{"accion":"ofrecer","dest":"{remi}","asunto":"...","cuerpo":"Te propongo: te doy N de [SOBRAN] a cambio de M de [recurso]."}}
{{"accion":"aceptar","dest":"{remi}","envio":{{"recurso":cantidad}},"recibir":{{"recurso":cantidad}}}}

Ejemplo aceptar confirmación: {{"accion":"aceptar","dest":"{remi}","envio":{{"arroz":1}},"recibir":{{"madera":1}}}}

Devuelve SOLO el JSON."""


# ── Consultation Ollama ────────────────────────────────────────────────────────


def consultar_ollama(prompt: str) -> dict:
    """Envoie le prompt à Ollama et parse la décision JSON.

    Tente d'abord un json.loads direct. En cas d'échec (texte autour du JSON,
    markdown code blocks, etc.), extrait le premier objet JSON via regex.
    Retourne {"accion": "esperar"} en cas d'échec total (fallback sûr).

    Args:
        prompt: Le prompt complet à envoyer au modèle.

    Returns:
        Dictionnaire JSON représentant la décision du LLM.
    """
    logger.debug("Consultando Ollama...")
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    ).json()

    texto = response.get("response", "").strip()
    logger.info("Ollama → %s", texto)

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]+\}", texto)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("JSON inválido del LLM. Fallback a esperar.")
        return {"accion": "esperar"}
