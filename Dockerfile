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

# ── PyTorch CPU-only (~300MB vs ~2GB GPU) ────────────────────────────────────
# DOIT être installé AVANT openai-whisper pour éviter la version GPU
RUN pip install --no-cache-dir \
    torch==2.1.0+cpu \
    torchaudio==2.1.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# ── Python deps ───────────────────────────────────────────────────────────────
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

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ── Démarrage ─────────────────────────────────────────────────────────────────
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
