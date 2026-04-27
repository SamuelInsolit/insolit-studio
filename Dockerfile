FROM python:3.11-slim

# ── Dépendances système ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Répertoire de travail ──────────────────────────────────────────────────────
WORKDIR /app

# ── Python deps (sans torch/whisper → image ~300MB au lieu de 1.5GB) ──────────
# Sur Railway : transcription via OpenAI API Whisper (OPENAI_API_KEY requis)
# En local    : pip install openai-whisper séparément si besoin
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── yt-dlp (dernière version) ─────────────────────────────────────────────────
RUN pip install --no-cache-dir yt-dlp --upgrade

# ── App ───────────────────────────────────────────────────────────────────────
COPY . .

# ── Répertoires de données ────────────────────────────────────────────────────
RUN mkdir -p /app/uploads /app/screenshots

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8501

# ── Démarrage ─────────────────────────────────────────────────────────────────
# Railway utilise son propre healthcheck (railway.toml) + startCommand avec $PORT
CMD ["sh", "-c", "python -m streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false --browser.gatherUsageStats=false"]
