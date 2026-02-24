"""
app.py — Orquestación: polling, broadcasts y endpoints FastAPI.

Agente autónomo de intercambio de recursos — FDI (Fundamentos de la Informática)

Arquitectura modular:
  config.py — Constantes y modelo de datos compartido
  butler.py — Cliente HTTP de Butler    (IA clásica: capa de acceso a datos)
  agent.py  — Lógica de negocio         (IA clásica: validación y decisiones)
  llm.py    — Prompts y consultas Ollama (IA moderna: negociación con LLM)
  app.py    — Orquestación: polling, broadcasts y endpoints FastAPI
"""

import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

import agent
import butler
import llm
from config import ACCEPT_COOLDOWN, BROADCAST_INTERVAL, POLL_INTERVAL

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── État global du polling ────────────────────────────────────────────────────
cartas_vistas: set[str] = set()        # IDs des cartas déjà traitées
broadcast_cooldown_until: float = 0.0  # Timestamp : n'accepte pas avant cette heure


# ── Orchestration des broadcasts ──────────────────────────────────────────────

def hacer_broadcast_completo() -> None:
    """Exécute le cycle complet de broadcast : général + 1:1 + achats oro.

    Récupère l'état et la liste des agents UNE SEULE FOIS, puis délègue
    aux fonctions de broadcast dans agent.py. Met à jour le cooldown global
    après le broadcast 1:1 pour éviter les sur-engagements de ressources.
    """
    global broadcast_cooldown_until
    estado = butler.obtener_estado()
    otros  = butler.obtener_otros_agentes(estado.Alias)

    agent.hacer_broadcast_general(estado, otros)
    agent.hacer_broadcast_propuestas_1a1(estado, otros)
    broadcast_cooldown_until = time.time() + ACCEPT_COOLDOWN  # cooldown après 1:1
    agent.hacer_broadcast_compras_con_oro(estado, otros)

    logger.info("Broadcast completo enviado a %d agentes.", len(otros))


# ── Traitement des cartas ──────────────────────────────────────────────────────

def _procesar_carta(estado, carta: dict) -> None:
    """Traite une seule carta : prompt → LLM → décision → exécution.

    Si la décision est 'aceptar', déclenche un re-broadcast pour mettre
    à jour les propositions avec les ressources actualisées post-échange.

    Args:
        estado: État déjà récupéré par le polling_loop (pas de re-fetch HTTP).
        carta:  La carta à traiter.
    """
    timestamp   = datetime.now().strftime("%H:%M:%S")
    en_cooldown = time.time() < broadcast_cooldown_until

    logger.info("[%s] CARTA de '%s' | %s", timestamp, carta.get("remi"), carta.get("asunto"))
    logger.info("  Cuerpo: %s", str(carta.get("cuerpo", ""))[:120])
    if en_cooldown:
        logger.info("  [cooldown] %ds restantes", int(broadcast_cooldown_until - time.time()))

    prompt    = llm.construir_prompt_nueva_carta(estado, carta, en_cooldown=en_cooldown)
    decision  = llm.consultar_ollama(prompt)
    resultado = agent.ejecutar_decision(decision, estado.Alias or "agente", estado)

    logger.info("  → %s", resultado)

    if resultado.get("estado") == "aceptado_y_enviado":
        logger.info("Post-accept: re-broadcast avec ressources mises à jour.")
        try:
            hacer_broadcast_completo()
        except Exception as e:
            logger.error("Erreur re-broadcast post-accept: %s", e)


# ── Boucle de polling ──────────────────────────────────────────────────────────

def polling_loop() -> None:
    """Boucle principale du daemon de polling.

    1. Attend que Butler soit accessible au démarrage (retry toutes les 5s).
    2. Marque les cartas existantes comme déjà vues (évite de les retraiter).
    3. Envoie les broadcasts initiaux.
    4. Toutes les POLL_INTERVAL secondes : détecte et traite les nouvelles cartas.
    5. Toutes les BROADCAST_INTERVAL secondes : re-broadcast périodique.
    """
    logger.info("Polling démarré.")

    # Attente de Butler
    while True:
        try:
            estado = butler.obtener_estado()
            for carta_id in (estado.Buzon or {}):
                cartas_vistas.add(carta_id)
            logger.info("Butler connecté. %d cartas existantes ignorées.", len(cartas_vistas))
            break
        except Exception:
            logger.warning("Butler non disponible, retry dans 5s...")
            time.sleep(5)

    # Broadcasts initiaux
    try:
        hacer_broadcast_completo()
    except Exception as e:
        logger.error("Erreur broadcast initial: %s", e)

    ultimo_broadcast = time.time()

    # Boucle principale
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            # Broadcast périodique
            if time.time() - ultimo_broadcast >= BROADCAST_INTERVAL:
                logger.info("Broadcast périodique...")
                try:
                    hacer_broadcast_completo()
                    ultimo_broadcast = time.time()
                except Exception as e:
                    logger.error("Erreur broadcast périodique: %s", e)

            # Détection des nouvelles cartas
            estado = butler.obtener_estado()
            nuevas = {
                cid: carta
                for cid, carta in (estado.Buzon or {}).items()
                if cid not in cartas_vistas
            }
            if nuevas:
                logger.info("%d nouvelle(s) carta(s) détectée(s).", len(nuevas))
                for cid, carta in nuevas.items():
                    cartas_vistas.add(cid)
                    _procesar_carta(estado, carta)

        except Exception as e:
            logger.error("Erreur polling: %s", e)


# ── FastAPI ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
    yield


app = FastAPI(
    title="Agente de intercambio de recursos",
    description="Agent autonome FDI — architecture modulaire Butler / Agent / LLM",
    lifespan=lifespan,
)


@app.post("/broadcast")
def broadcast() -> dict:
    """Déclenche manuellement un cycle complet de broadcast vers tous les agents."""
    hacer_broadcast_completo()
    return {"status": "broadcast envoyé"}


@app.post("/aceptar/{dest}")
def aceptar(dest: str, envio: dict) -> dict:
    """Accepte manuellement un échange : envoie un paquet et une carta de confirmation."""
    estado = butler.obtener_estado()
    alias  = estado.Alias or "agente"

    for rec, cant in envio.items():
        if estado.Recursos.get(rec, 0) < cant:
            return {"error": f"No tienes suficiente {rec} (tienes {estado.Recursos.get(rec, 0)})"}

    butler.enviar_paquete(dest, envio)
    butler.enviar_carta(
        remi=alias, dest=dest, asunto="Intercambio aceptado",
        cuerpo=f"Acepto el trato. Te envié: {json.dumps(envio)}. Envíame tu parte si aún no lo has hecho.",
    )
    return {"estado": "aceptado_y_enviado", "dest": dest, "paquete": envio}
