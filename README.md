# Agente 51 - "lobo leal"

Agent autonome d'echange de ressources pour le TP FDI (Fundamentos de la Informatica).

## Description

Ce projet est un agent autonome qui participe a un systeme multi-agents d'echange de ressources. Chaque agent possede des ressources et un objectif (ensemble de ressources a atteindre). Les agents communiquent entre eux via un serveur central appele **Butler** en s'envoyant des *cartas* (messages) et des *paquetes* (envois de ressources).

L'agent utilise un LLM local (Mistral via Ollama) pour decider automatiquement comment repondre aux propositions d'echange recues.

## Architecture

```
+------------------+       +------------------+       +------------------+
|   Notre Agent    | <---> |   Butler Server   | <---> |  Autres Agents   |
|   (FastAPI)      |       | 147.96.81.252:7719|       |                  |
|   port 8080      |       +------------------+       +------------------+
|                  |
|  polling_loop()  |       +------------------+
|  (thread bg)     | <---> |   Ollama (local)  |
+------------------+       |   Mistral 7B      |
                           |   port 11434      |
                           +------------------+
```

### Flux principal

1. Le **polling_loop** (thread en arriere-plan) interroge `/info` sur Butler toutes les 10 secondes
2. Les nouvelles cartas (non encore vues) sont detectees par comparaison d'IDs
3. Chaque nouvelle carta est envoyee au LLM avec un prompt contextualisé (etat, ressources, objectif)
4. Le LLM repond avec un JSON : `esperar`, `ofrecer`, ou `aceptar`
5. La decision est executee : envoi de carta et/ou paquete

### Validation des envois

Avant d'envoyer un paquete, `validar_envio()` verifie que :
- Les ressources proposees font partie des **SOBRAN** (surplus, non necessaires a l'objectif)
- Les quantites ne depassent pas ce qui est disponible
- Cela empeche le LLM d'envoyer des ressources dont on a besoin

## Endpoints API

| Methode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/broadcast` | Envoie un message de presentation a tous les agents |
| POST | `/aceptar/{dest}` | Accepte un echange manuellement : envoie un paquete + carta de confirmation |

## API Butler

| Methode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/info` | Retourne l'alias, ressources, objectif et buzon (boite aux lettres) |
| GET | `/gente` | Liste tous les agents inscrits |
| POST | `/carta` | Envoie une carta (message) a un autre agent |
| POST | `/paquete/{dest}` | Envoie des ressources a un autre agent |
| GET | `/dashboard` | Dashboard web du systeme |

## Prerequis

- Python 3.12+
- Ollama avec le modele Mistral

## Installation

```bash
# Installer les dependances Python
uv sync

# Installer Ollama (sans sudo)
curl -L https://ollama.com/download/ollama-linux-amd64.tgz | tar xz -C ~/.local/

# Telecharger le modele Mistral
~/.local/bin/ollama pull mistral
```

## Lancement

```bash
# 1. Lancer Ollama en arriere-plan
~/.local/bin/ollama serve &

# 2. Lancer l'agent
uv run uvicorn app:app --host 0.0.0.0 --port 8080

# 3. (Optionnel) Envoyer un broadcast initial
curl -X POST http://localhost:8080/broadcast
```

## Configuration

Variables en haut de `app.py` :

| Variable | Valeur | Description |
|----------|--------|-------------|
| `OLLAMA_URL` | `http://127.0.0.1:11434/api/generate` | URL de l'API Ollama |
| `BUTLER_BASE_URL` | `http://147.96.81.252:7719` | URL du serveur Butler |
| `MODEL` | `mistral` | Modele LLM utilise |
| `POLL_INTERVAL` | `10` | Intervalle de polling en secondes |

## Logs

Le dossier `logs/` contient les logs des sessions precedentes :
- `generate_session.log` : premiere session avec le endpoint `/generate` (obsolete)
- `server_polling_session1.log` : session de polling avec tentative d'echange avec garibaldi
- `server_polling_session2.log` : session de polling avec les cartas de AmarNoEsDelito, burrito sabanero, etc.
