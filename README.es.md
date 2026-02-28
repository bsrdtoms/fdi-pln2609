# fdi-pln-2609-p1 — Agente "lobo leal"

Agente autónomo de intercambio de recursos — Práctica 1, PLN (Procesamiento del Lenguaje Natural)

> 🌐 [Read in English](README.md) | [Lire en français](README.fr.md)

## Equipo

| Nombre | Trabajo |
|--------|---------|
| Thomas BOSSARD | Desarrollo completo del agente |

## Descripción

Agente autónomo que participa en un sistema multiagente de intercambio de recursos. Cada agente posee recursos y un objetivo (un conjunto de recursos a alcanzar). Los agentes se comunican a través de un servidor central **Butler** enviándose *cartas* (mensajes) y *paquetes* (transferencias de recursos).

Un LLM local (qwen2.5-coder:3b vía Ollama) decide automáticamente cómo responder a las propuestas de intercambio recibidas.

## Arquitectura

```
config.py  — Constantes y modelo de datos (ButlerState)
butler.py  — Cliente HTTP hacia Butler (acceso a datos)
agent.py   — Lógica de negocio (cálculos FALTAN/SOBRAN, validación, broadcasts)
llm.py     — Prompts e interfaz Ollama (decisiones de negociación)
app.py     — Orquestación FastAPI (polling, broadcasts, endpoints)
main.py    — Punto de entrada
```

## Puesta en marcha

```bash
# Prerequisito: Ollama con qwen2.5-coder:3b
ollama pull qwen2.5-coder:3b

# Lanzar el agente (Butler debe ser accesible)
FDI_PLN__BUTLER_ADDRESS=http://<butler_host>:7719 uv run fdi-pln-2609-p1
```

## Configuración

| Variable de entorno | Por defecto | Descripción |
|---------------------|-------------|-------------|
| `FDI_PLN__BUTLER_ADDRESS` | `http://127.0.0.1:7719` | URL del servidor Butler |

Parámetros internos en `config.py`:

| Variable | Valor | Descripción |
|----------|-------|-------------|
| `MODEL` | `qwen2.5-coder:3b` | Modelo Ollama |
| `POLL_INTERVAL` | `10s` | Intervalo de polling del buzón |
| `BROADCAST_INTERVAL` | `300s` | Intervalo entre broadcasts periódicos |
| `ACCEPT_COOLDOWN` | `60s` | Retardo antes de aceptar tras un broadcast 1:1 |

## Endpoints del agente

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/broadcast` | Lanza un broadcast a todos los agentes |
| POST | `/aceptar/{dest}` | Acepta manualmente un intercambio |

## Estrategia de negociación

1. Al arrancar: espera a Butler → marca las cartas existentes como vistas → broadcast general + propuestas 1:1 + compras con oro
2. Tras el broadcast 1:1: **cooldown de 60s** — el LLM recibe aviso de no aceptar inmediatamente (evita el sobrecompromiso de recursos)
3. Polling cada 10s: detección de nuevas cartas
4. Para cada carta: clasificación (`sistema` / `confirmacion` / `propuesta` / `general`)
5. Prompt LLM contextualizado → decisión JSON (`esperar` / `ofrecer` / `pedir` / `aceptar`)
6. Validación de envíos (red de seguridad contra alucinaciones del LLM)
7. Re-broadcast completo automático tras cada intercambio aceptado
