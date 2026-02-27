"""
config.py — Configuration globale et modèle de données partagé.

Point d'entrée unique pour toutes les constantes et le modèle ButlerState,
importé par tous les autres modules sans créer de cycles.
"""

import os

from pydantic import BaseModel

# — Serveur Butler ——————————————————————————————————————————————————————————————
BUTLER_BASE_URL: str = os.environ.get("FDI_PLN__BUTLER_ADDRESS", "http://127.0.0.1:7719")
AGENTE_SLOT: str = "lobo_leal"  # Identifiant de slot pour le mode monopuesto

# — Modèle LLM local (Ollama) ——————————————————————————————————————————————————
OLLAMA_URL: str = "http://127.0.0.1:11434/api/generate"
MODEL: str = "qwen2.5-coder:3b"

# — Intervalles de temps (en secondes) ————————————————————————————————————————
POLL_INTERVAL: int = 10        # Entre chaque vérification du buzón
BROADCAST_INTERVAL: int = 300  # Entre chaque broadcast périodique (5 min)
ACCEPT_COOLDOWN: int = 60      # Attente avant d'accepter après un broadcast 1:1


class ButlerState(BaseModel):
    """État complet de l'agent, retourné par l'endpoint /info de Butler."""

    Alias: str = ""
    Recursos: dict
    Objetivo: dict
    Buzon: dict | None = None
