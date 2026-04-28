import html as _html
import json
import os
import time
import subprocess
import logging
import streamlit as st
from dotenv import load_dotenv


def _e(val) -> str:
    """html.escape sur n'importe quelle valeur — indispensable avant injection dans du HTML."""
    if val is None:
        return "—"
    return _html.escape(str(val))

load_dotenv()
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Analyser un compte — Insolit Studio", page_icon="🔭", layout="wide")

from modules.styles import apply_styles
apply_styles()

st.markdown("""
<style>
.fiche-compte { background:#0a0a0a; border:1px solid #ff00a4; border-radius:16px; padding:1.5rem; }
</style>
""", unsafe_allow_html=True)

from modules.analyzer import (
    YTDLP_BIN, FFMPEG_BIN, FFPROBE_BIN, _ensure_dirs,
    VOLUME_PATH, SCREENSHOTS_PATH, IS_RAILWAY, get_ytdlp_cookie_args,
)
from modules.database import get_session, get_all_videos_with_stats, get_precision_level

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _clean_username(raw: str) -> str:
    raw = raw.strip().lstrip("@")
    for prefix in ["https://www.tiktok.com/@", "https://tiktok.com/@",
                   "https://www.instagram.com/", "https://instagram.com/"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    return raw.split("?")[0].strip("/")


def get_account_videos(username: str, platform: str, nb_videos: int, progress_cb=None) -> list:
    """Récupère la liste des vidéos d'un compte via yt-dlp --flat-playlist."""
    if platform == "TikTok":
        url = f"https://www.tiktok.com/@{username}"
    else:
        url = f"https://www.instagram.com/{username}/"

    if progress_cb:
        progress_cb(f"📋 Récupération des {nb_videos} dernières vidéos de @{username}...")

    cmd = (
        [YTDLP_BIN]
        + get_ytdlp_cookie_args()
        + [
            "--flat-playlist",
            "--playlist-end", str(nb_videos),
            "--print", "%(id)s\t%(title)s\t%(url)s\t%(view_count)s\t%(like_count)s\t%(comment_count)s\t%(duration)s\t%(upload_date)s\t%(music_track)s\t%(music_author)s\t%(is_original_sound)s",
            "--no-warnings",
            url,
        ]
    )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            err = result.stderr.lower()
            if "private" in err or "login" in err:
                raise RuntimeError("Compte privé — impossible d'analyser ce compte.")
            if "not found" in err or "404" in err:
                raise RuntimeError(f"Compte @{username} introuvable.")
            logger.warning(f"yt-dlp stderr: {result.stderr[-300:]}")

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                def safe_int(v):
                    try: return int(v)
                    except: return None
                def safe_float(v):
                    try: return float(v)
                    except: return None

                music_track = parts[8] if len(parts) > 8 else ""
                music_author = parts[9] if len(parts) > 9 else ""
                is_orig_raw = parts[10] if len(parts) > 10 else ""
                is_original = is_orig_raw.strip().lower() in ("true", "1", "yes") if is_orig_raw else False
                videos.append({
                    "id": parts[0] if len(parts) > 0 else "",
                    "titre": parts[1] if len(parts) > 1 else "",
                    "url": parts[2] if len(parts) > 2 else "",
                    "vues": safe_int(parts[3]) if len(parts) > 3 else None,
                    "likes": safe_int(parts[4]) if len(parts) > 4 else None,
                    "comments": safe_int(parts[5]) if len(parts) > 5 else None,
                    "duree": safe_float(parts[6]) if len(parts) > 6 else None,
                    "date": parts[7] if len(parts) > 7 else "",
                    "music_track": music_track,
                    "music_author": music_author,
                    "is_original_sound": is_original,
                })

        logger.info(f"Compte @{username}: {len(videos)} vidéos récupérées")
        return videos

    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout récupération compte (120s). Réessaie.")
    except FileNotFoundError:
        raise RuntimeError(f"yt-dlp introuvable: {YTDLP_BIN}")


def generate_account_report(username: str, platform: str, analyses: list) -> tuple[dict, dict]:
    """Génère le rapport de compte via Claude."""
    from modules.claude_mod import _call_claude

    data_str = json.dumps(analyses, ensure_ascii=False, indent=2)
    prompt = f"""Tu analyses le compte @{username} sur {platform} pour Insolit (bons plans restaurants IDF).

DONNÉES DES {len(analyses)} VIDÉOS ANALYSÉES :
{data_str}

Génère un rapport JSON complet (sans markdown) :

{{
  "resume_compte": {{
    "style_visuel_dominant": "description",
    "ton_editorial": "description",
    "frequence_publication": "estimation",
    "points_forts_compte": ["point1", "point2", "point3"],
    "points_faibles_compte": ["point1", "point2"]
  }},
  "meilleures_videos": [
    {{
      "titre": "titre ou description",
      "pourquoi_ca_marche": "explication précise",
      "elements_reproductibles": ["élément1", "élément2"]
    }}
  ],
  "pires_videos": [
    {{
      "titre": "titre ou description",
      "pourquoi_ca_pas_marche": "explication",
      "erreurs_a_eviter": ["erreur1"]
    }}
  ],
  "patterns_gagnants": [
    {{
      "pattern": "description du pattern",
      "frequence": "X sur Y vidéos",
      "impact_estime": "description"
    }}
  ],
  "hooks_qui_marchent": [
    {{
      "hook_complet": "description des 3-4 premières secondes combinant visuel + auditif + texte",
      "visuel_hook": "ce qu'on voit exactement (plan, sujet, action, mouvement, couleurs)",
      "auditif_hook": "ce qu'on entend exactement (voix, son, musique, silence)",
      "texte_ecran_hook": "texte exact affiché à l'écran (ou 'aucun')",
      "mecanique": "pourquoi ces 3-4s donnent envie de continuer (curiosité/FOMO/conflit/désir/humour)",
      "score": 8,
      "ce_qui_manque": "ce qui pourrait rendre ce hook encore plus fort"
    }}
  ],
  "opportunites_insolit": [
    "comment s'inspirer concrètement pour Insolit"
  ],
  "score_compte_global": 7,
  "verdict": "Analyse directe en 3 phrases sur ce compte et son utilité pour Insolit."
}}"""

    try:
        text, usage = _call_claude(prompt, max_tokens=7000)
        from modules.claude_mod import _parse_json_response
        parsed = _parse_json_response(text)
        if "_error" in parsed:
            logger.warning(f"Rapport compte JSON error: {parsed.get('_error')} | raw[:200]: {text[:200]}")
        return parsed, usage
    except Exception as e:
        logger.error(f"Erreur rapport compte: {e}")
        return {"_error": str(e)}, {}


def fetch_and_store_comments(url, video_id, ytdlp_cookie_args):
    """Amélioration 4 — Récupère et stocke les top commentaires d'une vidéo."""
    import json as _json
    from modules.database import get_session, TopCommentaire
    from modules.claude_mod import _call_claude

    tmp_prefix = "/tmp/insolit_comments"
    tmp_info = tmp_prefix + ".info.json"

    # Nettoyer le fichier éventuel précédent
    try:
        os.remove(tmp_info)
    except Exception:
        pass

    cmd = (
        [YTDLP_BIN]
        + ytdlp_cookie_args
        + [
            "--write-comments", "--max-comments", "5",
            "--skip-download", "--no-warnings",
            "--write-info-json", "-o", tmp_prefix,
            url,
        ]
    )
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception as e:
        logger.warning("fetch_and_store_comments subprocess error: " + str(e))
        return None

    if not os.path.exists(tmp_info):
        return None

    try:
        with open(tmp_info, "r", encoding="utf-8") as fh:
            info = _json.load(fh)
    except Exception as e:
        logger.warning("fetch_and_store_comments JSON parse error: " + str(e))
        return None

    comments = info.get("comments", [])
    if not comments:
        return None

    top5 = comments[:5]
    sess = get_session()
    insight_str = None
    try:
        for pos, c in enumerate(top5):
            texte = str(c.get("text", ""))[:1000]
            nb_likes = int(c.get("like_count", 0) or 0)
            tc_obj = TopCommentaire(
                video_id=video_id,
                texte=texte,
                nb_likes=nb_likes,
                position=pos + 1,
            )
            sess.add(tc_obj)
        sess.flush()

        # Insight Claude Haiku
        textes_joint = "\n".join(
            str(pos + 1) + ". " + str(c.get("text", ""))[:200]
            for pos, c in enumerate(top5)
        )
        prompt = (
            "Voici les 5 principaux commentaires de cette vidéo :\n"
            + textes_joint
            + "\n\nDonne un insight court (1-2 phrases) sur ce que ces commentaires révèlent sur l'audience et pourquoi cette vidéo a engagé. Sois direct et actionnable."
        )
        try:
            insight_text, _ = _call_claude(prompt, max_tokens=200)
            insight_str = insight_text.strip()
            # Mettre à jour le premier commentaire avec l'insight
            for tc in sess.new:
                if isinstance(tc, TopCommentaire) and tc.video_id == video_id:
                    tc.insight_claude = insight_str
                    break
        except Exception as e:
            logger.warning("Claude insight commentaires: " + str(e))

        sess.commit()
    except Exception as e:
        sess.rollback()
        logger.warning("fetch_and_store_comments DB error: " + str(e))
    finally:
        sess.close()

    try:
        os.remove(tmp_info)
    except Exception:
        pass

    return insight_str


# ─── UI ───────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="padding:1.5rem 0 0.5rem 0;">
    <h1 style="font-size:2rem;font-weight:900;color:#ff00a4;margin:0;">🔭 Analyser un compte</h1>
    <p style="color:#555;margin-top:0.3rem;">Analyse automatique complète de tous les contenus d'un compte TikTok ou Instagram</p>
</div>
""", unsafe_allow_html=True)

# ─── Statut cookies ───────────────────────────────────────────────────────────
_has_cookies_b64 = bool(os.getenv("TIKTOK_COOKIES_B64", "").strip())
if IS_RAILWAY and not _has_cookies_b64:
    st.warning(
        "⚠️ **Railway détecté sans cookies TikTok** — l'analyse de compte peut échouer sur les vidéos privées/protégées. "
        "Pour activer : exporte `cookies.txt` depuis Chrome (extension *Get cookies.txt LOCALLY*), "
        "encode en base64 et ajoute `TIKTOK_COOKIES_B64` dans les variables Railway.",
        icon="🍪",
    )
elif IS_RAILWAY and _has_cookies_b64:
    st.success("🍪 Cookies TikTok configurés — accès complet activé.", icon="✅")

# ─── Section A — Input ────────────────────────────────────────────────────────
with st.container():
    col1, col2 = st.columns([2, 1])
    with col1:
        compte_input = st.text_input(
            "@nomducompte ou URL du profil",
            placeholder="@strop.bon ou https://www.tiktok.com/@strop.bon",
            key="compte_input"
        )
    with col2:
        plateforme = st.radio("Plateforme", ["TikTok", "Instagram"], horizontal=True, key="plateforme")

    col3, col4 = st.columns([1, 1])
    with col3:
        nb_videos = st.select_slider(
            "Nombre de vidéos à analyser",
            options=[5, 10, 20, 50],
            value=10,
            key="nb_videos"
        )
    with col4:
        type_compte = st.selectbox(
            "Type de compte",
            ["Concurrent", "Inspiration", "Secteur", "Mon compte"],
            key="type_compte"
        )

    col5, col6 = st.columns([1, 1])
    with col5:
        categorie = st.selectbox(
            "Catégorie",
            ["Restaurant", "Bar", "Café", "Expérience", "Bon plan", "Tendance food", "Lifestyle", "Voyage IDF", "Autre"],
            key="categorie_compte"
        )
    with col6:
        recuperer_commentaires = st.toggle(
            "Récupérer les commentaires (plus lent +30s)",
            value=False,
            key="recup_comments"
        )

launch_btn = st.button("🚀 LANCER L'ANALYSE DU COMPTE", use_container_width=True, type="primary")

# ─── Pipeline ─────────────────────────────────────────────────────────────────
if launch_btn:
    if not compte_input.strip():
        st.error("Entre un nom de compte ou une URL.")
        st.stop()

    username = _clean_username(compte_input)
    type_map = {"Mon compte": "mon_compte", "Concurrent": "concurrent",
                "Inspiration": "inspiration", "Secteur": "secteur"}
    type_source = type_map.get(type_compte, "concurrent")

    st.markdown("---")
    st.markdown(f"### Analyse de **@{username}** sur {plateforme}")

    progress_global = st.progress(0)
    status_global = st.empty()

    # ── Étape 1 : Récupération de la playlist ─────────────────────────────────
    try:
        videos_list = get_account_videos(
            username, plateforme, nb_videos,
            progress_cb=lambda msg: status_global.markdown(f"**{msg}**")
        )
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    if not videos_list:
        st.error(f"Aucune vidéo trouvée pour @{username}. Vérifie le nom du compte.")
        st.stop()

    nb_found = len(videos_list)
    status_global.success(f"📋 {nb_found} vidéos trouvées sur @{username}")
    progress_global.progress(5)

    # ── Étape 2 : Analyse de chaque vidéo ────────────────────────────────────
    from modules.analyzer import analyze_video

    analyses_results = []
    errors = []
    start_time = time.time()

    progress_container = st.empty()
    video_status = st.empty()

    for i, vid in enumerate(videos_list):
        pct = 5 + int((i / nb_found) * 85)
        progress_global.progress(pct)

        elapsed = time.time() - start_time
        reste = (elapsed / max(i, 1)) * (nb_found - i) if i > 0 else 0
        reste_min = int(reste // 60)
        reste_sec = int(reste % 60)

        progress_container.markdown(f"""
        <div class="card card-cyan">
            <strong>Analyse en cours : {i+1}/{nb_found} vidéos</strong><br>
            <div style="background:#111;border-radius:4px;height:6px;margin:8px 0;">
                <div style="background:linear-gradient(90deg,#0000ff,#01f0fc,#ff00a4);width:{int((i/nb_found)*100)}%;height:6px;border-radius:4px;"></div>
            </div>
            Temps restant estimé : ~{reste_min}min {reste_sec}s
        </div>
        """, unsafe_allow_html=True)

        url_video = vid.get("url", "")
        if not url_video:
            errors.append(f"Vidéo {i+1}: URL manquante")
            continue

        video_status.markdown(f"⬇️ Vidéo {i+1}/{nb_found} : {vid.get('titre', '')[:60]}...")

        metadata = {
            "type_source": type_source,
            "nom_compte": username,
            "categorie": categorie,
            "partenaire": "",
            "ville": "",
        }

        try:
            result = analyze_video(
                source=url_video,
                metadata=metadata,
                is_url=True,
            )
            if result.get("success"):
                # Enrichit avec les stats yt-dlp
                from modules.database import get_session, Stats, Video as _VideoModel, compute_engagement_ratios
                if vid.get("vues") or vid.get("likes"):
                    sess = get_session()
                    try:
                        stats = Stats(
                            video_id=result["video_id"],
                            vues=vid.get("vues"),
                            likes=vid.get("likes"),
                            comments=vid.get("comments"),
                        )
                        if vid.get("vues"):
                            vues = vid["vues"]
                            if vues >= 500_000:
                                stats.performance_tag = "viral"
                            elif vues >= 50_000:
                                stats.performance_tag = "bon"
                            elif vues >= 10_000:
                                stats.performance_tag = "moyen"
                            else:
                                stats.performance_tag = "mauvais"
                        compute_engagement_ratios(stats)
                        sess.add(stats)
                        sess.commit()
                    finally:
                        sess.close()

                # Amélioration 3 — jour de publication
                date_str = vid.get("date", "")
                if date_str and len(date_str) == 8:
                    try:
                        from datetime import datetime as _dt
                        d = _dt.strptime(date_str, "%Y%m%d")
                        _JOURS = {
                            "Monday": "lundi", "Tuesday": "mardi", "Wednesday": "mercredi",
                            "Thursday": "jeudi", "Friday": "vendredi",
                            "Saturday": "samedi", "Sunday": "dimanche"
                        }
                        jour_fr = _JOURS.get(d.strftime("%A"), d.strftime("%A").lower())
                        sess2 = get_session()
                        try:
                            video_obj = sess2.query(_VideoModel).filter_by(id=result["video_id"]).first()
                            if video_obj:
                                video_obj.jour_publication = jour_fr
                                sess2.commit()
                        finally:
                            sess2.close()
                    except Exception as _e:
                        logger.warning("jour_publication: " + str(_e))

                # Amélioration 6 — son/musique
                music_track = vid.get("music_track", "")
                music_author = vid.get("music_author", "")
                is_orig = vid.get("is_original_sound", False)
                if music_track or music_author:
                    sess3 = get_session()
                    try:
                        video_obj3 = sess3.query(_VideoModel).filter_by(id=result["video_id"]).first()
                        if video_obj3:
                            video_obj3.nom_son = str(music_track)[:500] if music_track else ""
                            video_obj3.auteur_son = str(music_author)[:200] if music_author else ""
                            video_obj3.son_original = bool(is_orig)
                            sess3.commit()
                    finally:
                        sess3.close()

                # Amélioration 4 — commentaires
                if recuperer_commentaires:
                    try:
                        fetch_and_store_comments(
                            url_video, result["video_id"], get_ytdlp_cookie_args()
                        )
                    except Exception as _e:
                        logger.warning("commentaires: " + str(_e))

                analyses_results.append({
                    "video_id": result.get("video_id"),
                    "titre": result.get("titre"),
                    "url": url_video,
                    "vues": vid.get("vues"),
                    "likes": vid.get("likes"),
                    "duree": vid.get("duree"),
                    "cout": result.get("cout_total", 0),
                    "pegasus": result.get("pegasus_data", {}),
                    "whisper_texte": result.get("whisper_data", {}).get("texte_complet", ""),
                    "creative": result.get("creative_data", {}),
                    "nb_plans": result.get("plans_count", 0),
                    "score_potentiel": result.get("creative_data", {}).get("score_potentiel"),
                    "hook_texte": result.get("creative_data", {}).get("hook_texte"),
                    "hook_score": result.get("creative_data", {}).get("hook_score"),
                })
            else:
                errors.append(f"Vidéo {i+1}: {result.get('error', 'Erreur inconnue')}")
                logger.warning(f"Vidéo {i+1} échouée: {result.get('error')}")
        except Exception as e:
            errors.append(f"Vidéo {i+1}: {str(e)}")
            logger.error(f"Vidéo {i+1} exception: {e}", exc_info=True)

        # Rate limit entre chaque vidéo
        if i < nb_found - 1:
            time.sleep(3)

    progress_global.progress(90)
    video_status.empty()

    total_cout = sum(r.get("cout", 0) for r in analyses_results)
    elapsed_total = int(time.time() - start_time)

    if not analyses_results:
        st.error("Aucune vidéo n'a pu être analysée.")
        if errors:
            with st.expander("Erreurs"):
                for e in errors:
                    st.text(e)
        st.stop()

    # ── Étape 3 : Rapport Claude ──────────────────────────────────────────────
    status_global.markdown("**🧠 Génération du rapport de compte (Claude)...**")

    analyses_for_claude = [
        {
            "titre": r["titre"],
            "vues": r["vues"],
            "likes": r["likes"],
            "duree": r["duree"],
            "nb_plans": r["nb_plans"],
            "score_potentiel": r["score_potentiel"],
            "hook_texte": r["hook_texte"],
            "hook_score": r["hook_score"],
            "transcription": r["whisper_texte"][:300] if r["whisper_texte"] else "",
            "hook_analyse": r.get("pegasus", {}).get("hook_analyse", {}),
            "metriques": r.get("pegasus", {}).get("metriques_globales", {}),
        }
        for r in analyses_results
    ]

    rapport, claude_usage = generate_account_report(username, plateforme, analyses_for_claude)
    total_cout += claude_usage.get("cout_estime", 0)

    progress_global.progress(100)
    status_global.success(
        f"✅ {len(analyses_results)}/{nb_found} vidéos analysées | "
        f"Coût total : ~${total_cout:.3f} | Durée : {elapsed_total//60}min {elapsed_total%60}s"
    )
    if errors:
        with st.expander(f"⚠️ {len(errors)} erreurs"):
            for e in errors:
                st.text(e)

    # Sauvegarde en session
    st.session_state["last_compte_analysis"] = {
        "username": username,
        "plateforme": plateforme,
        "analyses": analyses_results,
        "rapport": rapport,
        "total_cout": total_cout,
        "elapsed": elapsed_total,
    }

# ─── Section B — Résultats ────────────────────────────────────────────────────
if "last_compte_analysis" in st.session_state:
    data = st.session_state["last_compte_analysis"]
    username = data["username"]
    plateforme = data["plateforme"]
    rapport = data.get("rapport", {})
    analyses = data.get("analyses", [])
    resume = rapport.get("resume_compte", {})

    st.markdown("---")

    # ── BLOC 1 — Fiche compte ─────────────────────────────────────────────────
    score_raw = rapport.get("score_compte_global", None)
    try:
        score_val = float(score_raw)
        score_display = str(round(score_val, 1))
        score_bar = int(score_val * 10)
    except (TypeError, ValueError):
        score_display = "—"
        score_bar = 50

    pf = resume.get("points_forts_compte", [])
    ppf = resume.get("points_faibles_compte", [])
    opps = rapport.get("opportunites_insolit", [])

    # Affichage erreur JSON si le rapport a échoué
    if rapport.get("_error"):
        st.error("⚠️ Le rapport IA n'a pas pu être généré correctement. Les données brutes des vidéos sont tout de même sauvegardées.")

    pf_html  = "".join('<div style="font-size:0.85rem;margin-bottom:3px;">• ' + _e(p) + '</div>' for p in pf[:3])
    ppf_html = "".join('<div style="font-size:0.85rem;margin-bottom:3px;">• ' + _e(p) + '</div>' for p in ppf[:2])
    opp_html = "".join('<div style="font-size:0.85rem;margin-bottom:3px;">• ' + _e(o) + '</div>' for o in opps[:2])

    fiche_html = (
        '<div class="fiche-compte">'
        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">'
        '<div>'
        '<span style="font-size:1.4rem;font-weight:900;color:#ff00a4;">@' + _e(username) + '</span>'
        '<span style="color:#555;margin-left:8px;">' + _e(plateforme) + '</span>'
        '</div>'
        '<div style="text-align:right;">'
        '<div style="font-size:0.85rem;color:#888;">' + str(len(analyses)) + ' vidéos analysées</div>'
        '<div style="font-size:1.1rem;font-weight:700;color:#01f0fc;">Score global : ' + score_display + '/10</div>'
        '<div style="background:#111;border-radius:4px;height:6px;width:150px;margin-top:4px;">'
        '<div style="background:linear-gradient(90deg,#0000ff,#ff00a4);width:' + str(score_bar) + '%;height:6px;border-radius:4px;"></div>'
        '</div>'
        '</div>'
        '</div>'
        '<div style="margin-top:1rem;display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;">'
        '<div>'
        '<div style="font-size:0.7rem;color:#555;text-transform:uppercase;letter-spacing:1px;">Style</div>'
        '<div style="color:#01f0fc;font-size:0.9rem;">' + _e(resume.get("style_visuel_dominant")) + '</div>'
        '<div style="font-size:0.7rem;color:#555;margin-top:8px;text-transform:uppercase;letter-spacing:1px;">Ton</div>'
        '<div style="color:#01f0fc;font-size:0.9rem;">' + _e(resume.get("ton_editorial")) + '</div>'
        '</div>'
        '<div>'
        '<div style="font-size:0.75rem;color:#888;margin-bottom:4px;">✅ Points forts</div>'
        + pf_html +
        '</div>'
        '<div>'
        '<div style="font-size:0.75rem;color:#888;margin-bottom:4px;">⚠️ Points faibles</div>'
        + ppf_html +
        '<div style="font-size:0.75rem;color:#888;margin-top:8px;margin-bottom:4px;">💡 Pour Insolit</div>'
        + opp_html +
        '</div>'
        '</div>'
        '<div style="margin-top:1rem;padding-top:1rem;border-top:1px solid #1a1a1a;color:#aaa;font-style:italic;font-size:0.9rem;">'
        + _e(rapport.get("verdict")) +
        '</div>'
        '</div>'
    )
    st.markdown(fiche_html, unsafe_allow_html=True)

    # ── BLOC 2 — Top vidéos ───────────────────────────────────────────────────
    meilleures = rapport.get("meilleures_videos", [])
    if meilleures:
        st.markdown("### 🏆 Top vidéos du compte")
        cols = st.columns(min(3, len(meilleures)))
        for i, v in enumerate(meilleures[:3]):
            with cols[i]:
                # Screenshot si dispo
                if i < len(analyses):
                    vid_id = analyses[i].get("video_id", "")
                    shot = os.path.join(SCREENSHOTS_PATH, str(vid_id), "plan_01.jpg")
                    if os.path.exists(shot):
                        st.image(shot, use_container_width=True)
                card_html = (
                    '<div class="card card-pink">'
                    '<div style="font-weight:700;font-size:0.9rem;color:#ff00a4;">#' + str(i+1) + '</div>'
                    '<div style="font-size:0.85rem;margin:4px 0;">' + _e(v.get("titre","—"))[:80] + '</div>'
                    '<div style="color:#888;font-size:0.8rem;margin-top:6px;">'
                    '<strong style="color:#01f0fc;">Pourquoi ça marche :</strong><br>'
                    + _e(v.get("pourquoi_ca_marche","—")) +
                    '</div>'
                    '</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)
                repro = v.get("elements_reproductibles", [])
                if repro:
                    for r in repro[:2]:
                        st.markdown("✅ " + str(r))

    # ── BLOC 3 — Patterns gagnants ────────────────────────────────────────────
    patterns = rapport.get("patterns_gagnants", [])
    if patterns:
        st.markdown("### 🔁 Patterns gagnants du compte")
        for p in patterns[:5]:
            p_html = (
                '<div class="card card-blue">'
                '<strong style="color:#01f0fc;">' + _e(p.get("pattern","—")) + '</strong>'
                '<span style="color:#555;margin-left:12px;font-size:0.8rem;">' + _e(p.get("frequence","")) + '</span><br>'
                '<span style="color:#888;font-size:0.85rem;">Impact : ' + _e(p.get("impact_estime","—")) + '</span>'
                '</div>'
            )
            st.markdown(p_html, unsafe_allow_html=True)

    # ── BLOC 4 — Hooks qui marchent ───────────────────────────────────────────
    hooks = rapport.get("hooks_qui_marchent", [])
    if hooks:
        st.markdown("### 🎣 Top hooks du compte")
        for h in hooks[:5]:
            score_h = h.get("score", 0)
            score_color = "#00C853" if score_h >= 8 else "#FFD700" if score_h >= 6 else "#FF6B35"

            # Nouveau format riche
            hook_complet   = h.get("hook_complet") or h.get("texte", "—")
            visuel         = h.get("visuel_hook", "")
            auditif        = h.get("auditif_hook", "")
            texte_ecran    = h.get("texte_ecran_hook", "")
            mecanique      = h.get("mecanique") or h.get("pourquoi", "")
            ce_qui_manque  = h.get("ce_qui_manque", "")

            # Lignes optionnelles — html.escape sur tous les champs Claude
            rows_html = ""
            if visuel:
                rows_html += '<div style="margin-bottom:4px;"><span style="color:#888;font-size:0.78em;">👁 VISUEL</span><br><span style="font-size:0.85em;">' + _e(visuel) + '</span></div>'
            if auditif:
                rows_html += '<div style="margin-bottom:4px;"><span style="color:#888;font-size:0.78em;">🔊 AUDITIF</span><br><span style="font-size:0.85em;">' + _e(auditif) + '</span></div>'
            if texte_ecran and texte_ecran.lower() not in ("aucun", "none", ""):
                rows_html += '<div style="margin-bottom:4px;"><span style="color:#888;font-size:0.78em;">📝 TEXTE ÉCRAN</span><br><span style="font-size:0.85em;font-weight:600;">' + _e(texte_ecran) + '</span></div>'
            if mecanique:
                rows_html += '<div style="margin-top:6px;padding-top:6px;border-top:1px solid #1a1a1a;"><span style="color:#ff00a4;font-size:0.78em;font-weight:700;">⚡ POURQUOI ÇA ACCROCHE</span><br><span style="font-size:0.85em;">' + _e(mecanique) + '</span></div>'
            if ce_qui_manque:
                rows_html += '<div style="margin-top:4px;"><span style="color:#888;font-size:0.78em;">⚠️ CE QUI MANQUE</span><br><span style="font-size:0.82em;color:#666;">' + _e(ce_qui_manque) + '</span></div>'

            st.markdown(
                '<div style="background:#0a0a0a;border:1px solid #222;border-left:3px solid ' + score_color + ';'
                'border-radius:8px;padding:1rem;margin-bottom:0.75rem;">'
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                '<span style="font-size:0.75em;color:#555;text-transform:uppercase;letter-spacing:1px;">HOOK</span>'
                '<span style="font-size:1.1rem;font-weight:900;color:' + score_color + ';">' + str(score_h) + '/10</span>'
                '</div>'
                '<div style="font-style:italic;font-size:0.9em;color:#ddd;margin-bottom:10px;">«' + _e(hook_complet) + '»</div>'
                + rows_html +
                '</div>',
                unsafe_allow_html=True,
            )

    # ── BLOC Sons — Sons des vidéos analysées ────────────────────────────────
    from modules.database import get_session as _gs, Video as _VidM
    _sons_data = []
    for _a in analyses:
        _vid_id_s = _a.get("video_id")
        if _vid_id_s:
            _s2 = _gs()
            try:
                _vo = _s2.query(_VidM).filter_by(id=_vid_id_s).first()
                if _vo and _vo.nom_son:
                    _sons_data.append({
                        "son": _vo.nom_son,
                        "auteur": _vo.auteur_son or "",
                        "original": _vo.son_original,
                    })
            finally:
                _s2.close()

    if _sons_data:
        st.markdown("### Sons des vidéos analysées")
        from collections import Counter as _Ctr
        sons_counter = _Ctr(_d["son"] for _d in _sons_data if _d.get("son"))
        nb_orig = sum(1 for _d in _sons_data if _d.get("original"))
        st.caption(
            str(len(_sons_data)) + " vidéos avec son · "
            + str(nb_orig) + " sons originaux ("
            + str(round(nb_orig / len(_sons_data) * 100)) + "%)"
        )
        for _son, _cnt in sons_counter.most_common(10):
            _auteur = next((_d["auteur"] for _d in _sons_data if _d["son"] == _son and _d.get("auteur")), "")
            _label = _son + (" — " + _auteur if _auteur else "") + " ×" + str(_cnt)
            st.markdown("- " + _label)

    # ── BLOC 5 — Grille complète ──────────────────────────────────────────────
    if analyses:
        st.markdown("### 📊 Toutes les vidéos analysées")
        analyses_sorted = sorted(analyses, key=lambda x: x.get("vues") or 0, reverse=True)

        from modules.database import Transcription, Plan as PlanDB

        def _load_transcript(video_id):
            """Charge les mots Whisper et les plans depuis la DB pour une vidéo."""
            if not video_id:
                return [], []
            sess = get_session()
            try:
                mots  = sess.query(Transcription).filter_by(video_id=video_id).order_by(Transcription.timestamp).all()
                plans = sess.query(PlanDB).filter_by(video_id=video_id).order_by(PlanDB.numero_plan).all()
                return (
                    [{"ts": m.timestamp, "mot": m.mot} for m in mots],
                    [{"num": p.numero_plan, "debut": p.timestamp_debut, "fin": p.timestamp_fin,
                      "texte": p.texte_visible or ""} for p in plans],
                )
            finally:
                sess.close()

        def _render_transcript(mots, plans, titre):
            """Formate la transcription groupée par plan."""
            if not mots:
                return None

            # Grouper les mots par plan
            def _plan_for_ts(ts, plans):
                for p in plans:
                    if p["debut"] <= ts <= p["fin"]:
                        return p["num"]
                return 0

            lines = []
            if plans:
                for p in plans:
                    mots_plan = [m["mot"] for m in mots if p["debut"] <= m["ts"] <= p["fin"]]
                    if not mots_plan and not p["texte"]:
                        continue
                    lines.append("PLAN " + str(p["num"]) + " (" + str(round(p["debut"], 1)) + "s–" + str(round(p["fin"], 1)) + "s) :")
                    if mots_plan:
                        lines.append('  Texte dit : "' + " ".join(mots_plan) + '"')
                    if p["texte"]:
                        lines.append("  Texte écran : " + p["texte"])
                    lines.append("")
            else:
                # Pas de plans — affichage mot par mot
                lines.append("MOT PAR MOT :")
                chunk = []
                for m in mots:
                    chunk.append("[" + str(round(m["ts"], 1)) + "s] " + m["mot"])
                    if len(chunk) >= 10:
                        lines.append("  " + "  ".join(chunk))
                        chunk = []
                if chunk:
                    lines.append("  " + "  ".join(chunk))

            return "\n".join(lines)

        # Pre-check quelles vidéos ont une transcription Whisper
        from modules.database import Transcription as _TransModel
        _all_vid_ids = [a.get("video_id") for a in analyses_sorted if a.get("video_id")]
        _sess_check = get_session()
        try:
            _vids_with_transcript = set(
                r[0] for r in _sess_check.query(_TransModel.video_id).filter(
                    _TransModel.video_id.in_(_all_vid_ids)
                ).distinct().all()
            )
        finally:
            _sess_check.close()

        cols = st.columns(3)
        for idx, a in enumerate(analyses_sorted):
            col = cols[idx % 3]
            with col:
                vid_id = a.get("video_id", "")
                shot = os.path.join(SCREENSHOTS_PATH, str(vid_id), "plan_01.jpg")
                if os.path.exists(shot):
                    st.image(shot, use_container_width=True)
                else:
                    st.markdown('<div style="background:#111;height:100px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#333;font-size:1.5rem;">🎬</div>', unsafe_allow_html=True)

                vues     = a.get("vues")
                vues_str = f"{vues:,}" if vues else "—"
                score_v  = a.get("score_potentiel", "—")
                titre_v  = str(a.get("titre") or "—")
                hook_txt = str(a.get("hook_texte") or "")
                st.markdown(
                    '<div style="padding:0.4rem 0;">'
                    '<div style="font-size:0.85rem;font-weight:600;">' + _e(titre_v[:45]) + '</div>'
                    '<div style="color:#888;font-size:0.78rem;margin-top:2px;">👁 ' + vues_str + ' · Score ' + str(score_v) + '/10</div>'
                    '<div style="color:#555;font-size:0.78rem;font-style:italic;">' + _e(hook_txt[:50]) + '</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

                # Accordéon transcript — seulement si données Whisper présentes
                if vid_id in _vids_with_transcript:
                    with st.expander("▶ Voir le script transcrit"):
                        mots_db, plans_db = _load_transcript(vid_id)
                        script_txt = _render_transcript(mots_db, plans_db, titre_v)
                        if script_txt:
                            st.text(script_txt)
                            st.button(
                                "📋 Copier ce script",
                                key="copy_script_" + str(vid_id) + "_" + str(idx),
                                on_click=lambda t=script_txt: st.session_state.update({"_copied_script": t}),
                            )
                            if st.session_state.get("_copied_script") == script_txt:
                                st.code(script_txt, language="")
                        else:
                            st.caption("Script structuré non disponible pour cette vidéo.")
                else:
                    st.caption("🔇 Pas de transcription audio — configurez OPENAI_API_KEY sur Railway pour activer Whisper.")

    # ── BLOC 6 — Comparaison avec ta base ────────────────────────────────────
    all_my_videos = get_all_videos_with_stats()
    my_annotated = [v for v in all_my_videos if v.get("performance_tag") in ["viral", "bon"]]

    if len(my_annotated) >= 5 and analyses:
        st.markdown("### ⚡ Ce compte vs tes meilleures vidéos")

        def _avg(lst, key):
            vals = [v.get(key) for v in lst if v.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else "—"

        compte_data = {
            "Durée moy (s)": _avg(analyses, "duree"),
            "Score potentiel": _avg(analyses, "score_potentiel"),
            "Hook score": _avg(analyses, "hook_score"),
        }
        mes_data = {
            "Durée moy (s)": _avg(my_annotated, "duree_secondes"),
            "Score potentiel": _avg(my_annotated, "score_potentiel"),
            "Hook score": _avg(my_annotated, "hook_score"),
        }

        import pandas as pd
        df_cmp = pd.DataFrame({
            "Variable": list(compte_data.keys()),
            f"@{username}": list(compte_data.values()),
            "Tes meilleures": list(mes_data.values()),
        })
        st.dataframe(df_cmp.set_index("Variable"), use_container_width=True)

    # ── Boutons d'action ──────────────────────────────────────────────────────
    st.markdown("---")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("💾 Tout dans la bibliothèque ✓", disabled=True, use_container_width=True):
            pass

    with col_b:
        if st.button("🎯 Générer brief inspiré de ce compte", use_container_width=True):
            st.session_state["brief_from_compte"] = username
            st.switch_page("pages/4_Generer.py")

    with col_c:
        # Export rapport texte
        if rapport and not rapport.get("_error"):
            rapport_txt = f"RAPPORT COMPTE @{username} — {plateforme}\n{'='*50}\n\n"
            rapport_txt += f"Score global : {rapport.get('score_compte_global')}/10\n"
            rapport_txt += f"Verdict : {rapport.get('verdict','')}\n\n"
            rapport_txt += f"Style : {resume.get('style_visuel_dominant','')}\n"
            rapport_txt += f"Ton : {resume.get('ton_editorial','')}\n\n"
            rapport_txt += "PATTERNS GAGNANTS :\n"
            for p in patterns[:5]:
                rapport_txt += f"  • {p.get('pattern')} ({p.get('frequence')})\n"
            rapport_txt += "\nOPPORTUNITÉS INSOLIT :\n"
            for o in opps:
                rapport_txt += f"  • {o}\n"

            st.download_button(
                "📄 Exporter le rapport",
                data=rapport_txt,
                file_name=f"rapport_{username}.txt",
                mime="text/plain",
                use_container_width=True
            )

    # Coût total
    nb, niveau = get_precision_level()
    st.markdown(f"""
    <div style="text-align:center;padding:1rem;color:#444;font-size:0.85rem;">
        {len(analyses)} vidéos analysées · Coût total : ~${data.get("total_cout",0):.3f} ·
        Durée : {data.get("elapsed",0)//60}min {data.get("elapsed",0)%60}s ·
        Base : {nb} annotées
    </div>
    """, unsafe_allow_html=True)
