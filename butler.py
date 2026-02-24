"""
butler.py — Couche réseau vers le serveur Butler (IA classique : accès aux données).

Ce module est la seule source de vérité pour les appels HTTP vers Butler.
Il ne contient aucune logique métier : il reçoit des paramètres, exécute
une requête HTTP et retourne le résultat brut ou lève une exception.
"""

import logging

import requests

from config import BUTLER_BASE_URL, ButlerState

logger = logging.getLogger(__name__)


def obtener_estado() -> ButlerState:
    """Récupère l'état courant de l'agent depuis l'endpoint /info de Butler.

    Returns:
        ButlerState avec les ressources, l'objectif et le buzón actuel.

    Raises:
        requests.RequestException: Si Butler est inaccessible.
    """
    r = requests.get(f"{BUTLER_BASE_URL}/info", timeout=10)
    r.raise_for_status()
    return ButlerState(**r.json())


def obtener_otros_agentes(mi_alias: str) -> list[str]:
    """Retourne la liste des alias de tous les autres agents actifs.

    Args:
        mi_alias: L'alias de cet agent, exclu de la liste retournée.

    Returns:
        Liste des alias. Retourne [] en cas d'erreur réseau.
    """
    try:
        r = requests.get(f"{BUTLER_BASE_URL}/gente", timeout=10)
        r.raise_for_status()
        return [
            g.get("Alias", g.get("alias", ""))
            for g in r.json()
            if g.get("Alias", g.get("alias", "")) != mi_alias
        ]
    except Exception as e:
        logger.error("Error obteniendo agentes: %s", e)
        return []


def enviar_carta(remi: str, dest: str, asunto: str, cuerpo: str) -> None:
    """Envoie une carta (lettre) à un agent via Butler.

    Args:
        remi:   Alias de l'expéditeur.
        dest:   Alias du destinataire.
        asunto: Objet de la carta.
        cuerpo: Corps de la carta.
    """
    logger.info("CARTA → %s | %s", dest, asunto)
    r = requests.post(
        f"{BUTLER_BASE_URL}/carta",
        json={"remi": remi, "dest": dest, "asunto": asunto, "cuerpo": cuerpo},
        timeout=10,
    )
    logger.debug("Butler: %s %s", r.status_code, r.text)


def enviar_paquete(dest: str, recursos: dict) -> None:
    """Envoie un paquet de ressources à un agent via Butler.

    Args:
        dest:     Alias du destinataire.
        recursos: Dictionnaire {ressource: quantité} à transférer.
    """
    logger.info("PAQUETE → %s: %s", dest, recursos)
    r = requests.post(
        f"{BUTLER_BASE_URL}/paquete/{dest}",
        json=recursos,
        timeout=10,
    )
    logger.debug("Butler: %s %s", r.status_code, r.text)
