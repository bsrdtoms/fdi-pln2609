# fdi-pln-2609-p1 — Agente "lobo leal"

Agent autonome d'echange de ressources — Práctica 1, PLN (Procesamiento de Lenguaje Natural)

## Equipo

| Nombre | Trabajo |
|--------|---------|
| Thomas BOSSARD | Desarrollo completo del agente |

## Description

Agent autonome qui participe a un systeme multi-agents d'echange de ressources. Chaque agent possede des ressources et un objectif (ensemble de ressources a atteindre). Les agents communiquent via un serveur central **Butler** en s'envoyant des *cartas* (messages) et des *paquetes* (transferts de ressources).

Le LLM local (qwen2.5-coder:3b via Ollama) decide automatiquement comment repondre aux propositions d'echange recues.

## Architecture

```
config.py  — Constantes et modele de donnees (ButlerState)
butler.py  — Client HTTP vers Butler (acces aux donnees)
agent.py   — Logique metier (calculs FALTAN/SOBRAN, validation, broadcasts)
llm.py     — Prompts et interface Ollama (decisions de negociation)
app.py     — Orchestration FastAPI (polling, broadcasts, endpoints)
main.py    — Point d'entree
```

## Lancement

```bash
# Prerequis : Ollama avec qwen2.5-coder:3b
ollama pull qwen2.5-coder:3b

# Lancer l'agent (Butler doit etre accessible)
FDI_PLN__BUTLER_ADDRESS=http://<butler_host>:7719 uv run fdi-pln-2609-p1
```

## Configuration

| Variable d'environnement | Defaut | Description |
|--------------------------|--------|-------------|
| `FDI_PLN__BUTLER_ADDRESS` | `http://127.0.0.1:7719` | URL du serveur Butler |

Parametres internes dans `config.py` :

| Variable | Valeur | Description |
|----------|--------|-------------|
| `MODEL` | `qwen2.5-coder:3b` | Modele Ollama |
| `POLL_INTERVAL` | `10s` | Intervalle de polling du buzon |
| `BROADCAST_INTERVAL` | `300s` | Intervalle entre broadcasts periodiques |
| `ACCEPT_COOLDOWN` | `60s` | Delai avant d'accepter apres un broadcast 1:1 |

## Endpoints de l'agent

| Methode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/broadcast` | Declenche un broadcast vers tous les agents |
| POST | `/aceptar/{dest}` | Accepte manuellement un echange |

## Strategie de negociation

1. Au demarrage : broadcast general + propositions 1:1 + achats avec oro
2. Polling toutes les 10s : detection des nouvelles cartas
3. Pour chaque carta : classification (sistema / confirmacion / propuesta / general)
4. Prompt LLM contextualise → decision JSON (`esperar` / `ofrecer` / `aceptar`)
5. Validation des envois (filet de securite contre les hallucinations LLM)
6. Broadcast automatique apres chaque echange accepte
