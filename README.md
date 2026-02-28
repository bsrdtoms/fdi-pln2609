# fdi-pln-2609-p1 — Agent "lobo leal"

Autonomous resource exchange agent — Práctica 1, PLN (Natural Language Processing)

> 🌐 [Lire en français](README.fr.md) | [Leer en español](README.es.md)

## Team

| Name | Work |
|------|------|
| Thomas BOSSARD | Full agent development |

## Description

Autonomous agent participating in a multi-agent resource exchange system. Each agent holds resources and has an objective (a set of resources to reach). Agents communicate via a central **Butler** server by exchanging *cartas* (messages) and *paquetes* (resource transfers).

A local LLM (qwen2.5-coder:3b via Ollama) automatically decides how to respond to incoming exchange proposals.

## Architecture

```
config.py  — Constants and data model (ButlerState)
butler.py  — HTTP client to Butler (data access)
agent.py   — Business logic (FALTAN/SOBRAN calculations, validation, broadcasts)
llm.py     — Prompts and Ollama interface (negotiation decisions)
app.py     — FastAPI orchestration (polling, broadcasts, endpoints)
main.py    — Entry point
```

## Getting started

```bash
# Prerequisite: Ollama with qwen2.5-coder:3b
ollama pull qwen2.5-coder:3b

# Start the agent (Butler must be reachable)
FDI_PLN__BUTLER_ADDRESS=http://<butler_host>:7719 uv run fdi-pln-2609-p1
```

## Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `FDI_PLN__BUTLER_ADDRESS` | `http://127.0.0.1:7719` | Butler server URL |

Internal parameters in `config.py`:

| Variable | Value | Description |
|----------|-------|-------------|
| `MODEL` | `qwen2.5-coder:3b` | Ollama model |
| `POLL_INTERVAL` | `10s` | Mailbox polling interval |
| `BROADCAST_INTERVAL` | `300s` | Interval between periodic broadcasts |
| `ACCEPT_COOLDOWN` | `60s` | Delay before accepting after a 1:1 broadcast |

## Agent endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/broadcast` | Triggers a broadcast to all agents |
| POST | `/aceptar/{dest}` | Manually accepts an exchange |

## Negotiation strategy

1. On startup: general broadcast + 1:1 proposals + purchases with oro
2. Polling every 10s: detection of new cartas
3. For each carta: classification (sistema / confirmacion / propuesta / general)
4. Contextualised LLM prompt → JSON decision (`esperar` / `ofrecer` / `aceptar`)
5. Send validation (safety net against LLM hallucinations)
6. Automatic broadcast after each accepted exchange
