import os
import ssl
import json
import logging
import subprocess
import time
import certifi
from pathlib import Path
from datetime import datetime
from modules._env import _ROOT  # noqa — charge .env

# Fix SSL pour Whisper et requêtes HTTPS
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# Injection PATH anticipée — nécessaire pour ffmpeg (Whisper) et yt-dlp
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

VOLUME_PATH = os.getenv("RAILWAY_VOLUME_PATH", "./uploads")
SCREENSHOTS_PATH = "./screenshots"

# Détecte si on tourne sur Railway/Linux ou macOS local
IS_RAILWAY = os.getenv("RAILWAY_ENVIRONMENT") is not None or os.path.exists("/usr/bin/ffmpeg")

# Chemins des binaires — cherche dans plusieurs emplacements courants
def _find_bin(name: str) -> str:
    candidates = [
        # Railway / Linux
        Path("/usr/bin") / name,
        Path("/usr/local/bin") / name,
        # macOS local
        Path.home() / "bin" / name,
        Path("/Library/Frameworks/Python.framework/Versions/3.14/bin") / name,
        Path("/opt/homebrew/bin") / name,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return name  # fallback: laisse le shell chercher

YTDLP_BIN = _find_bin("yt-dlp")
FFMPEG_BIN = _find_bin("ffmpeg")
FFPROBE_BIN = _find_bin("ffprobe")


def _ensure_dirs():
    os.makedirs(VOLUME_PATH, exist_ok=True)
    os.makedirs(SCREENSHOTS_PATH, exist_ok=True)


def download_video(url: str, video_id: int, progress_callback=None) -> str:
    """Télécharge une vidéo via yt-dlp — gère TikTok, Instagram, YouTube."""
    _ensure_dirs()
    output_path = os.path.join(VOLUME_PATH, f"{video_id}.mp4")

    if progress_callback:
        progress_callback("Téléchargement de la vidéo...")

    is_tiktok = "tiktok.com" in url
    is_instagram = "instagram.com" in url

    # Construire la commande selon la plateforme
    base_cmd = [YTDLP_BIN, "--no-playlist", "-o", output_path]

    if is_tiktok or is_instagram:
        if not IS_RAILWAY:
            # macOS local : Chrome cookies disponibles
            base_cmd += ["--cookies-from-browser", "chrome"]
        else:
            # Railway/serveur : pas de Chrome, utilise user-agent + headers
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
                # Vérifie que le fichier existe (yt-dlp peut changer l'extension)
                if not os.path.exists(output_path):
                    # Cherche un fichier avec le même nom mais extension différente
                    base = os.path.splitext(output_path)[0]
                    for ext in [".mp4", ".webm", ".mkv", ".mov"]:
                        if os.path.exists(base + ext):
                            os.rename(base + ext, output_path)
                            break
                logger.info(f"Vidéo téléchargée: {output_path}")
                return output_path
            else:
                err = result.stderr[-500:]
                if "private" in err.lower() or "login" in err.lower():
                    raise RuntimeError("Compte privé — impossible d'accéder à cette vidéo.")
                logger.warning(f"yt-dlp tentative {attempt+1}/3 : {err[-200:]}")
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
    """Copie un fichier uploadé vers le répertoire de stockage."""
    _ensure_dirs()
    ext = Path(filename).suffix or ".mp4"
    output_path = os.path.join(VOLUME_PATH, f"{video_id}{ext}")
    with open(output_path, "wb") as f:
        f.write(file_bytes)
    logger.info(f"Fichier copié: {output_path}")
    return output_path


def get_video_duration(video_path: str) -> float:
    """Retourne la durée d'une vidéo en secondes via ffprobe."""
    try:
        cmd = [
            FFPROBE_BIN, "-v", "quiet", "-print_format", "json",
            "-show_format", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 0.0


def extract_screenshots(video_path: str, plans: list, video_id: int, progress_callback=None) -> list:
    """Extrait 1 frame par plan via ffmpeg."""
    if not plans:
        return []

    screenshots_dir = os.path.join(SCREENSHOTS_PATH, str(video_id))
    os.makedirs(screenshots_dir, exist_ok=True)

    paths = []
    total = len(plans)

    for i, plan in enumerate(plans):
        if progress_callback:
            progress_callback(f"Screenshot {i+1}/{total}...")

        ts = plan.get("timestamp_debut", 0)
        output = os.path.join(screenshots_dir, f"plan_{i+1:02d}.jpg")
        try:
            cmd = [
                FFMPEG_BIN, "-y", "-ss", str(ts),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                output
            ]
            subprocess.run(cmd, capture_output=True, timeout=15)
            paths.append(output if os.path.exists(output) else None)
        except Exception as e:
            logger.warning(f"Screenshot plan {i+1} échoué: {e}")
            paths.append(None)

    return paths


def analyze_video(
    source: str,
    metadata: dict,
    progress_callback=None,
    is_url: bool = True,
    file_bytes: bytes = None,
    filename: str = None,
) -> dict:
    """
    Pipeline principal d'analyse vidéo.
    Retourne un dict complet avec toutes les données.
    """
    from modules.database import (
        get_session, Video, AnalysePegasus, Plan,
        Transcription, AnalyseCreative, init_db
    )
    from modules.twelvelabs import (
        analyze_with_pegasus, get_marengo_embedding, search_similar_videos
    )
    from modules.whisper_mod import transcribe
    from modules.claude_mod import analyze_creative

    init_db()
    session = get_session()
    start_time = time.time()
    total_cout = 0.0

    def step(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    try:
        # ── Étape 1 : Création entrée DB ──────────────────────────────────────
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

        # ── Étape 1 : Acquisition ─────────────────────────────────────────────
        step("⬇️ Récupération de la vidéo...")
        if is_url:
            video_path = download_video(source, video_id, step)
        else:
            video_path = copy_uploaded_video(file_bytes, filename, video_id)

        duree = get_video_duration(video_path)
        video.fichier_path = video_path
        video.duree_secondes = duree
        session.commit()
        step(f"⬇️ Vidéo récupérée ({duree:.0f}s)")

        # ── Étape 2 : Pegasus 1.1 ─────────────────────────────────────────────
        step("🎬 Analyse des plans (Pegasus)...")
        pegasus_data = analyze_with_pegasus(video_path, step)

        plans_data = pegasus_data.get("plans", [])
        metriques = pegasus_data.get("metriques_globales", {})
        hook = pegasus_data.get("hook_analyse", {})

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
                timestamp_fin=float(p.get("timestamp_fin", 0)),
                duree=float(p.get("timestamp_fin", 0)) - float(p.get("timestamp_debut", 0)),
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

        session.commit()
        step(f"🎬 {len(plans_data)} plans détectés")

        # ── Étape 3 : Marengo embeddings ──────────────────────────────────────
        step("🔍 Recherche vidéos similaires (Marengo)...")
        embedding = get_marengo_embedding(video_path)
        similar_videos = []

        if embedding:
            ap.set_embedding(embedding)
            session.commit()

            all_embeddings = _load_all_embeddings(session, exclude_id=video_id)
            similar_videos = search_similar_videos(embedding, all_embeddings, top_k=5)
            step(f"🔍 {len(similar_videos)} vidéos similaires trouvées")
        else:
            step("🔍 Embedding non disponible")

        # ── Étape 4 : Whisper ─────────────────────────────────────────────────
        step("📝 Transcription (Whisper)...")
        whisper_result = transcribe(video_path, step)

        for w in whisper_result.get("mots", []):
            t = Transcription(
                video_id=video_id,
                timestamp=w["start"],
                mot=w["mot"],
                confiance=w["confiance"],
            )
            session.add(t)
        session.commit()
        step(f"📝 {whisper_result.get('nb_mots', 0)} mots transcrits")

        # ── Étape 5 : Claude ──────────────────────────────────────────────────
        step("🧠 Analyse créative (Claude)...")
        similar_for_claude = [
            {
                "video_id": s.get("video_id"),
                "titre": s.get("titre"),
                "vues": s.get("vues"),
                "similarite": s.get("similarite"),
                "hook_texte": s.get("hook_texte"),
                "score_potentiel": s.get("score_potentiel"),
            }
            for s in similar_videos
        ]

        creative_data, claude_usage = analyze_creative(pegasus_data, whisper_result, similar_for_claude)
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
        step("🧠 Analyse créative générée")

        # ── Étape 6 : Screenshots ─────────────────────────────────────────────
        step("📸 Extraction des screenshots...")
        shot_paths = extract_screenshots(video_path, plans_data, video_id, step)

        plans_db = session.query(Plan).filter_by(video_id=video_id).order_by(Plan.numero_plan).all()
        for plan_obj, shot_path in zip(plans_db, shot_paths):
            if shot_path:
                plan_obj.screenshot_path = shot_path
        session.commit()
        step(f"📸 {len([p for p in shot_paths if p])} screenshots extraits")

        # ── Étape 7 : Finalisation ────────────────────────────────────────────
        video.statut_analyse = "complete"
        session.commit()

        elapsed = round(time.time() - start_time)
        step(f"✅ Terminé en {elapsed}s | Coût estimé : ~${total_cout:.4f}")

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
        logger.error(f"Erreur pipeline analyse: {e}", exc_info=True)
        try:
            video.statut_analyse = "erreur"
            session.commit()
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def _pct_to_bool(pct_str: str) -> bool:
    try:
        val = float(str(pct_str).replace("%", "").strip())
        return val > 20
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
                "video_id": v.id,
                "titre": v.titre,
                "nom_compte": v.nom_compte,
                "embedding": emb,
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
