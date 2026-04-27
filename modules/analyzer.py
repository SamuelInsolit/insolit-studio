import os
import ssl
import json
import base64
import logging
import subprocess
import time
import certifi
from pathlib import Path
from datetime import datetime
from modules._env import _ROOT  # noqa — charge .env

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

VOLUME_PATH    = os.getenv("RAILWAY_VOLUME_PATH", "./uploads")
SCREENSHOTS_PATH = "./screenshots"
IS_RAILWAY     = os.getenv("RAILWAY_ENVIRONMENT") is not None or os.path.exists("/usr/bin/ffmpeg")


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
        if not IS_RAILWAY:
            base_cmd += ["--cookies-from-browser", "chrome"]
        else:
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
    Compresse la vidéo pour réduire la taille → traitement rapide.
    720p max, 900kbps video, 96kbps audio.
    Retourne le chemin du fichier compressé (ou original si échec).
    """
    if progress_callback:
        progress_callback("🗜️ Compression de la vidéo...")

    base     = os.path.splitext(video_path)[0]
    out_path = f"{base}_c.mp4"

    # Filtre scale : respecte l'orientation portrait/paysage
    scale_filter = "scale='if(gt(iw,ih),min(720,iw),-2)':'if(gt(iw,ih),-2,min(720,ih))'"

    cmd = [
        FFMPEG_BIN, "-y", "-i", video_path,
        "-vf", scale_filter,
        "-c:v", "libx264", "-crf", "28", "-b:v", "900k", "-maxrate", "1200k",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        "-threads", "2",
        out_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.exists(out_path):
            orig_mb  = os.path.getsize(video_path) / 1024 / 1024
            comp_mb  = os.path.getsize(out_path)   / 1024 / 1024
            logger.info(f"Compression: {orig_mb:.1f}MB → {comp_mb:.1f}MB ({comp_mb/orig_mb*100:.0f}%)")
            if progress_callback:
                progress_callback(f"🗜️ Vidéo compressée ({orig_mb:.0f}MB → {comp_mb:.0f}MB)")
            return out_path
    except Exception as e:
        logger.warning(f"Compression échouée: {e} — utilisation fichier original")
    return video_path


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION DE SCÈNES (ffmpeg) + EXTRACTION FRAMES pour Vision
# ─────────────────────────────────────────────────────────────────────────────

def detect_scene_changes(video_path: str, duration: float) -> list:
    """
    Détecte les changements de plan via ffmpeg (scene filter).
    Retourne une liste de timestamps où des coupes sont détectées.
    """
    try:
        # Paramètre 0.25 = seuil de détection (0=tout, 1=rien)
        cmd = [
            FFMPEG_BIN, "-i", video_path,
            "-filter:v", "select='gt(scene,0.25)',showinfo",
            "-frames:v", "50",
            "-f", "null", "/dev/null",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stderr  # ffmpeg écrit showinfo sur stderr

        timestamps = [0.0]  # Toujours inclure le début
        for line in output.split("\n"):
            if "pts_time:" in line:
                try:
                    pts_part = [p for p in line.split() if "pts_time:" in p][0]
                    ts = float(pts_part.split(":")[1])
                    if ts > 0.5 and ts < duration - 0.5:  # Ignorer tout début/fin
                        timestamps.append(round(ts, 2))
                except Exception:
                    pass

        timestamps.append(duration)  # Toujours inclure la fin

        # Si pas assez de scènes détectées → découpage uniforme
        if len(timestamps) < 3:
            n = max(4, min(8, int(duration / 4)))
            timestamps = [0.0] + [round((i + 1) * duration / (n + 1), 2) for i in range(n)] + [duration]

        return sorted(set(timestamps))

    except Exception as e:
        logger.warning(f"Détection scènes échouée: {e}")
        n = max(4, min(8, int(duration / 4)))
        return [round(i * duration / (n + 1), 2) for i in range(n + 2)]


def extract_frames_for_vision(video_path: str, timestamps: list) -> list:
    """
    Extrait 1 frame par timestamp détecté (au milieu de chaque plan).
    Retourne liste de {"data": base64_jpeg, "timestamp": float}.
    """
    frames = []
    # On prend le milieu de chaque intervalle (pas le début exact)
    for i in range(len(timestamps) - 1):
        t_start = timestamps[i]
        t_end   = timestamps[i + 1]
        t_mid   = round((t_start + t_end) / 2, 2)

        frame_path = f"/tmp/insolit_f{i:02d}.jpg"
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

    logger.info(f"Frames extraites: {len(frames)} / {len(timestamps)-1} plans détectés")
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

        # ── 3. Compression ───────────────────────────────────────────────────
        step("🗜️ Compression de la vidéo...")
        compressed_path = compress_video(video_path, step)
        # Utilise le compressé pour la suite (plus rapide)
        working_path = compressed_path

        # ── 4. Détection scènes + extraction frames ──────────────────────────
        step("📸 Détection des plans (ffmpeg)...")
        scene_timestamps = detect_scene_changes(working_path, duree)
        frames = extract_frames_for_vision(working_path, scene_timestamps)
        step(f"📸 {len(frames)} plans détectés via ffmpeg")

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
            duree_moyenne_plan=duree / max(len(plans_data), 1),
            rythme_coupes_par_seconde=float(metriques.get("rythme_coupes_par_seconde", 0)),
            luminosite_moyenne=float(metriques.get("luminosite_moyenne", 5)),
            presence_visage=_pct_to_bool(metriques.get("presence_visage_pourcentage", "0%")),
            presence_texte_ecran=_pct_to_bool(metriques.get("proportion_texte_ecran", "0%")),
            qualite_production=float(metriques.get("qualite_globale", 5)),
            type_tournage=metriques.get("type_tournage", ""),
            mouvement_dominant="",
        )
        session.add(ap)

        for i, p in enumerate(plans_data):
            plan_obj = Plan(
                video_id=video_id,
                numero_plan=i + 1,
                timestamp_debut=float(p.get("timestamp_debut", 0)),
                timestamp_fin=float(p.get("timestamp_fin", duree)),
                duree=float(p.get("timestamp_fin", duree)) - float(p.get("timestamp_debut", 0)),
                type_plan=p.get("type_plan", ""),
                description=p.get("sujet_principal", ""),
                luminosite=float(p.get("luminosite", 5)),
                mouvement=p.get("mouvement_camera", ""),
                presence_visage=bool(p.get("presence_visage", False)),
                expression=p.get("expression_visage", ""),
                texte_visible=p.get("texte_visible_ecran"),
                couleur_dominante=json.dumps(p.get("couleurs_dominantes", []), ensure_ascii=False),
                qualite=float(p.get("qualite_production", 5)),
                role_narratif=p.get("role_narratif", ""),
                points_forts=json.dumps(p.get("points_forts", []), ensure_ascii=False),
                suggestion_amelioration=p.get("suggestion_amelioration", ""),
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

        # ── 8. Analyse créative Claude ───────────────────────────────────────
        step("🧠 Analyse créative (Claude Haiku)...")
        creative_data, claude_usage = analyze_creative(pegasus_data, whisper_result, similar_videos)
        if claude_usage:
            total_cout += claude_usage.get("cout_estime", 0)

        ac = AnalyseCreative(
            video_id=video_id,
            hook_texte=creative_data.get("hook_texte", hook.get("texte_dit", "")),
            hook_visuel=creative_data.get("hook_visuel", ""),
            hook_type=creative_data.get("hook_type", hook.get("type_hook", "")),
            hook_score=float(creative_data.get("hook_score", hook.get("score_accroche", 5))),
            hook_analyse=creative_data.get("hook_analyse", ""),
            structure_narrative=creative_data.get("structure_narrative", ""),
            points_forts=json.dumps(creative_data.get("points_forts", []), ensure_ascii=False),
            points_faibles=json.dumps(creative_data.get("points_faibles", []), ensure_ascii=False),
            score_potentiel=float(creative_data.get("score_potentiel", 5)),
            recommandations=json.dumps(creative_data.get("recommandations", []), ensure_ascii=False),
            comparaison_base=creative_data.get("comparaison_base", ""),
            adaptable_insolit=bool(creative_data.get("adaptable_insolit", True)),
            note_adaptation=creative_data.get("note_adaptation", ""),
        )
        session.add(ac)

        titre_auto = _generate_title(metadata, whisper_result, hook)
        video.titre = titre_auto
        session.commit()

        # ── 9. Screenshots ────────────────────────────────────────────────────
        step("📸 Extraction des screenshots...")
        shot_paths = extract_screenshots(working_path, plans_data, video_id)
        plans_db = session.query(Plan).filter_by(video_id=video_id).order_by(Plan.numero_plan).all()
        for plan_obj, shot_path in zip(plans_db, shot_paths):
            if shot_path:
                plan_obj.screenshot_path = shot_path
        session.commit()

        # ── 10. Finalisation ──────────────────────────────────────────────────
        video.statut_analyse = "complete"
        session.commit()

        elapsed = round(time.time() - start_time)
        step(f"✅ Terminé en {elapsed}s | Coût : ~${total_cout:.4f}")

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
            "cout_total": total_cout,
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


def _generate_title(metadata: dict, whisper_data: dict, hook_data: dict) -> str:
    partenaire = metadata.get("partenaire", "")
    ville = metadata.get("ville", "")
    hook_text = hook_data.get("texte_dit", "")
    if partenaire and ville:
        return f"{partenaire} — {ville}"
    elif hook_text:
        return hook_text[:80]
    elif partenaire:
        return partenaire
    else:
        return f"Vidéo du {datetime.now().strftime('%d/%m/%Y %H:%M')}"
