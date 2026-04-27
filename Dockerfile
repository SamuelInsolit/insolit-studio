FROM python:3.11-slim

# ── Dépendances système ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    curl \
    git \
    build-essential \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Répertoire de travail ──────────────────────────────────────────────────────
WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── yt-dlp (dernière version) ─────────────────────────────────────────────────
RUN pip install --no-cache-dir yt-dlp --upgrade

# ── Pré-télécharge le modèle Whisper small ────────────────────────────────────
# (small ~500MB RAM — adapté aux limites Railway)
RUN python -c "import whisper; whisper.load_model('small')" || echo "Whisper model download skipped"

# ── App ───────────────────────────────────────────────────────────────────────
COPY . .

# ── Répertoires de données ────────────────────────────────────────────────────
RUN mkdir -p /app/uploads /app/screenshots

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8501

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ── Démarrage ─────────────────────────────────────────────────────────────────
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
