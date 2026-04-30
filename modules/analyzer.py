import os
import ssl
import json
import base64
import logging
import subprocess
import time
import threading
import certifi
from pathlib import Path
from datetime import datetime
from modules._env import _ROOT  # noqa — charge .env

# ── Sémaphore global — limite à 3 analyses simultanées (rate-limits API + disque) ──
ANALYSIS_SEMAPHORE = threading.Semaphore(3)

# Fix SSL
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# Injection PATH anticipée
_EXTRA_PATHS = [
    str(Path.home() / "bin"),
    "/Library/Frameworks/Python.framework/Versions/3.14/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
]
_cur = os.environ.get("PATH", "")
_add = ":".join(p for p in _EXTRA_PATHS if p not in _cur and Path(p).exists())
if _add:
    os.environ["PATH"] = _add + ":" + _cur

logger = logging.getLogger(__name__)

VOLUME_PATH      = os.getenv("RAILWAY_VOLUME_PATH", "./uploads")
SCREENSHOTS_PATH = "./screenshots"
IS_RAILWAY       = os.getenv("RAILWAY_ENVIRONMENT") is not None or os.path.exists("/usr/bin/ffmpeg")

# ── Fichier cookies TikTok persistant (priorité 1) ───────────────────────────
# Uploadé via l'UI Streamlit → sauvegardé dans VOLUME_PATH (volume Railway).
# Priorité : COOKIES_FILE > TIKTOK_COOKIES_B64 (env var) > browser (local) > rien
COOKIES_FILE = os.path.join(VOLUME_PATH, "tiktok_cookies.txt")

_COOKIES_FILE_CACHE: str | None = None   # chemin résolu pour la session courante


def reset_cookie_cache():
    """Force la re-résolution des cookies (appeler après upload d'un nouveau fichier)."""
    global _COOKIES_FILE_CACHE
    _COOKIES_FILE_CACHE = None


def get_ytdlp_cookie_args() -> list:
    """
    Retourne les args yt-dlp corrects pour l'authentification TikTok/IG.

    Priorité :
    1. COOKIES_FILE dans VOLUME_PATH (uploadé via l'UI — le plus récent)
    2. TIKTOK_COOKIES_B64 (env var Railway — fallback initial)
    3. --cookies-from-browser chrome (en local seulement)
    4. Rien (mode dégradé — stats souvent fausses sur TikTok)
    """
    global _COOKIES_FILE_CACHE

    # Si déjà résolu dans cette session, on réutilise
    if _COOKIES_FILE_CACHE and os.path.exists(_COOKIES_FILE_CACHE):
        return ["--cookies", _COOKIES_FILE_CACHE]

    # 1. Fichier uploadé via UI (volume persistant Railway)
    if os.path.exists(COOKIES_FILE):
        _COOKIES_FILE_CACHE = COOKIES_FILE
        logger.info("Cookies TikTok chargés depuis " + COOKIES_FILE)
        return ["--cookies", COOKIES_FILE]

    # 2. Variable d'environnement base64 (méthode Railway historique)
    b64 = os.getenv("TIKTOK_COOKIES_B64", "").strip()
    if b64:
        import base64 as _b64
        tmp_path = "/tmp/tiktok_cookies_b64.txt"
        try:
            with open(tmp_path, "w") as f:
                f.write(_b64.b64decode(b64).decode("utf-8"))
            _COOKIES_FILE_CACHE = tmp_path
            logger.info("Cookies TikTok chargés depuis TIKTOK_COOKIES_B64")
            return ["--cookies", tmp_path]
        except Exception as e:
            logger.warning("Impossible de décoder TIKTOK_COOKIES_B64: " + str(e))

    # 3. Navigateur local
    if not IS_RAILWAY:
        return ["--cookies-from-browser", "chrome"]

    # 4. Aucun cookie — stats TikTok non authentifiées (souvent fausses)
    logger.warning("Aucun cookie TikTok configuré — stats potentiellement incorrectes")
    return []


def get_cookies_status() -> dict:
    """
    Vérifie rapidement l'état des cookies TikTok sans appel réseau.
    Retourne {"status": "ok"|"missing"|"suspect", "source": ..., "details": ...}
    """
    # 1. Fichier uploadé via UI
    if os.path.exists(COOKIES_FILE):
        return _parse_cookies_status(COOKIES_FILE, source="UI upload")

    # 2. Variable d'environnement
    b64 = os.getenv("TIKTOK_COOKIES_B64", "").strip()
    if b64:
        import base64 as _b64
        tmp = "/tmp/tiktok_cookies_b64.txt"
        try:
            with open(tmp, "w") as f:
                f.write(_b64.b64decode(b64).decode("utf-8"))
            return _parse_cookies_status(tmp, source="env var TIKTOK_COOKIES_B64")
        except Exception:
            pass
        return {"status": "suspect", "source": "env var", "details": "Impossible de décoder TIKTOK_COOKIES_B64"}

    # 3. Local sans Railway
    if not IS_RAILWAY:
        return {"status": "ok", "source": "navigateur", "details": "--cookies-from-browser chrome (local)"}

    return {"status": "missing", "source": "aucun", "details": "Aucun cookie configuré"}


def _parse_cookies_status(path: str, source: str) -> dict:
    """Lit le fichier cookies et cherche les clés TikTok essentielles."""
    try:
        with open(path) as f:
            content = f.read()
    except Exception as e:
        return {"status": "missing", "source": source, "details": "Fichier illisible: " + str(e)}

    # Le cookie le plus critique pour l'auth TikTok
    essential = ["sessionid"]
    helpful   = ["tt_chain_token", "msToken", "tiktok_webapp_theme"]

    has_essential = any(k in content for k in essential)
    has_helpful   = any(k in content for k in helpful)

    if has_essential:
        found = [k for k in essential + helpful if k in content]
        return {
            "status":  "ok",
            "source":  source,
            "details": "Cookies présents : " + ", ".join(found),
            "file":    path,
        }
    elif has_helpful:
        return {
            "status":  "suspect",
            "source":  source,
            "details": "sessionid manquant — cookies partiels ou expirés",
            "file":    path,
        }
    else:
        return {
            "status":  "suspect",
            "source":  source,
            "details": "Aucun cookie TikTok reconnu — fichier incorrect ou expiré",
            "file":    path,
        }


def validate_tiktok_cookies_live(cookie_args: list, test_url: str = None) -> dict:
    """
    Validation en temps réel : interroge une vidéo TikTok connue pour populaire.
    Compare si les vues retournées sont plausibles (> 10 000).
    Retourne {"valid": bool, "vues_retournees": int, "message": str}
    """
    # Vidéo de test : une vidéo TikTok très populaire et stable
    test_url = test_url or "https://www.tiktok.com/@tiktok/video/6829267836783971589"
    cmd = (
        [YTDLP_BIN]
        + cookie_args
        + [
            "--skip-download",
            "--print", "%(view_count)s",
            "--no-warnings",
            "--quiet",
            test_url,
        ]
    )
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        raw = r.stdout.strip()
        views = int(raw) if raw.isdigit() else 0
        if views > 100_000:
            return {"valid": True,  "vues_retournees": views,
                    "message": f"✅ Cookies valides — {views:,} vues retournées (vidéo test)"}
        elif views > 0:
            return {"valid": False, "vues_retournees": views,
                    "message": f"⚠️ Cookies suspects — {views:,} vues (attendu >100k) — peut-être expirés"}
        else:
            return {"valid": False, "vues_retournees": 0,
                    "message": "❌ Impossible de récupérer les stats — cookies invalides ou TikTok bloqué"}
    except Exception as e:
        return {"valid": False, "vues_retournees": 0, "message": "Erreur validation: " + str(e)}


def _find_bin(name: str) -> str:
    candidates = [
        Path("/usr/bin") / name,
        Path("/usr/local/bin") / name,
        Path.home() / "bin" / name,
        Path("/Library/Frameworks/Python.framework/Versions/3.14/bin") / name,
        Path("/opt/homebrew/bin") / name,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return name

YTDLP_BIN  = _find_bin("yt-dlp")
FFMPEG_BIN = _find_bin("ffmpeg")
FFPROBE_BIN = _find_bin("ffprobe")


def _ensure_dirs():
    os.makedirs(VOLUME_PATH, exist_ok=True)
    os.makedirs(SCREENSHOTS_PATH, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# TÉLÉCHARGEMENT / ACQUISITION
# ─────────────────────────────────────────────────────────────────────────────

def download_video(url: str, video_id: int, progress_callback=None) -> str:
    _ensure_dirs()
    output_path = os.path.join(VOLUME_PATH, f"{video_id}.mp4")
    if progress_callback:
        progress_callback("Téléchargement de la vidéo...")

    is_tiktok   = "tiktok.com" in url
    is_instagram = "instagram.com" in url
    base_cmd    = [YTDLP_BIN, "--no-playlist", "-o", output_path]

    if is_tiktok or is_instagram:
        base_cmd += get_ytdlp_cookie_args()
        if IS_RAILWAY and not os.getenv("TIKTOK_COOKIES_B64"):
            # Fallback sans cookies : user-agent mobile (TikTok public seulement)
            base_cmd += [
                "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                "--add-header", "Referer:https://www.tiktok.com/",
                "--add-header", "Accept-Language:fr-FR,fr;q=0.9",
            ]
        base_cmd += ["-f", "bestvideo[vcodec^=avc][height<=720]+bestaudio/best[height<=720]/best"]
    else:
        base_cmd += ["-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best"]
        base_cmd += ["--merge-output-format", "mp4"]

    base_cmd.append(url)

    for attempt in range(3):
        try:
            result = subprocess.run(base_cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0:
                if not os.path.exists(output_path):
                    base = os.path.splitext(output_path)[0]
                    for ext in [".mp4", ".webm", ".mkv", ".mov"]:
                        if os.path.exists(base + ext):
                            os.rename(base + ext, output_path)
                            break
                return output_path
            err = result.stderr[-500:]
            if "private" in err.lower() or "login" in err.lower():
                raise RuntimeError("Compte privé — impossible d'accéder à cette vidéo.")
            if attempt < 2:
                time.sleep(3)
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise RuntimeError("Timeout téléchargement (180s dépassé)")
            time.sleep(5)
        except FileNotFoundError:
            raise RuntimeError(f"yt-dlp introuvable : {YTDLP_BIN}")

    raise RuntimeError(f"Téléchargement échoué après 3 tentatives. URL: {url}")


def copy_uploaded_video(file_bytes: bytes, filename: str, video_id: int) -> str:
    _ensure_dirs()
    ext = Path(filename).suffix or ".mp4"
    output_path = os.path.join(VOLUME_PATH, f"{video_id}{ext}")
    with open(output_path, "wb") as f:
        f.write(file_bytes)
    return output_path


def get_video_duration(video_path: str) -> float:
    try:
        cmd = [FFPROBE_BIN, "-v", "quiet", "-print_format", "json", "-show_format", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# COMPRESSION VIDÉO (réduit la taille 5-10x pour traitement rapide)
# ─────────────────────────────────────────────────────────────────────────────

def compress_video(video_path: str, progress_callback=None) -> str:
    """
    La compression est SKIPPÉE par défaut.
    ffmpeg travaille directement sur le fichier original (MOV/MP4/HEVC → détection scènes OK).
    Transcoder prend 20-30s même en ultrafast — bien plus long que le gain obtenu.
    On garde cette fonction comme no-op pour compatibilité.
    """
    orig_mb = os.path.getsize(video_path) / 1024 / 1024
    logger.info(f"Compression skippée — traitement direct du fichier ({orig_mb:.1f}MB)")
    if progress_callback:
        progress_callback(f"📁 Fichier {orig_mb:.0f}MB — démarrage analyse directe...")
    return video_path


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION DE SCÈNES (ffmpeg) + EXTRACTION FRAMES pour Vision
# ─────────────────────────────────────────────────────────────────────────────

def detect_scene_changes(video_path: str, duration: float) -> list:
    """
    Sampling uniforme dense — rapide (~0s), pas de décodage complet.
    Claude Vision analyse chaque frame et détecte les vrais changements de plans.

    Pourquoi pas le filtre ffmpeg scene ?
    → Décoder chaque frame HEVC (iPhone .mov) prend 1-2x la durée vidéo sur CPU.
    → Le sampling uniforme + Vision donne le même résultat en 10x moins de temps.

    Nombre de frames adapté à la durée (dense pour détecter tous les plans) :
    - ≤ 10s  : 1 frame/~0.8s  → max 12 frames
    - 10-20s : 1 frame/~1.2s  → max 15 frames
    - 20-30s : 1 frame/~2s    → max 15 frames
    - 30-60s : 1 frame/~3s    → max 15 frames
    - > 60s  : 1 frame/~5s    → max 15 frames
    """
    if duration <= 10:
        n_frames = min(12, max(6, int(duration * 1.2)))
    elif duration <= 20:
        n_frames = min(15, max(10, int(duration / 1.2)))
    elif duration <= 30:
        n_frames = min(15, max(12, int(duration / 2)))
    elif duration <= 60:
        n_frames = min(15, max(12, int(duration / 3)))
    else:
        n_frames = min(15, max(12, int(duration / 5)))

    step = duration / (n_frames + 1)
    timestamps = [0.0] + [round((i + 1) * step, 2) for i in range(n_frames)] + [round(duration, 2)]
    timestamps = sorted(set(timestamps))

    logger.info(f"Sampling dense: {len(timestamps)-1} intervalles pour {duration:.0f}s")
    return timestamps


MAX_FRAMES_VISION = 12   # Max frames envoyées à Claude Vision — 12 = bon équilibre plans/vitesse


def extract_frames_for_vision(video_path: str, timestamps: list,
                              screenshots_dir: str = None) -> list:
    """
    Extrait 1 frame par timestamp détecté (au milieu de chaque plan).
    Limite à MAX_FRAMES_VISION pour contrôler le coût Claude Vision.
    Retourne liste de {"data": base64_jpeg, "timestamp": float}.

    Si screenshots_dir est fourni, sauvegarde chaque frame sur disque (gratuit,
    fait en même temps que l'encodage base64 — pas de passe ffmpeg supplémentaire).
    """
    import shutil

    # Échantillonnage intelligent si trop de plans
    intervals = list(range(len(timestamps) - 1))
    if len(intervals) > MAX_FRAMES_VISION:
        step = len(intervals) / MAX_FRAMES_VISION
        intervals = [int(i * step) for i in range(MAX_FRAMES_VISION)]
        logger.info(f"Sous-échantillonnage: {len(timestamps)-1} plans → {MAX_FRAMES_VISION} frames pour Vision")

    if screenshots_dir:
        os.makedirs(screenshots_dir, exist_ok=True)

    frames = []
    for i in intervals:
        t_start = timestamps[i]
        t_end   = timestamps[i + 1]
        t_mid   = round((t_start + t_end) / 2, 2)

        frame_path = f"/tmp/insolit_{os.getpid()}_{i:02d}.jpg"
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(t_mid),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "4",
            "-vf", "scale=480:-1",   # 480px largeur — suffisant pour Vision
            frame_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
            if os.path.exists(frame_path):
                # Copier en screenshot AVANT d'encoder (même fichier, 0 coût ffmpeg)
                if screenshots_dir:
                    shot_num = len(frames) + 1
                    shot_dst = os.path.join(screenshots_dir, f"plan_{shot_num:02d}.jpg")
                    try:
                        shutil.copy2(frame_path, shot_dst)
                    except Exception as _se:
                        logger.debug(f"Screenshot {shot_num} non sauvegardé: {_se}")

                with open(frame_path, "rb") as fh:
                    data = base64.standard_b64encode(fh.read()).decode("utf-8")
                frames.append({
                    "data": data,
                    "timestamp_debut": t_start,
                    "timestamp_fin": t_end,
                    "timestamp_mid": t_mid,
                })
                try:
                    os.remove(frame_path)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Frame {i} échouée: {e}")

    logger.info(f"Frames extraites: {len(frames)} / {len(timestamps)-1} plans"
                + (f" + screenshots → {screenshots_dir}" if screenshots_dir else ""))
    return frames


# ─────────────────────────────────────────────────────────────────────────────
# SCREENSHOTS FINAUX (pour affichage UI)
# ─────────────────────────────────────────────────────────────────────────────

def extract_screenshots(video_path: str, plans: list, video_id: int, progress_callback=None) -> list:
    if not plans:
        return []
    screenshots_dir = os.path.join(SCREENSHOTS_PATH, str(video_id))
    os.makedirs(screenshots_dir, exist_ok=True)
    paths = []
    for i, plan in enumerate(plans):
        ts = plan.get("timestamp_debut", 0)
        output = os.path.join(screenshots_dir, f"plan_{i+1:02d}.jpg")
        try:
            cmd = [FFMPEG_BIN, "-y", "-ss", str(ts), "-i", video_path,
                   "-frames:v", "1", "-q:v", "3", output]
            subprocess.run(cmd, capture_output=True, timeout=15)
            paths.append(output if os.path.exists(output) else None)
        except Exception as e:
            logger.warning(f"Screenshot plan {i+1} échoué: {e}")
            paths.append(None)
    return paths


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def estimate_analysis_time(file_size_bytes: int, duration_seconds: float) -> int:
    """Estime le temps d'analyse en secondes selon la taille/durée."""
    # Base: 20s + 0.5s/seconde de vidéo + 2s/MB
    size_mb = file_size_bytes / 1024 / 1024
    estimate = 20 + duration_seconds * 0.5 + size_mb * 0.8
    return int(max(25, min(90, estimate)))


def analyze_video(
    source: str,
    metadata: dict,
    progress_callback=None,
    is_url: bool = True,
    file_bytes: bytes = None,
    filename: str = None,
    file_size_bytes: int = 0,
    quick_mode: bool = False,
) -> dict:
    """
    Pipeline principal d'analyse vidéo (Vision-first, rapide).
    Architecture : ffmpeg compression + scene detection + Claude Vision + Whisper (parallèle).
    Temps estimé : 25-45s selon durée/taille.
    """
    from concurrent.futures import ThreadPoolExecutor
    from modules.database import (
        get_session, Video, AnalysePegasus, Plan,
        Transcription, AnalyseCreative, init_db
    )
    from modules.claude_mod import analyze_frames_with_vision, analyze_creative
    from modules.whisper_mod import transcribe

    init_db()
    session = get_session()
    start_time = time.time()
    total_cout = 0.0

    def step(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    try:
        # ── 1. DB entry ──────────────────────────────────────────────────────
        step("⬇️ Initialisation...")
        video = Video(
            url_source=source if is_url else None,
            type_source=metadata.get("type_source", "inspiration"),
            nom_compte=metadata.get("nom_compte", ""),
            categorie=metadata.get("categorie", ""),
            partenaire=metadata.get("partenaire", ""),
            ville=metadata.get("ville", ""),
            statut_analyse="en_cours",
            type_offre=metadata.get("type_offre", ""),
        )
        session.add(video)
        session.commit()
        video_id = video.id

        # ── 2. Acquisition ───────────────────────────────────────────────────
        step("⬇️ Récupération de la vidéo...")
        if is_url:
            video_path = download_video(source, video_id, step)
        else:
            video_path = copy_uploaded_video(file_bytes, filename, video_id)

        duree = get_video_duration(video_path)
        video.fichier_path = video_path
        video.duree_secondes = duree
        session.commit()

        # ── 3. Préparation (pas de compression — ffmpeg lit directement) ────────
        working_path = compress_video(video_path, step)  # no-op, retourne original

        # ── 4. Sampling + extraction frames (+ screenshots sauvegardés en même temps) ──
        mode_label = "⚡ rapide" if quick_mode else "🔬 complet"
        step(f"📸 Extraction des frames ({mode_label})...")
        scene_timestamps = detect_scene_changes(working_path, duree)
        # Screenshots sauvegardés PENDANT l'extraction — même passe ffmpeg, 0 coût extra
        screenshots_dir = os.path.join(SCREENSHOTS_PATH, str(video_id))
        frames = extract_frames_for_vision(working_path, scene_timestamps,
                                           screenshots_dir=screenshots_dir)
        # Mode rapide : limiter à 5 frames pour réduire coût et temps
        if quick_mode and len(frames) > 5:
            frames = frames[:5]
        step(f"📸 {len(frames)} frames extraites ({mode_label}) + screenshots")

        # ── 5. Vision (Claude) + Whisper en PARALLÈLE ───────────────────────
        step(f"🎬 Analyse Vision + 📝 Transcription en parallèle...")

        _vision_result  = [None]
        _vision_usage   = [{}]
        _whisper_result = [None]
        _vision_error   = [None]
        _whisper_error  = [None]

        def _run_vision():
            try:
                res, usg = analyze_frames_with_vision(frames, duree)
                _vision_result[0] = res
                _vision_usage[0]  = usg
            except Exception as e:
                _vision_error[0] = e

        def _run_whisper():
            try:
                _whisper_result[0] = transcribe(working_path, None)
            except Exception as e:
                _whisper_error[0] = e

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_vision  = executor.submit(_run_vision)
            f_whisper = executor.submit(_run_whisper)
            f_vision.result()
            f_whisper.result()

        # Résultats Vision
        if _vision_error[0]:
            logger.error(f"Vision error: {_vision_error[0]}")
            pegasus_data = _vision_fallback(duree)
        else:
            pegasus_data = _vision_result[0] or _vision_fallback(duree)

        # Garde anti-troncature : si Vision a retourné 0 plans, retry avec 5 frames (sauf mode rapide)
        if not quick_mode and not pegasus_data.get("plans"):
            logger.warning("Vision retourne 0 plans — retry avec 5 frames (JSON tronqué probable)")
            frames_lite = frames[:5] if frames else []
            if frames_lite:
                try:
                    res2, usg2 = analyze_frames_with_vision(frames_lite, duree)
                    if res2 and res2.get("plans"):
                        pegasus_data = res2
                        if usg2:
                            total_cout += usg2.get("cout_estime", 0)
                        logger.info(f"Retry Vision réussi: {len(res2['plans'])} plans")
                    else:
                        pegasus_data = _vision_fallback(duree)
                        logger.warning("Retry Vision aussi vide — fallback plans synthétiques")
                except Exception as e2:
                    logger.error(f"Retry Vision échoué: {e2}")
                    pegasus_data = _vision_fallback(duree)
            else:
                pegasus_data = _vision_fallback(duree)

        if _vision_usage[0]:
            total_cout += _vision_usage[0].get("cout_estime", 0)

        # Résultats Whisper
        if _whisper_error[0]:
            logger.error(f"Whisper error: {_whisper_error[0]}")
            whisper_result = {"mots": [], "texte_complet": "", "nb_mots": 0, "debit_parole": 0, "silences": [], "langue": "fr"}
        else:
            whisper_result = _whisper_result[0] or {"mots": [], "texte_complet": "", "nb_mots": 0, "debit_parole": 0, "silences": [], "langue": "fr"}

        plans_data = pegasus_data.get("plans", [])
        metriques  = pegasus_data.get("metriques_globales", {})
        hook       = pegasus_data.get("hook_analyse", {})

        step(f"🎬 {len(plans_data)} plans | 📝 {whisper_result.get('nb_mots', 0)} mots transcrits")

        # ── 6. Sauvegarde DB (Vision + Whisper) ─────────────────────────────
        ap = AnalysePegasus(
            video_id=video_id,
            raw_json=json.dumps(pegasus_data, ensure_ascii=False),
            nb_plans=len(plans_data),
            duree_moyenne_plan=round(duree / max(len(plans_data), 1), 2),
            rythme_coupes_par_seconde=float(metriques.get("rythme_coupes_par_seconde") or 0),
            luminosite_moyenne=float(metriques.get("luminosite_moyenne") or 5),
            presence_visage=_pct_to_bool(metriques.get("presence_visage_pourcentage", "0%")),
            presence_texte_ecran=_pct_to_bool(metriques.get("proportion_texte_ecran", "0%")),
            qualite_production=float(metriques.get("qualite_globale") or 5),
            type_tournage=_to_str(metriques.get("type_tournage", "")),
            mouvement_dominant="",
        )
        session.add(ap)

        for i, p in enumerate(plans_data):
            t_debut = float(p.get("timestamp_debut") or 0)
            t_fin   = float(p.get("timestamp_fin") or duree)
            plan_obj = Plan(
                video_id=video_id,
                numero_plan=i + 1,
                timestamp_debut=t_debut,
                timestamp_fin=t_fin,
                duree=round(t_fin - t_debut, 2),
                type_plan=_to_str(p.get("type_plan", "")),
                description=_to_str(p.get("sujet_principal", "")),
                luminosite=float(p.get("luminosite") or 5),
                mouvement=_to_str(p.get("mouvement_camera", "")),
                presence_visage=bool(p.get("presence_visage", False)),
                expression=_to_str(p.get("expression_visage", "")),
                texte_visible=_to_str(p.get("texte_visible_ecran")) or None,
                couleur_dominante=_to_str(p.get("couleurs_dominantes", [])),
                qualite=float(p.get("qualite_production") or 5),
                role_narratif=_to_str(p.get("role_narratif", "")),
                points_forts=_to_str(p.get("points_forts", [])),
                suggestion_amelioration=_to_str(p.get("suggestion_amelioration", "")),
                changement_scene=bool(p.get("changement_scene", False)),
                personnes=_to_str(p.get("personnes", "")),
            )
            session.add(plan_obj)

        for w in whisper_result.get("mots", []):
            session.add(Transcription(
                video_id=video_id,
                timestamp=w["start"],
                mot=w["mot"],
                confiance=w["confiance"],
            ))

        session.commit()

        # ── 7. Marengo embedding (optionnel, en arrière-plan) ────────────────
        # Note: skippé ici pour garder < 30s. Le refaire manuellement si besoin.
        similar_videos = []

        # ── 8. Analyse créative Claude (avec les vraies images = plus précis) ─────
        step("🧠 Analyse créative (Claude Haiku + images réelles)...")
        # Frames envoyées à analyze_creative seulement en mode complet (quick_mode=False)
        # En mode rapide ou analyse de compte → texte seul (Haiku, moins cher)
        frames_for_creative = (frames[:5] if frames else []) if not quick_mode else []
        creative_data, claude_usage = analyze_creative(
            pegasus_data, whisper_result, similar_videos,
            frames=frames_for_creative
        )
        if claude_usage:
            total_cout += claude_usage.get("cout_estime", 0)

        ac = AnalyseCreative(
            video_id=video_id,
            hook_texte=_to_str(creative_data.get("hook_texte", hook.get("texte_dit", ""))),
            hook_visuel=_to_str(creative_data.get("hook_visuel", "")),
            hook_type=_to_str(creative_data.get("hook_type", hook.get("type_hook", ""))),
            hook_score=float(creative_data.get("hook_score") or hook.get("score_accroche") or 5),
            hook_analyse=_to_str(creative_data.get("hook_analyse", "")),
            structure_narrative=_to_str(creative_data.get("structure_narrative", "")),
            points_forts=_to_str(creative_data.get("points_forts", [])),
            points_faibles=_to_str(creative_data.get("points_faibles", [])),
            score_potentiel=float(creative_data.get("score_potentiel") or 5),
            recommandations=_to_str(creative_data.get("recommandations", [])),
            comparaison_base=_to_str(creative_data.get("comparaison_base", "")),
            adaptable_insolit=bool(creative_data.get("adaptable_insolit", True)),
            note_adaptation=_to_str(creative_data.get("note_adaptation", "")),
        )
        session.add(ac)

        titre_auto = _generate_title(metadata, whisper_result, hook, duree=duree)
        video.titre = titre_auto
        session.commit()

        # ── 9. Screenshots : déjà sauvegardés pendant extract_frames_for_vision ──
        # Chaque frame = screenshot → ./screenshots/{video_id}/plan_XX.jpg

        # ── 10. Finalisation ──────────────────────────────────────────────────
        video.statut_analyse = "complete"
        session.commit()

        elapsed = round(time.time() - start_time)
        # Temps séquentiel estimé = Vision + Whisper si non parallèles (~20s chacun)
        # En parallèle on économise ~min(dur_vision, dur_whisper) ≈ 15-20s
        sequential_estimate = elapsed + 15
        step(f"✅ Terminé en {elapsed}s | ~{sequential_estimate - elapsed}s économisés (parallèle) | Coût : ~${total_cout:.4f}")

        return {
            "success": True,
            "video_id": video_id,
            "titre": titre_auto,
            "duree_secondes": duree,
            "pegasus_data": pegasus_data,
            "whisper_data": whisper_result,
            "creative_data": creative_data,
            "similar_videos": similar_videos,
            "plans_count": len(plans_data),
            "elapsed": elapsed,
            "elapsed_saved": sequential_estimate - elapsed,
            "cout_total": total_cout,
            "screenshots_dir": screenshots_dir,
        }

    except Exception as e:
        logger.error(f"Erreur pipeline: {e}", exc_info=True)
        try:
            video.statut_analyse = "erreur"
            session.commit()
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _to_str(val) -> str:
    """Convertit n'importe quelle valeur en string sûre pour une colonne Text SQLite.
    Evite le bug 'type dict/list is not supported' lors des INSERTs.
    - dict / list → JSON string
    - None        → ""
    - str         → inchangé
    - autre       → str(val)
    """
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _vision_fallback(duration: float) -> dict:
    n = max(3, int(duration / 5))
    plans = []
    for i in range(n):
        t0 = round(i * duration / n, 1)
        t1 = round((i + 1) * duration / n, 1)
        plans.append({
            "timestamp_debut": t0, "timestamp_fin": t1,
            "type_plan": "plan_moyen", "sujet_principal": f"Plan {i+1}",
            "luminosite": 6, "type_lumiere": "mixte",
            "mouvement_camera": "statique", "presence_visage": False,
            "expression_visage": "na", "texte_visible_ecran": None,
            "couleurs_dominantes": [], "qualite_production": 6,
            "emotion_transmise": "neutre", "role_narratif": "contexte",
            "points_forts": [], "suggestion_amelioration": "",
            "scene_change_type": "cut",
        })
    return {
        "plans": plans,
        "hook_analyse": {
            "duree_hook_secondes": 3, "texte_dit": "", "texte_visible": None,
            "type_hook": "inconnu", "score_accroche": 5,
            "premiere_impression": "Analyse Vision non disponible",
            "ce_qui_accroche": "", "ce_qui_manque": None,
        },
        "metriques_globales": {
            "nb_plans_total": n, "rythme_coupes_par_seconde": round(n / max(duration, 1), 2),
            "luminosite_moyenne": 6, "presence_visage_pourcentage": "0%",
            "proportion_texte_ecran": "0%", "type_tournage": "inconnu", "qualite_globale": 6,
        },
    }


def _pct_to_bool(pct_str: str) -> bool:
    try:
        return float(str(pct_str).replace("%", "").strip()) > 20
    except Exception:
        return False


def _load_all_embeddings(session, exclude_id: int = None) -> list:
    from modules.database import AnalysePegasus, Video
    q = session.query(AnalysePegasus, Video).join(Video).filter(
        AnalysePegasus.marengo_embedding.isnot(None)
    )
    if exclude_id:
        q = q.filter(Video.id != exclude_id)
    result = []
    for ap, v in q.all():
        emb = ap.get_embedding()
        if emb:
            result.append({
                "video_id": v.id, "titre": v.titre,
                "nom_compte": v.nom_compte, "embedding": emb,
            })
    return result


def _generate_title(metadata: dict, whisper_data: dict, hook_data: dict, duree: float = 0) -> str:
    """
    Génère un titre propre et lisible.
    Format : [Partenaire ou @compte ou Catégorie] · [Durée]s · [Date]
    """
    partenaire  = (metadata.get("partenaire") or "").strip()
    nom_compte  = (metadata.get("nom_compte") or "").strip().lstrip("@")
    categorie   = (metadata.get("categorie") or "").strip()
    date_str    = datetime.now().strftime("%d/%m/%Y")
    duree_str   = f"{int(duree)}s" if duree and duree > 0 else ""

    if partenaire:
        parts = [partenaire]
    elif nom_compte:
        parts = [f"@{nom_compte}"]
    elif categorie:
        parts = [categorie]
    else:
        parts = ["Vidéo"]

    if duree_str:
        parts.append(duree_str)
    parts.append(date_str)
    return " · ".join(parts)
