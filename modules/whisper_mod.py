import os
import sys
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Sur Railway → OpenAI Whisper API (pas de torch, image légère)
# En local  → Whisper local (gratuit, offline)
IS_RAILWAY = os.getenv("RAILWAY_ENVIRONMENT") is not None
USE_API    = IS_RAILWAY or os.getenv("WHISPER_USE_API", "0") == "1"

# Injection PATH pour ffmpeg local
_EXTRA_PATHS = [
    str(Path.home() / "bin"),
    "/Library/Frameworks/Python.framework/Versions/3.14/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
]
_current_path = os.environ.get("PATH", "")
_inject = ":".join(p for p in _EXTRA_PATHS if p not in _current_path)
if _inject:
    os.environ["PATH"] = _inject + ":" + _current_path

def _find_bin(name: str) -> str:
    for base in _EXTRA_PATHS + ["/usr/bin"]:
        p = Path(base) / name
        if p.exists():
            return str(p)
    return name

FFMPEG_BIN = _find_bin("ffmpeg")

# ─── Modèle local (lazy) ──────────────────────────────────────────────────────
_whisper_model = None

def _get_local_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        # tiny  → ~5s   / 39MB   — rapide, bon pour hooks courts
        # small → ~20s  / 500MB  — meilleure précision FR
        model_size = os.getenv("WHISPER_MODEL", "tiny")
        logger.info(f"Chargement Whisper local {model_size}...")
        _whisper_model = whisper.load_model(model_size)
        logger.info(f"Whisper {model_size} chargé.")
    return _whisper_model


# ─── Extraction audio ─────────────────────────────────────────────────────────
def _extract_audio(video_path: str) -> str:
    audio_path = str(Path(video_path).with_suffix(".wav"))
    cmd = [FFMPEG_BIN, "-y", "-i", video_path,
           "-ar", "16000", "-ac", "1", "-f", "wav", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract: {result.stderr[-300:]}")
    return audio_path


def _extract_audio_mp3(video_path: str) -> str:
    """Pour l'API OpenAI (accepte mp3, max 25MB)."""
    audio_path = str(Path(video_path).with_suffix(".mp3"))
    cmd = [FFMPEG_BIN, "-y", "-i", video_path,
           "-ar", "16000", "-ac", "1",
           "-c:a", "libmp3lame", "-b:a", "32k",
           audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg mp3 extract: {result.stderr[-300:]}")
    return audio_path


# ─── Transcription via API OpenAI (Railway) ───────────────────────────────────
def _transcribe_api(video_path: str) -> dict:
    """
    Utilise l'API Whisper d'OpenAI.
    Coût : $0.006/minute (vidéo 30s = ~$0.003).
    Avantage : aucun torch/whisper installé → image Docker -1GB.
    """
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
    # Note: si pas de clé OpenAI séparée, fallback sur transcription locale si dispo
    if not api_key or api_key.startswith("sk-ant"):
        logger.warning("Pas de OPENAI_API_KEY — fallback Whisper local")
        return _transcribe_local(video_path)

    client = OpenAI(api_key=api_key)

    # Extraire audio en mp3 léger (max 25MB requis par API)
    audio_path = _extract_audio_mp3(video_path)
    try:
        file_size_mb = os.path.getsize(audio_path) / 1024 / 1024
        logger.info(f"Transcription API Whisper: {file_size_mb:.1f}MB mp3")

        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="fr",
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )

        words = []
        # verbose_json retourne words avec timestamps
        for w in (result.words or []):
            words.append({
                "mot": w.word.strip(),
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "confiance": 0.95,  # API ne fournit pas de score de confiance
            })

        texte = result.text.strip() if result.text else ""
        nb_mots = len(words)
        duree = words[-1]["end"] if words else 1
        debit = round(nb_mots / max(duree, 1), 2)

        # Silences > 0.5s
        silences = []
        for i in range(1, len(words)):
            gap = words[i]["start"] - words[i-1]["end"]
            if gap > 0.5:
                silences.append({"debut": words[i-1]["end"], "fin": words[i]["start"], "duree": round(gap, 3)})

        logger.info(f"API Whisper: {nb_mots} mots, débit={debit} mots/s")
        return {"mots": words, "texte_complet": texte, "nb_mots": nb_mots,
                "debit_parole": debit, "silences": silences, "langue": "fr"}

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


# ─── Transcription locale (Mac/dev) ──────────────────────────────────────────
def _transcribe_local(video_path: str) -> dict:
    audio_path = _extract_audio(video_path)
    try:
        model = _get_local_model()
        result = model.transcribe(audio_path, language="fr", word_timestamps=True, verbose=False)

        words = []
        for segment in result.get("segments", []):
            for wd in segment.get("words", []):
                words.append({
                    "mot": wd["word"].strip(),
                    "start": round(float(wd["start"]), 3),
                    "end": round(float(wd["end"]), 3),
                    "confiance": round(float(wd.get("probability", 0.9)), 3),
                })

        duree = result.get("segments", [{}])[-1].get("end", 1) if result.get("segments") else 1
        debit = round(len(words) / max(duree, 1), 2)

        silences = []
        for i in range(1, len(words)):
            gap = words[i]["start"] - words[i-1]["end"]
            if gap > 0.5:
                silences.append({"debut": words[i-1]["end"], "fin": words[i]["start"], "duree": round(gap, 3)})

        texte = result.get("text", "").strip()
        logger.info(f"Whisper local: {len(words)} mots, débit={debit} mots/s")
        return {"mots": words, "texte_complet": texte, "nb_mots": len(words),
                "debit_parole": debit, "silences": silences, "langue": result.get("language", "fr")}
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


# ─── Point d'entrée public ────────────────────────────────────────────────────
def transcribe(video_path: str, progress_callback=None) -> dict:
    """
    Transcription avec timestamps par mot.
    - Railway / WHISPER_USE_API=1 → OpenAI API (~$0.003/vidéo 30s, 0 RAM)
    - Local                       → Whisper tiny local (~4-6s, gratuit)
    """
    if progress_callback:
        mode = "API OpenAI" if USE_API else "Whisper local"
        progress_callback(f"📝 Transcription ({mode})...")
    try:
        if USE_API:
            return _transcribe_api(video_path)
        else:
            return _transcribe_local(video_path)
    except Exception as e:
        logger.error(f"Transcription échouée: {e}")
        return {"mots": [], "texte_complet": "", "nb_mots": 0,
                "debit_parole": 0, "silences": [], "langue": "fr", "_error": str(e)}


def format_transcript_display(words: list) -> str:
    if not words:
        return "Aucune transcription disponible."
    lines, current_line, current_start = [], [], None
    for w in words:
        if current_start is None:
            current_start = w["start"]
        current_line.append(w["mot"])
        if len(current_line) >= 8 or w["mot"].endswith((".", "!", "?", ",")):
            lines.append(f"[{current_start:.1f}s] {' '.join(current_line)}")
            current_line, current_start = [], None
    if current_line:
        ts = f"[{current_start:.1f}s]" if current_start else "[?s]"
        lines.append(f"{ts} {' '.join(current_line)}")
    return "\n".join(lines)
