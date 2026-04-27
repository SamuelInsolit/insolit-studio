import os
import sys
import logging
import subprocess
import certifi
from pathlib import Path

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# Injecte ~/bin dans PATH pour que Whisper trouve ffmpeg
_EXTRA_PATHS = [
    str(Path.home() / "bin"),
    str(Path.home() / "Library" / "Application Support" / "insolit" / "bin"),
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

logger = logging.getLogger(__name__)

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        logger.info("Chargement modèle Whisper medium...")
        _whisper_model = whisper.load_model("medium")
        logger.info("Modèle Whisper chargé.")
    return _whisper_model


def _extract_audio(video_path: str) -> str:
    """Extrait l'audio d'une vidéo en WAV via ffmpeg."""
    audio_path = str(Path(video_path).with_suffix(".wav"))
    try:
        cmd = [
            FFMPEG_BIN, "-y", "-i", video_path,
            "-ar", "16000", "-ac", "1", "-f", "wav",
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg erreur: {result.stderr}")
        logger.info(f"Audio extrait: {audio_path}")
        return audio_path
    except FileNotFoundError:
        raise RuntimeError("ffmpeg non trouvé. Installe ffmpeg sur le système.")


def transcribe(video_path: str, progress_callback=None) -> dict:
    """
    Transcription mot par mot avec timestamps.
    Retourne un dict avec mots, débit parole, silences.
    """
    if progress_callback:
        progress_callback("Extraction audio...")

    audio_path = _extract_audio(video_path)

    try:
        model = _get_model()

        if progress_callback:
            progress_callback("Transcription Whisper en cours...")

        result = model.transcribe(
            audio_path,
            language="fr",
            word_timestamps=True,
            verbose=False
        )

        words = []
        for segment in result.get("segments", []):
            for word_data in segment.get("words", []):
                words.append({
                    "mot": word_data["word"].strip(),
                    "start": round(float(word_data["start"]), 3),
                    "end": round(float(word_data["end"]), 3),
                    "confiance": round(float(word_data.get("probability", 0.9)), 3),
                })

        # Débit de parole
        duree_totale = result.get("segments", [{}])[-1].get("end", 1) if result.get("segments") else 1
        debit_parole = round(len(words) / max(duree_totale, 1), 2)

        # Détection silences > 0.5s
        silences = []
        for i in range(1, len(words)):
            gap = words[i]["start"] - words[i - 1]["end"]
            if gap > 0.5:
                silences.append({
                    "debut": words[i - 1]["end"],
                    "fin": words[i]["start"],
                    "duree": round(gap, 3)
                })

        texte_complet = result.get("text", "").strip()
        nb_mots = len(words)

        logger.info(f"Transcription: {nb_mots} mots, débit={debit_parole} mots/s")

        return {
            "mots": words,
            "texte_complet": texte_complet,
            "nb_mots": nb_mots,
            "debit_parole": debit_parole,
            "silences": silences,
            "langue": result.get("language", "fr"),
        }

    except Exception as e:
        logger.error(f"Erreur Whisper: {e}")
        return {
            "mots": [],
            "texte_complet": "",
            "nb_mots": 0,
            "debit_parole": 0,
            "silences": [],
            "langue": "fr",
            "_error": str(e)
        }
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def format_transcript_display(words: list) -> str:
    """Formate la transcription pour affichage avec timestamps."""
    if not words:
        return "Aucune transcription disponible."

    lines = []
    current_line = []
    current_start = None

    for w in words:
        if current_start is None:
            current_start = w["start"]
        current_line.append(w["mot"])

        if len(current_line) >= 8 or w["mot"].endswith((".", "!", "?", ",")):
            ts = f"[{current_start:.1f}s]"
            lines.append(f"{ts} {' '.join(current_line)}")
            current_line = []
            current_start = None

    if current_line:
        ts = f"[{current_start:.1f}s]" if current_start else "[?s]"
        lines.append(f"{ts} {' '.join(current_line)}")

    return "\n".join(lines)
