# Déploiement Railway — Insolit Studio

## IDs Railway

```
Project ID:     86ca97e9-24a3-4467-a8f8-8dfe437a2efa
Service ID:     975a4068-19b6-4fca-9f50-2ee45f65f0aa
Environment ID: 6bb354ba-9ebc-4db6-8adb-a9020d018333
API Token:      085d1a70-4438-469c-be52-2efa49aa5716
Repo:           SamuelInsolit/insolit-studio (branch: main)
```

## Commandes de déploiement

### Déployer le dernier commit sur main
```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer 085d1a70-4438-469c-be52-2efa49aa5716" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { serviceInstanceDeploy(serviceId: \"975a4068-19b6-4fca-9f50-2ee45f65f0aa\", environmentId: \"6bb354ba-9ebc-4db6-8adb-a9020d018333\", commitSha: \"FULL_SHA_ICI\") }"
  }'
```

⚠️ Utiliser le **SHA complet** (40 chars), pas le SHA court (7 chars).

### Redéployer le dernier build réussi
```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer ..." \
  -d '{"query": "mutation { serviceInstanceRedeploy(serviceId: \"...\", environmentId: \"...\") }"}'
```

### Vérifier le statut des déploiements
```bash
curl -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer ..." \
  -d '{"query": "{ deployments(first: 3, input: { serviceId: \"...\" }) { edges { node { id status createdAt meta } } } }"}'
```

## Configuration (railway.toml)

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "python -m streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"
healthcheckPath = "/_stcore/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

## Docker Image

- Builder : **Dockerfile** (pas Railpack)
- Base : `python:3.11-slim`
- PyTorch : **CPU-only** (`torch==2.1.0+cpu`) → ~1.5GB vs ~4GB GPU
- PyTorch installé AVANT requirements.txt pour éviter version GPU
- Pas de pré-download modèle Whisper (téléchargé au premier appel)

## Variables d'environnement requises

```
ANTHROPIC_API_KEY=sk-ant-...      # Claude API
RAILWAY_ENVIRONMENT=production    # Détecté auto par Railway
DATABASE_URL=postgresql://...     # PostgreSQL (optionnel, SQLite par défaut)
```

## Problèmes connus et solutions

### ❌ "Failed to fetch specific commit: couldn't find remote ref"
**Cause** : SHA court (7 chars) passé à `serviceInstanceDeploy`
**Fix** : Utiliser `git rev-parse HEAD` pour obtenir le SHA complet (40 chars)

### ❌ Builder RAILPACK au lieu de DOCKERFILE
**Cause** : `serviceInstanceDeploy` ignore parfois le `railway.toml`
**Fix** : Utiliser `serviceInstanceRedeploy` OU vérifier que `railway.toml` est committed et poussé

### ❌ Healthcheck timeout (service unavailable)
**Causes possibles** :
1. OOM (Out of Memory) — Whisper medium trop lourd → utiliser `small` sur Railway
2. Import crash au démarrage → vérifier les logs Railway
3. Mauvais port — `startCommand` doit utiliser `$PORT`

### ❌ Build timeout >10 min
**Cause** : Whisper model pré-téléchargé dans Dockerfile + image GPU de 4GB
**Fix** : 
- Supprimer le `RUN python -c "import whisper; whisper.load_model('medium')"` du Dockerfile
- Installer CPU-only PyTorch avant requirements.txt

### ❌ Database URL (postgres:// vs postgresql://)
SQLAlchemy requiert `postgresql://` mais Railway fournit `postgres://`.
**Fix** (dans `database.py`) :
```python
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
```

## Temps de build typiques

- Avec cache Docker : ~60-90s
- Sans cache (nouveau build) : ~180-240s
- Healthcheck start period : 300s (configuré dans railway.toml)

## URL de l'application

À retrouver dans Railway Dashboard → Service → Settings → Domains.
Format : `https://insolit-studio-XXXX.railway.app`
