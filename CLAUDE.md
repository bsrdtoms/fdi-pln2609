# CLAUDE.md - Contexte du projet pour Claude Code

## Qu'est-ce que ce projet ?

Agent autonome d'echange de ressources pour un TP universitaire (FDI - Fundamentos de la Informatica). L'agent s'appelle "lobo leal" et participe a un systeme multi-agents ou chaque agent doit atteindre un objectif de ressources en negociant avec les autres.

## Stack technique

- **FastAPI** : serveur web avec lifespan events
- **Ollama** : serveur LLM local (Mistral 7B)
- **Butler** : serveur central d'echange a `http://147.96.81.252:7719`
- **uv** : gestionnaire de paquets Python

## Fichiers importants

- `app.py` : tout le code de l'agent (polling, LLM, envois)
- `pyproject.toml` : dependances (fastapi, requests, uvicorn, ruff)
- `logs/` : logs des sessions precedentes

## Comment ca marche

### Boucle principale (polling_loop)
- Thread daemon lance au demarrage via FastAPI lifespan
- Interroge `/info` sur Butler toutes les 10 secondes
- Detecte les nouvelles cartas par comparaison d'IDs (`cartas_vistas` set)
- Envoie chaque nouvelle carta au LLM une par une (pas tout le buzon)

### Prompt LLM
- Pre-calcule FALTAN (ce qu'on a besoin) et SOBRAN (ce qu'on peut donner)
- Donne au LLM uniquement la carta courante + etat actuel
- Demande un JSON strict : `esperar`, `ofrecer`, ou `aceptar`
- "REGLA ABSOLUTA" pour empecher le LLM d'offrir des ressources qu'on n'a pas

### Validation (validar_envio)
- Filet de securite : verifie que les ressources a envoyer sont dans SOBRAN
- Plafonne les quantites au disponible
- Bloque les envois invalides meme si le LLM les demande

## Problemes connus

- **Mistral trop passif** : repond souvent "esperar" meme quand il pourrait negocier
- **Hallucinations LLM** : parfois le LLM propose des ressources qu'on n'a pas dans le texte des cartas (mais validar_envio bloque les envois reels)
- **JSON invalide** : Mistral genere parfois du texte apres le JSON, le fallback est "esperar"
- **Butler offline** : quand le serveur Butler tombe, le polling log des erreurs de connexion en boucle

## Commandes utiles

```bash
# Lancer Ollama
~/.local/bin/ollama serve &

# Lancer l'agent
uv run uvicorn app:app --host 0.0.0.0 --port 8080

# Broadcast a tous les agents
curl -X POST http://localhost:8080/broadcast

# Accepter manuellement un echange
curl -X POST http://localhost:8080/aceptar/nomAgent -H "Content-Type: application/json" -d '{"piedra": 1}'

# Verifier l'etat courant
curl http://147.96.81.252:7719/info

# Voir les agents
curl http://147.96.81.252:7719/gente

# Dashboard
# http://147.96.81.252:7719/dashboard
```

## Historique des decisions de design

1. **Polling au lieu de webhooks** : Butler n'a pas de webhooks, on doit interroger regulierement
2. **Une carta a la fois au LLM** : Mistral 7B est petit, envoyer tout le buzon depasse ses capacites
3. **Pre-calcul FALTAN/SOBRAN** : reduit la charge cognitive du LLM, il n'a pas a calculer
4. **validar_envio comme filet de securite** : on ne fait pas confiance au LLM pour les envois de ressources
5. **Suppression de /generate** : on garde uniquement le polling automatique, plus simple
