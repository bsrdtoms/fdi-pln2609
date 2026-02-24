"""
agent.py — Logique métier de l'agent (IA classique : validation, décisions, broadcasts).

Ce module contient toutes les règles de gestion des ressources :
calcul des manques/surplus, validation des envois, exécution des décisions
LLM et composition des messages de broadcast.

Il ne fait aucun appel direct à Ollama (délégué à llm.py) et ne connaît
pas FastAPI (délégué à app.py).
"""

import json
import logging

from config import ButlerState
from butler import enviar_carta, enviar_paquete

logger = logging.getLogger(__name__)


# ── Calcul des ressources ──────────────────────────────────────────────────────

def calcular_faltan_sobran(recursos: dict, objetivo: dict) -> tuple[dict, dict]:
    """Calcule les ressources manquantes et excédentaires.

    Args:
        recursos: Ressources actuellement possédées.
        objetivo: Objectif à atteindre.

    Returns:
        Tuple (faltan, sobran) où :
        - faltan = ressources à acquérir pour atteindre l'objectif
        - sobran = ressources disponibles au-delà de l'objectif (échangeables)
    """
    faltan = {
        rec: cant - recursos.get(rec, 0)
        for rec, cant in objetivo.items()
        if cant > recursos.get(rec, 0)
    }
    sobran = {
        rec: cant - objetivo.get(rec, 0)
        for rec, cant in recursos.items()
        if cant > objetivo.get(rec, 0) or rec not in objetivo
    }
    return faltan, sobran


# ── Validation et exécution ────────────────────────────────────────────────────

def validar_envio(envio: dict, estado: ButlerState) -> dict | None:
    """Valide et plafonne un envoi proposé contre les ressources réellement disponibles.

    Filet de sécurité contre les hallucinations LLM : même si le LLM propose
    un envoi invalide, cette fonction le bloque ou le corrige silencieusement.

    Args:
        envio:  Dictionnaire {ressource: quantité} proposé par le LLM.
        estado: État courant de l'agent (déjà récupéré par l'appelant, sans re-fetch HTTP).

    Returns:
        Dictionnaire des quantités réellement envoyables, ou None si rien n'est valide.
    """
    _, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)
    envio_valido = {
        rec: min(cant, sobran[rec])
        for rec, cant in envio.items()
        if isinstance(cant, int) and cant > 0 and sobran.get(rec, 0) > 0
    }
    return envio_valido or None


def ejecutar_decision(decision: dict, mi_alias: str, estado: ButlerState) -> dict:
    """Exécute la décision prise par le LLM.

    Dispatche selon l'action :
    - 'esperar'         : ne fait rien
    - 'ofrecer'/'pedir' : envoie une carta de négociation
    - 'aceptar'         : valide l'envoi, envoie le paquet + carta de confirmation

    Args:
        decision: Dictionnaire JSON produit par le LLM.
        mi_alias: Alias de cet agent.
        estado:   État courant (transmis à validar_envio sans re-fetch HTTP).

    Returns:
        Dictionnaire de résultat, ex: {"estado": "aceptado_y_enviado", "paquete": {...}}
    """
    accion = decision.get("accion")
    logger.info("Ejecutando: %s", decision)

    if accion == "esperar":
        return {"estado": "esperando"}

    dest = decision.get("dest", "")

    if accion == "aceptar" and dest:
        envio_valido = validar_envio(decision.get("envio", {}), estado)
        if envio_valido:
            recibir = decision.get("recibir", {})
            recibir_txt = f" Espero recibir: {json.dumps(recibir)}." if recibir else ""
            enviar_paquete(dest, envio_valido)
            enviar_carta(
                remi=mi_alias, dest=dest, asunto="Intercambio aceptado",
                cuerpo=(
                    f"Acepto el trato. Te envié: {json.dumps(envio_valido)}.{recibir_txt}"
                    " Envíame tu parte si aún no lo has hecho."
                ),
            )
            return {"estado": "aceptado_y_enviado", "paquete": envio_valido}
        logger.warning("Envío bloqueado: %s no disponible en SOBRAN", decision.get("envio"))
        return {"estado": "envio_bloqueado"}

    if accion in ("pedir", "ofrecer") and dest and decision.get("cuerpo"):
        enviar_carta(
            remi=mi_alias, dest=dest,
            asunto=decision.get("asunto", "Propuesta de intercambio"),
            cuerpo=decision["cuerpo"],
        )
        return {"estado": f"{accion}_enviado"}

    logger.warning("Acción inválida o campos faltantes: %s", decision)
    return {"estado": "esperando"}


# ── Broadcasts ─────────────────────────────────────────────────────────────────

def hacer_broadcast_general(estado: ButlerState, otros: list[str]) -> list[str]:
    """Envoie une carta d'annonce générale (besoins/offres) à tous les agents.

    Args:
        estado: État courant (pré-chargé par l'appelant).
        otros:  Liste des alias des autres agents.

    Returns:
        Liste des alias auxquels la carta a été envoyée.
    """
    alias = estado.Alias or "agente"
    faltan, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)
    cuerpo = (
        f"Hola, soy {alias}.\n"
        f"Necesito: {', '.join(f'{v} de {k}' for k, v in faltan.items())}.\n"
        f"Ofrezco a cambio: {', '.join(f'{v} de {k}' for k, v in sobran.items())}.\n"
        "Si te interesa, propón un intercambio concreto."
    )
    for dest in otros:
        enviar_carta(remi=alias, dest=dest, asunto="Busco intercambio", cuerpo=cuerpo)
    logger.info("Broadcast general: %d cartas enviadas.", len(otros))
    return otros


def hacer_broadcast_propuestas_1a1(estado: ButlerState, otros: list[str]) -> int:
    """Envoie des propositions d'échange 1:1 (1 SOBRAN contre 1 FALTAN) à tous les agents.

    Pour chaque paire (ressource_à_donner × ressource_voulue), envoie une carta
    individuelle à chaque agent. Le cooldown doit être mis à jour par l'appelant
    (app.py) après cet appel.

    Args:
        estado: État courant (pré-chargé par l'appelant).
        otros:  Liste des alias des autres agents.

    Returns:
        Nombre de cartas envoyées (0 si rien à proposer).
    """
    alias = estado.Alias or "agente"
    faltan, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)

    if not faltan or not sobran:
        logger.info("Broadcast 1:1 omis : rien à proposer.")
        return 0

    count = 0
    for rec_dar, cant_dar in sobran.items():
        for rec_recibir in faltan:
            asunto = f"Oferta: 1 {rec_dar} por 1 {rec_recibir}"
            cuerpo = (
                f"Hola, soy {alias}.\n"
                f"Te propongo: te doy 1 de {rec_dar} a cambio de 1 de {rec_recibir}.\n"
                f"Tengo {cant_dar} de {rec_dar} disponibles.\n"
                f"Si aceptas, envíame 1 de {rec_recibir} y yo te envío 1 de {rec_dar}."
            )
            for dest in otros:
                enviar_carta(remi=alias, dest=dest, asunto=asunto, cuerpo=cuerpo)
                count += 1

    logger.info("Broadcast 1:1: %d cartas enviadas.", count)
    return count


def hacer_broadcast_compras_con_oro(estado: ButlerState, otros: list[str]) -> int:
    """Propose d'acheter chaque ressource manquante pour 3 oro.

    L'or est une monnaie universelle : personne n'en a besoin dans son objectif,
    donc tout le monde est prêt à en recevoir en échange de leurs surplus.

    Args:
        estado: État courant (pré-chargé par l'appelant).
        otros:  Liste des alias des autres agents.

    Returns:
        Nombre de cartas envoyées (0 si pas assez d'oro ou rien à acheter).
    """
    alias = estado.Alias or "agente"
    faltan, sobran = calcular_faltan_sobran(estado.Recursos, estado.Objetivo)
    oro_disponible = sobran.get("oro", 0)

    if not faltan or oro_disponible < 3:
        logger.info("Broadcast oro omis : pas assez d'oro ou rien à acheter.")
        return 0

    count = 0
    for rec_faltan in faltan:
        asunto = f"Compro: 1 {rec_faltan} por 3 oro"
        cuerpo = (
            f"Hola, soy {alias}.\n"
            f"Compro 1 de {rec_faltan} a cambio de 3 de oro.\n"
            f"Tengo {oro_disponible} de oro disponibles.\n"
            f"Si aceptas, envíame 1 de {rec_faltan} y yo te envío 3 de oro inmediatamente."
        )
        for dest in otros:
            enviar_carta(remi=alias, dest=dest, asunto=asunto, cuerpo=cuerpo)
            count += 1

    logger.info("Broadcast oro: %d cartas enviadas.", count)
    return count
