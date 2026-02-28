# fdi-pln-2609-p1 — Agent « lobo leal »

Agent autonome d'échange de ressources — Práctica 1, PLN (Traitement du langage naturel)

> 🌐 [Read in English](README.md) | [Leer en español](README.es.md)

## Équipe

| Nom | Travail |
|-----|---------|
| Thomas BOSSARD | Développement complet de l'agent |

## Description

Agent autonome participant à un système multi-agents d'échange de ressources. Chaque agent possède des ressources et un objectif (un ensemble de ressources à atteindre). Les agents communiquent via un serveur central **Butler** en s'envoyant des *cartas* (messages) et des *paquetes* (transferts de ressources).

Un LLM local (qwen2.5-coder:3b via Ollama) décide automatiquement comment répondre aux propositions d'échange reçues.

## Architecture

```
config.py  — Constantes et modèle de données (ButlerState)
butler.py  — Client HTTP vers Butler (accès aux données)
agent.py   — Logique métier (calculs FALTAN/SOBRAN, validation, broadcasts)
llm.py     — Prompts et interface Ollama (décisions de négociation)
app.py     — Orchestration FastAPI (polling, broadcasts, endpoints)
main.py    — Point d'entrée
```

## Lancement

```bash
# Prérequis : Ollama avec qwen2.5-coder:3b
ollama pull qwen2.5-coder:3b

# Lancer l'agent (Butler doit être accessible)
FDI_PLN__BUTLER_ADDRESS=http://<butler_host>:7719 uv run fdi-pln-2609-p1
```

## Configuration

| Variable d'environnement | Défaut | Description |
|--------------------------|--------|-------------|
| `FDI_PLN__BUTLER_ADDRESS` | `http://127.0.0.1:7719` | URL du serveur Butler |

Paramètres internes dans `config.py` :

| Variable | Valeur | Description |
|----------|--------|-------------|
| `MODEL` | `qwen2.5-coder:3b` | Modèle Ollama |
| `POLL_INTERVAL` | `10s` | Intervalle de polling du buzon |
| `BROADCAST_INTERVAL` | `300s` | Intervalle entre broadcasts périodiques |
| `ACCEPT_COOLDOWN` | `60s` | Délai avant d'accepter après un broadcast 1:1 |

## Endpoints de l'agent

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/broadcast` | Déclenche un broadcast vers tous les agents |
| POST | `/aceptar/{dest}` | Accepte manuellement un échange |

## Stratégie de négociation

1. Au démarrage : attente de Butler → marque les cartas existantes comme vues → broadcast général + propositions 1:1 + achats avec oro
2. Après le broadcast 1:1 : **cooldown de 60s** — le LLM est averti de ne pas accepter immédiatement (évite le sur-engagement de ressources)
3. Polling toutes les 10s : détection des nouvelles cartas
4. Pour chaque carta : classification (`sistema` / `confirmacion` / `propuesta` / `general`)
5. Prompt LLM contextualisé → décision JSON (`esperar` / `ofrecer` / `pedir` / `aceptar`)
6. Validation des envois (filet de sécurité contre les hallucinations du LLM)
7. Re-broadcast complet automatique après chaque échange accepté
