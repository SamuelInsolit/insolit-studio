import html as _html
import json
import math
import os
import time
import subprocess
import logging
from datetime import date, timedelta
import streamlit as st
from dotenv import load_dotenv


def _e(val) -> str:
    """html.escape sur n'importe quelle valeur — avant toute injection dans du HTML."""
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
.mode-card-selected {
    background:#0a0a0a; border:2px solid #ff00a4; border-radius:12px;
    padding:0.8rem; cursor:pointer; text-align:center;
}
.mode-card {
    background:#0a0a0a; border:1px solid #222; border-radius:12px;
    padding:0.8rem; cursor:pointer; text-align:center;
}
</style>
""", unsafe_allow_html=True)

from modules.analyzer import (
    YTDLP_BIN, FFMPEG_BIN, FFPROBE_BIN, _ensure_dirs,
    VOLUME_PATH, SCREENSHOTS_PATH, IS_RAILWAY, get_ytdlp_cookie_args,
    get_cookies_status, validate_tiktok_cookies_live, reset_cookie_cache,
    COOKIES_FILE,
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


def _safe_int(v):
    try:
        return int(v)
    except Exception:
        return None


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _engagement_score(vid: dict) -> float:
    """(likes + comments×2) / vues × 100"""
    vues = vid.get("vues") or 0
    if vues == 0:
        return 0.0
    likes    = vid.get("likes") or 0
    comments = vid.get("comments") or 0
    return (likes + comments * 2) / vues * 100


def _auto_tag(vid: dict, mode: str) -> str:
    """Retourne le tag de performance selon le mode d'analyse choisi."""
    if mode == "pires":
        return "mauvais"
    if mode == "engagees":
        score = vid.get("_eng", 0)
        if score > 10:  return "viral"
        if score > 5:   return "bon"
        if score > 2:   return "moyen"
        return "mauvais"
    # meilleures ou moitié haute du mixte
    vues = vid.get("vues") or 0
    if vues >= 500_000: return "viral"
    if vues >= 50_000:  return "bon"
    if vues >= 10_000:  return "moyen"
    return "mauvais"


# ─── Catalogue & tri ──────────────────────────────────────────────────────────

def get_catalog_metadata(username: str, platform: str, period_days: int,
                          progress_cb=None) -> list:
    """
    Récupère les métadonnées (sans télécharger les vidéos) via --flat-playlist.
    Filtre ensuite par date en Python pour garantir la compatibilité yt-dlp/TikTok.
    """
    if platform == "TikTok":
        url = "https://www.tiktok.com/@" + username
    else:
        url = "https://www.instagram.com/" + username + "/"

    if progress_cb:
        progress_cb("🔍 Récupération du catalogue de @" + username + "...")

    # Calcul de la date limite
    if period_days > 0:
        date_limit = (date.today() - timedelta(days=period_days)).strftime("%Y%m%d")
    else:
        date_limit = None  # Toute la période

    cmd = (
        [YTDLP_BIN]
        + get_ytdlp_cookie_args()
        + [
            "--flat-playlist",
            "--playlist-end", "500",       # max raisonnable
            "--print",
            "%(id)s|%(title)s|%(url)s|%(view_count)s|%(like_count)s"
            "|%(comment_count)s|%(duration)s|%(upload_date)s"
            "|%(music_track)s|%(music_author)s|%(is_original_sound)s",
            "--no-warnings",
            url,
        ]
    )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            err = result.stderr.lower()
            if "private" in err or "login" in err:
                raise RuntimeError("Compte privé — impossible d'analyser.")
            if "not found" in err or "404" in err:
                raise RuntimeError("Compte @" + username + " introuvable.")
            logger.warning("yt-dlp stderr: " + result.stderr[-300:])

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            vid_date = parts[7] if len(parts) > 7 else ""

            # Filtre date en Python
            if date_limit and vid_date and len(vid_date) == 8:
                if vid_date < date_limit:
                    continue  # plus vieux que la période

            vid = {
                "id":             parts[0] if len(parts) > 0 else "",
                "titre":          parts[1] if len(parts) > 1 else "",
                "url":            parts[2] if len(parts) > 2 else "",
                "vues":           _safe_int(parts[3]) if len(parts) > 3 else None,
                "likes":          _safe_int(parts[4]) if len(parts) > 4 else None,
                "comments":       _safe_int(parts[5]) if len(parts) > 5 else None,
                "duree":          _safe_float(parts[6]) if len(parts) > 6 else None,
                "date":           vid_date,
                "music_track":    parts[8]  if len(parts) > 8  else "",
                "music_author":   parts[9]  if len(parts) > 9  else "",
                "is_original_sound": (parts[10].strip().lower() in ("true","1","yes"))
                                      if len(parts) > 10 else False,
            }
            # Pré-calcul score engagement
            vid["_eng"] = _engagement_score(vid)
            videos.append(vid)

        logger.info("Catalogue @" + username + ": " + str(len(videos)) + " vidéos")
        return videos

    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout récupération catalogue (180s). Réessaie.")
    except FileNotFoundError:
        raise RuntimeError("yt-dlp introuvable: " + YTDLP_BIN)


def sort_videos_by_mode(videos: list, mode: str, n: int) -> list:
    """
    Trie et sélectionne N vidéos selon le mode choisi.
    Les vidéos sans vues sont placées en fin de liste.
    """
    has_views = [v for v in videos if v.get("vues") is not None and (v.get("vues") or 0) > 0]
    no_views  = [v for v in videos if v not in has_views]

    if mode == "meilleures":
        sorted_v = sorted(has_views, key=lambda x: x.get("vues", 0), reverse=True)
        return (sorted_v + no_views)[:n]

    elif mode == "pires":
        sorted_v = sorted(has_views, key=lambda x: x.get("vues", 0))
        # Marquer pour annotation forcée
        for v in sorted_v:
            v["_mode_pires"] = True
        return (sorted_v + no_views)[:n]

    elif mode == "engagees":
        sorted_v = sorted(has_views, key=lambda x: x.get("_eng", 0), reverse=True)
        return (sorted_v + no_views)[:n]

    elif mode == "mixte":
        n_top = math.ceil(n / 2)
        n_bot = n // 2
        top = sorted(has_views, key=lambda x: x.get("vues", 0), reverse=True)[:n_top]
        top_ids = {v["id"] for v in top}
        bot_pool = [v for v in has_views if v["id"] not in top_ids]
        bot = sorted(bot_pool, key=lambda x: x.get("vues", 0))[:n_bot]
        for v in bot:
            v["_mode_pires"] = True
        return top + bot

    elif mode == "recentes":
        # Tri par date de publication (plus récentes d'abord) — ne dépend pas des stats
        def _parse_date(v):
            d = v.get("date", "") or ""
            return d if len(d) == 8 else "00000000"
        return sorted(videos, key=_parse_date, reverse=True)[:n]

    return videos[:n]


# ─── Rapport Claude ───────────────────────────────────────────────────────────

def generate_account_report(username: str, platform: str, analyses: list) -> tuple[dict, dict]:
    """Génère le rapport de compte via Claude Sonnet."""
    from modules.claude_mod import _call_claude

    data_str = json.dumps(analyses, ensure_ascii=False, indent=2)
    prompt = (
        "Tu analyses le compte @" + username + " sur " + platform
        + " pour Insolit (bons plans restaurants IDF).\n\n"
        "DONNÉES DES " + str(len(analyses)) + " VIDÉOS ANALYSÉES :\n"
        + data_str
        + """

Génère un rapport JSON complet (sans markdown) :

{
  "resume_compte": {
    "style_visuel_dominant": "description",
    "ton_editorial": "description",
    "frequence_publication": "estimation",
    "points_forts_compte": ["point1", "point2", "point3"],
    "points_faibles_compte": ["point1", "point2"]
  },
  "meilleures_videos": [
    {
      "titre": "titre ou description",
      "pourquoi_ca_marche": "explication précise",
      "elements_reproductibles": ["élément1", "élément2"]
    }
  ],
  "pires_videos": [
    {
      "titre": "titre ou description",
      "pourquoi_ca_pas_marche": "explication",
      "erreurs_a_eviter": ["erreur1"]
    }
  ],
  "patterns_gagnants": [
    {
      "pattern": "description du pattern",
      "frequence": "X sur Y vidéos",
      "impact_estime": "description"
    }
  ],
  "hooks_qui_marchent": [
    {
      "hook_complet": "description des 3-4 premières secondes combinant visuel + auditif + texte",
      "visuel_hook": "ce qu'on voit exactement",
      "auditif_hook": "ce qu'on entend exactement",
      "texte_ecran_hook": "texte exact affiché à l'écran (ou 'aucun')",
      "mecanique": "pourquoi ces 3-4s donnent envie de continuer",
      "score": 8,
      "ce_qui_manque": "ce qui pourrait rendre ce hook encore plus fort"
    }
  ],
  "opportunites_insolit": [
    "comment s'inspirer concrètement pour Insolit"
  ],
  "score_compte_global": 7,
  "verdict": "Analyse directe en 3 phrases sur ce compte et son utilité pour Insolit."
}"""
    )

    try:
        text, usage = _call_claude(prompt, max_tokens=7000)
        from modules.claude_mod import _parse_json_response
        parsed = _parse_json_response(text)
        if "_error" in parsed:
            logger.warning("Rapport JSON error: " + str(parsed.get("_error"))
                           + " | raw[:200]: " + text[:200])
        return parsed, usage
    except Exception as exc:
        logger.error("Erreur rapport compte: " + str(exc))
        return {"_error": str(exc)}, {}


def fetch_and_store_comments(url, video_id, ytdlp_cookie_args):
    """Récupère et stocke les top commentaires d'une vidéo."""
    import json as _json
    from modules.database import get_session, TopCommentaire
    from modules.claude_mod import _call_claude

    tmp_prefix = "/tmp/insolit_comments"
    tmp_info = tmp_prefix + ".info.json"

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
    except Exception as exc:
        logger.warning("fetch_and_store_comments subprocess error: " + str(exc))
        return None

    if not os.path.exists(tmp_info):
        return None

    try:
        with open(tmp_info, "r", encoding="utf-8") as fh:
            info = _json.load(fh)
    except Exception as exc:
        logger.warning("fetch_and_store_comments JSON parse error: " + str(exc))
        return None

    comments = info.get("comments", [])
    if not comments:
        return None

    top5 = comments[:5]
    sess = get_session()
    insight_str = None
    try:
        # Crée les objets et garde une référence directe (sess.new est vide après flush)
        tc_objects = []
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
            tc_objects.append(tc_obj)

        textes_joint = "\n".join(
            str(pos + 1) + ". " + str(c.get("text", ""))[:200]
            for pos, c in enumerate(top5)
        )
        prompt_c = (
            "Voici les 5 principaux commentaires de cette vidéo :\n"
            + textes_joint
            + "\n\nDonne un insight court (1-2 phrases) sur ce que ces commentaires révèlent "
            + "sur l'audience et pourquoi cette vidéo a engagé. Sois direct et actionnable."
        )
        try:
            insight_text, _ = _call_claude(prompt_c, max_tokens=200)
            insight_str = insight_text.strip()
            # Mise à jour directe via la référence Python (pas via sess.new qui est vide après flush)
            if tc_objects:
                tc_objects[0].insight_claude = insight_str
        except Exception as exc:
            logger.warning("Claude insight commentaires: " + str(exc))

        sess.commit()
    except Exception as exc:
        sess.rollback()
        logger.warning("fetch_and_store_comments DB error: " + str(exc))
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
    <p style="color:#555;margin-top:0.3rem;">Analyse intelligente — sélectionne les vidéos qui enrichissent vraiment ta base</p>
</div>
""", unsafe_allow_html=True)

# ─── Statut cookies TikTok ────────────────────────────────────────────────────
_cookie_status = get_cookies_status()
_ck_ok      = _cookie_status["status"] == "ok"
_ck_suspect = _cookie_status["status"] == "suspect"
_ck_missing = _cookie_status["status"] == "missing"

if _ck_ok:
    _ck_col, _ck_btn_col = st.columns([4, 1])
    with _ck_col:
        st.markdown(
            '<div style="background:#001a0a;border:1px solid #00C853;border-radius:8px;'
            'padding:0.5rem 1rem;font-size:0.85em;">'
            '✅ <strong style="color:#00C853;">Cookies TikTok configurés</strong>'
            ' — stats complètes activées'
            '<br><span style="color:#555;font-size:0.78em;">'
            + _cookie_status.get("source", "") + ' · ' + _cookie_status.get("details", "")
            + '</span></div>',
            unsafe_allow_html=True
        )
    with _ck_btn_col:
        if st.button("🔬 Tester", key="test_cookies_btn", use_container_width=True,
                     help="Vérifie les cookies en interrogeant une vidéo test"):
            with st.spinner("Test en cours (~15s)..."):
                _vr = validate_tiktok_cookies_live(get_ytdlp_cookie_args())
            if _vr["valid"]:
                st.success(_vr["message"])
            else:
                st.warning(_vr["message"])

elif _ck_suspect:
    st.markdown(
        '<div style="background:#1a0f00;border:1px solid #FF9800;border-radius:8px;'
        'padding:0.5rem 1rem;font-size:0.85em;margin-bottom:0.5rem;">'
        '⚠️ <strong style="color:#FF9800;">Cookies TikTok suspects</strong>'
        ' — les stats peuvent être incorrectes<br>'
        '<span style="color:#888;font-size:0.78em;">'
        + _cookie_status.get("details", "") + '</span></div>',
        unsafe_allow_html=True
    )
else:  # missing
    st.markdown(
        '<div style="background:#1a0000;border:1px solid #F44336;border-radius:8px;'
        'padding:0.5rem 1rem;font-size:0.85em;margin-bottom:0.5rem;">'
        '❌ <strong style="color:#F44336;">Cookies TikTok non configurés</strong>'
        ' — les vues/likes seront incorrects (ex: 345 au lieu de 2,2M)'
        '</div>',
        unsafe_allow_html=True
    )

# ── Section upload cookies (expander) ────────────────────────────────────────
with st.expander("🍪 Configurer les cookies TikTok" + (" ← requis pour stats exactes" if not _ck_ok else " (déjà configurés)"),
                 expanded=_ck_missing):
    st.markdown("""
**Pourquoi ?** TikTok retourne des stats fausses aux requêtes non authentifiées.
Avec tes cookies : les vraies vues, likes, et engagement.

**En 3 étapes :**

1. Installe l'extension Chrome [**Get cookies.txt LOCALLY**](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. Connecte-toi sur **[tiktok.com](https://tiktok.com)** avec ton compte
3. Clique sur l'extension → **Export As** → **cookies.txt** (format Netscape)
""")

    col_up, col_info = st.columns([2, 1])
    with col_up:
        uploaded_cookies = st.file_uploader(
            "📁 Uploader tiktok_cookies.txt (format Netscape)",
            type=["txt"],
            key="cookies_upload",
            help="Le fichier exporté par l'extension 'Get cookies.txt LOCALLY'"
        )
        if uploaded_cookies is not None:
            _content = uploaded_cookies.read().decode("utf-8", errors="replace")
            # Vérification minimale avant sauvegarde
            if "tiktok.com" not in _content and "sessionid" not in _content:
                st.error("❌ Ce fichier ne semble pas être des cookies TikTok valides.")
            else:
                try:
                    os.makedirs(VOLUME_PATH, exist_ok=True)
                    with open(COOKIES_FILE, "w") as _cf:
                        _cf.write(_content)
                    reset_cookie_cache()
                    st.success("✅ Cookies sauvegardés ! La page va se recharger...")
                    st.rerun()
                except Exception as _e:
                    st.error("Erreur sauvegarde: " + str(_e))

    with col_info:
        if _ck_ok or _ck_suspect:
            if st.button("🗑️ Supprimer les cookies", key="del_cookies",
                         use_container_width=True):
                try:
                    if os.path.exists(COOKIES_FILE):
                        os.remove(COOKIES_FILE)
                    reset_cookie_cache()
                    st.success("Cookies supprimés.")
                    st.rerun()
                except Exception as _e:
                    st.error(str(_e))

        st.markdown("""
<div style="font-size:0.78em;color:#666;margin-top:8px;">
⚠️ Le fichier cookies est confidentiel — il donne accès à ton compte TikTok.<br>
Il n'est jamais envoyé à personne et n'est pas pushé sur GitHub.
</div>""", unsafe_allow_html=True)

# ─── Section A — Input ────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])
with col1:
    compte_input = st.text_input(
        "@nomducompte ou URL du profil",
        placeholder="@my.bouffe ou https://www.tiktok.com/@strop.bon",
        key="compte_input"
    )
with col2:
    plateforme = st.radio("Plateforme", ["TikTok", "Instagram"], horizontal=True, key="plateforme")

col_tc, col_cat, col_com = st.columns(3)
with col_tc:
    type_compte = st.selectbox(
        "Type de compte",
        ["Concurrent", "Inspiration", "Secteur", "Mon compte"],
        key="type_compte"
    )
with col_cat:
    categorie = st.selectbox(
        "Catégorie",
        ["Restaurant", "Bar", "Café", "Expérience", "Bon plan",
         "Tendance food", "Lifestyle", "Voyage IDF", "Autre"],
        key="categorie_compte"
    )
with col_com:
    recuperer_commentaires = st.toggle(
        "💬 Récupérer commentaires (+30s/vidéo)",
        value=False, key="recup_comments"
    )

st.markdown("---")

# ─── Section B — Période ─────────────────────────────────────────────────────
st.markdown("**📅 Période à analyser**")
PERIODE_OPTIONS = {
    "30 derniers jours":  30,
    "6 derniers mois":   180,
    "12 derniers mois":  365,
    "Toute la période":    0,
}
periode_label = st.radio(
    "Période",
    list(PERIODE_OPTIONS.keys()),
    index=1,
    horizontal=True,
    key="periode_label",
    label_visibility="collapsed",
)
period_days = PERIODE_OPTIONS[periode_label]

# ─── Section C — Mode de sélection ───────────────────────────────────────────
st.markdown("**🎯 Je veux analyser...**")

MODES = {
    "meilleures": {
        "emoji": "🔥",
        "label": "LES MEILLEURES",
        "desc": "Top X par vues\n→ enrichit ce qui marche",
        "needs_stats": True,
    },
    "pires": {
        "emoji": "❌",
        "label": "LES PIRES",
        "desc": "Bottom X par vues\n→ enrichit ce qui marche pas",
        "needs_stats": True,
    },
    "engagees": {
        "emoji": "⚡",
        "label": "LES PLUS ENGAGÉES",
        "desc": "Top X par ratio\nlikes+saves/vues\n→ qualité réelle",
        "needs_stats": True,
    },
    "mixte": {
        "emoji": "🎯",
        "label": "SÉLECTION MIXTE",
        "desc": "X/2 meilleures\n+ X/2 pires\n→ contraste maximum",
        "needs_stats": True,
    },
    "recentes": {
        "emoji": "📅",
        "label": "LES PLUS RÉCENTES",
        "desc": "X dernières vidéos\npubliées\n→ sans besoin de stats",
        "needs_stats": False,
    },
}

# Mode dégradé sans cookies : forcer "recentes" et expliquer
if _ck_missing:
    st.markdown("""
    <div style="background:#1a0000;border:1px solid #F44336;border-radius:8px;
                padding:0.7rem 1rem;margin-bottom:0.8rem;font-size:0.85em;">
        ❌ <strong style="color:#F44336;">Modes verrouillés</strong> —
        les modes Meilleures / Pires / Engagées / Mixte nécessitent des stats exactes.
        <br>Configure les cookies ci-dessus pour les débloquer.
        <br>Seul le mode <strong>📅 Les plus récentes</strong> est disponible sans cookies.
    </div>
    """, unsafe_allow_html=True)
    st.session_state["selection_mode"] = "recentes"

# Initialiser le mode par défaut
if "selection_mode" not in st.session_state:
    st.session_state["selection_mode"] = "meilleures"

mode_cols = st.columns(5)
for i, (mode_key, mode_info) in enumerate(MODES.items()):
    with mode_cols[i]:
        needs_stats = mode_info.get("needs_stats", True)
        locked = _ck_missing and needs_stats
        selected = st.session_state["selection_mode"] == mode_key

        border_color = "#ff00a4" if selected else ("#444" if locked else "#333")
        bg_color     = "#1a0010" if selected else ("#0d0d0d" if locked else "#0a0a0a")
        label_color  = "#666" if locked else "#ddd"

        st.markdown(
            '<div style="background:' + bg_color + ';border:2px solid ' + border_color + ';'
            'border-radius:12px;padding:0.9rem;text-align:center;min-height:120px;'
            + ('opacity:0.45;' if locked else '') + '">'
            '<div style="font-size:1.4rem;">' + mode_info["emoji"] + ('🔒' if locked else '') + '</div>'
            '<div style="font-size:0.75rem;font-weight:700;color:' + label_color + ';margin-top:4px;">'
            + mode_info["label"] + '</div>'
            '<div style="font-size:0.68rem;color:#555;margin-top:4px;white-space:pre-line;">'
            + mode_info["desc"] + '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "✓ Sélectionné" if selected else ("🔒 Verrouillé" if locked else "Choisir"),
            key="mode_btn_" + mode_key,
            use_container_width=True,
            type="primary" if selected else "secondary",
            disabled=locked,
        ):
            st.session_state["selection_mode"] = mode_key
            if "compte_preview" in st.session_state:
                del st.session_state["compte_preview"]
            st.rerun()

selection_mode = st.session_state["selection_mode"]

# ─── Section D — Nombre de vidéos ────────────────────────────────────────────
st.markdown("")
if selection_mode == "mixte":
    nb_videos = st.slider(
        "Nombre total de vidéos (X/2 meilleures + X/2 pires)",
        min_value=4, max_value=50, value=10, step=2,
        key="nb_videos"
    )
    n_top = math.ceil(nb_videos / 2)
    n_bot = nb_videos // 2
    st.caption(str(n_top) + " meilleures + " + str(n_bot) + " pires = contraste maximum pour la base")
elif selection_mode == "recentes":
    nb_videos = st.slider(
        "Nombre de vidéos récentes à analyser",
        min_value=5, max_value=30, value=10, step=5,
        key="nb_videos"
    )
    st.caption("📅 Les " + str(nb_videos) + " vidéos les plus récentes — ne nécessite pas de stats exactes")
else:
    nb_videos = st.slider(
        "Nombre de vidéos à analyser",
        min_value=5, max_value=50, value=10, step=5,
        key="nb_videos"
    )

# ─── Section E — Prévisualisation ────────────────────────────────────────────
st.markdown("---")

preview_btn = st.button(
    "🔍 PRÉVISUALISER LA SÉLECTION",
    use_container_width=True,
    type="secondary",
    key="preview_btn"
)

if preview_btn:
    if not compte_input.strip():
        st.error("Entre un nom de compte ou une URL.")
        st.stop()

    username_p = _clean_username(compte_input)
    status_prev = st.empty()

    with st.spinner("Récupération du catalogue (sans téléchargement)..."):
        try:
            catalog = get_catalog_metadata(
                username_p, plateforme, period_days,
                progress_cb=lambda msg: status_prev.markdown("**" + msg + "**")
            )
        except RuntimeError as exc:
            st.error(str(exc))
            st.stop()

    if not catalog:
        st.warning(
            "Aucune vidéo trouvée sur la période sélectionnée pour @" + username_p
            + ". Essaie une période plus longue."
        )
        st.stop()

    # Tri selon le mode
    selected_vids = sort_videos_by_mode(catalog, selection_mode, nb_videos)
    catalog_size = len(catalog)

    # Sauvegarde preview
    st.session_state["compte_preview"] = {
        "videos":        selected_vids,
        "catalog_size":  catalog_size,
        "username":      username_p,
        "plateforme":    plateforme,
        "mode":          selection_mode,
        "nb":            nb_videos,
        "period_days":   period_days,
        "periode_label": periode_label,
    }
    status_prev.empty()

# ─── Affichage Preview ────────────────────────────────────────────────────────
if "compte_preview" in st.session_state:
    prev = st.session_state["compte_preview"]
    sel_vids = prev["videos"]
    catalog_size = prev["catalog_size"]
    uname_prev = prev["username"]
    mode_prev = prev["mode"]

    nb_sel = len(sel_vids)
    mode_label = MODES[mode_prev]["emoji"] + " " + MODES[mode_prev]["label"]

    if catalog_size < nb_videos:
        st.info(
            "Seulement **" + str(catalog_size) + " vidéos** disponibles sur la période — toutes seront analysées."
        )

    st.markdown(
        "📊 **" + str(catalog_size) + " vidéos** trouvées sur " + prev["periode_label"]
        + " | Mode : " + mode_label
        + " | **" + str(nb_sel) + " vidéos** seront analysées"
    )

    # Tableau de prévisualisation
    import pandas as pd

    def _fmt_date(d):
        if not d or len(d) != 8:
            return d or "—"
        return d[6:8] + "/" + d[4:6] + "/" + d[2:4]

    def _fmt_vues(v):
        if v is None:
            return "—"
        if v >= 1_000_000:
            return str(round(v / 1_000_000, 1)) + "M"
        if v >= 1_000:
            return str(round(v / 1_000, 1)) + "k"
        return str(v)

    rows = []
    for i, v in enumerate(sel_vids):
        eng_str = (str(round(v.get("_eng", 0), 1)) + "%") if v.get("vues") else "—"
        rows.append({
            "#":     i + 1,
            "Titre": (v.get("titre") or "—")[:55],
            "Date":  _fmt_date(v.get("date", "")),
            "Vues":  _fmt_vues(v.get("vues")),
            "Likes": _fmt_vues(v.get("likes")),
            "Eng.":  eng_str,
            "Durée": (str(int(v.get("duree", 0))) + "s") if v.get("duree") else "—",
        })

    df_prev = pd.DataFrame(rows).set_index("#")
    st.dataframe(df_prev, use_container_width=True, height=min(40 * nb_sel + 60, 500))

    # Coût estimé
    cout_estime = nb_sel * 0.030
    st.markdown(
        '<div style="background:#0a0a0a;border:1px solid #222;border-radius:8px;'
        'padding:0.7rem 1rem;margin:0.5rem 0;color:#888;font-size:0.85rem;">'
        '🧮 Ces <strong style="color:#ddd;">' + str(nb_sel) + ' vidéos</strong>'
        ' seront téléchargées et analysées (Vision + Whisper + Claude) — '
        'coût estimé : <strong style="color:#01f0fc;">~$' + str(round(cout_estime, 2)) + '</strong>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_mod, col_launch = st.columns(2)
    with col_mod:
        if st.button("✏️ Modifier la sélection", use_container_width=True, key="modify_btn"):
            del st.session_state["compte_preview"]
            st.rerun()
    with col_launch:
        launch_btn = st.button(
            "🚀 LANCER L'ANALYSE (" + str(nb_sel) + " vidéos)",
            use_container_width=True,
            type="primary",
            key="launch_btn",
        )

    # ─── Pipeline d'analyse ───────────────────────────────────────────────────
    if launch_btn:
        username = prev["username"]
        plateforme_p = prev["plateforme"]
        videos_list = sel_vids
        mode_analyse = prev["mode"]
        type_map = {"Mon compte": "mon_compte", "Concurrent": "concurrent",
                    "Inspiration": "inspiration", "Secteur": "secteur"}
        type_source = type_map.get(type_compte, "concurrent")

        nb_found = len(videos_list)

        st.markdown("---")
        st.markdown("### Analyse de **@" + username + "** | " + mode_label)

        progress_global = st.progress(0)
        status_global   = st.empty()

        from modules.analyzer import analyze_video, ANALYSIS_SEMAPHORE
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from modules.database import Stats, Video as _VideoModel, compute_engagement_ratios
        from datetime import datetime as _dt

        _JOURS = {
            "Monday": "lundi", "Tuesday": "mardi",
            "Wednesday": "mercredi", "Thursday": "jeudi",
            "Friday": "vendredi", "Saturday": "samedi",
            "Sunday": "dimanche"
        }

        analyses_results = []
        errors = []
        start_time = time.time()
        progress_container = st.empty()
        video_status = st.empty()

        # ── Fonction de travail par vidéo (s'exécute dans un thread) ─────────
        def _analyze_one(vid_item):
            """Analyse une vidéo + sauvegarde Stats/Video — thread-safe (session propre)."""
            url_v = vid_item.get("url", "")
            if not url_v:
                return {"error": "URL manquante", "vid": vid_item}

            meta = {
                "type_source": type_source,
                "nom_compte":  username,
                "categorie":   categorie,
                "partenaire":  "",
                "ville":       "",
            }
            use_quick = (mode_analyse == "pires") or vid_item.get("_mode_pires", False)

            # Sémaphore : max 3 analyses simultanées (rate-limits API)
            with ANALYSIS_SEMAPHORE:
                res = analyze_video(source=url_v, metadata=meta,
                                    is_url=True, quick_mode=use_quick)

            if not res.get("success"):
                return {"error": res.get("error", "Erreur inconnue"), "vid": vid_item}

            vid_id = res["video_id"]

            # ── DB : Stats + Video (jour, son) — session dédiée à ce thread ──
            sess_t = get_session()
            try:
                if vid_item.get("vues") or vid_item.get("likes"):
                    stats_t = Stats(
                        video_id=vid_id,
                        vues=vid_item.get("vues"),
                        likes=vid_item.get("likes"),
                        comments=vid_item.get("comments"),
                    )
                    stats_t.performance_tag = (
                        "mauvais" if vid_item.get("_mode_pires")
                        else _auto_tag(vid_item, mode_analyse)
                    )
                    compute_engagement_ratios(stats_t)
                    sess_t.add(stats_t)

                vo = sess_t.query(_VideoModel).filter_by(id=vid_id).first()
                if vo:
                    date_str = vid_item.get("date", "")
                    if date_str and len(date_str) == 8:
                        try:
                            d = _dt.strptime(date_str, "%Y%m%d")
                            vo.jour_publication = _JOURS.get(
                                d.strftime("%A"), d.strftime("%A").lower())
                        except Exception:
                            pass
                    mt = vid_item.get("music_track", "")
                    ma = vid_item.get("music_author", "")
                    if mt or ma:
                        vo.nom_son      = str(mt)[:500] if mt else ""
                        vo.auteur_son   = str(ma)[:200] if ma else ""
                        vo.son_original = bool(vid_item.get("is_original_sound", False))
                sess_t.commit()
            except Exception as exc_db:
                sess_t.rollback()
                logger.warning("DB thread: " + str(exc_db))
            finally:
                sess_t.close()

            # Commentaires (si option activée)
            if recuperer_commentaires:
                try:
                    fetch_and_store_comments(url_v, vid_id, get_ytdlp_cookie_args())
                except Exception as exc_c:
                    logger.warning("commentaires: " + str(exc_c))

            perf_tag = "mauvais" if vid_item.get("_mode_pires") else _auto_tag(vid_item, mode_analyse)
            return {
                "video_id":        vid_id,
                "titre":           res.get("titre"),
                "url":             url_v,
                "vues":            vid_item.get("vues"),
                "likes":           vid_item.get("likes"),
                "duree":           vid_item.get("duree"),
                "cout":            res.get("cout_total", 0),
                "elapsed":         res.get("elapsed", 0),
                "pegasus":         res.get("pegasus_data", {}),
                "whisper_texte":   res.get("whisper_data", {}).get("texte_complet", ""),
                "creative":        res.get("creative_data", {}),
                "nb_plans":        res.get("plans_count", 0),
                "score_potentiel": res.get("creative_data", {}).get("score_potentiel"),
                "hook_texte":      res.get("creative_data", {}).get("hook_texte"),
                "hook_score":      res.get("creative_data", {}).get("hook_score"),
                "mode":            mode_analyse,
                "perf_tag":        perf_tag,
                "vision_reelle":   res.get("creative_data", {}).get("_vision_reelle", False),
            }

        # ── Lancement 3 vidéos en parallèle (semaphore protège les APIs) ─────
        MAX_WORKERS = 3
        status_global.markdown(
            f"**⚡ Analyse de {nb_found} vidéos — {MAX_WORKERS} en parallèle...**"
        )

        completed_count = 0
        futures_map = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for vid in videos_list:
                f = executor.submit(_analyze_one, vid)
                futures_map[f] = vid

            for future in as_completed(futures_map):
                completed_count += 1
                pct = 5 + int((completed_count / nb_found) * 85)
                progress_global.progress(pct)

                elapsed_t = time.time() - start_time
                reste_t   = (elapsed_t / completed_count) * (nb_found - completed_count)
                reste_min = int(reste_t // 60)
                reste_sec = int(reste_t % 60)

                progress_container.markdown(
                    '<div class="card card-cyan">'
                    '<strong>⚡ ' + str(completed_count) + '/' + str(nb_found)
                    + ' vidéos terminées</strong>'
                    + (' · ' + str(nb_found - completed_count) + ' en cours' if nb_found - completed_count > 0 else '')
                    + '<br>'
                    '<div style="background:#111;border-radius:4px;height:6px;margin:8px 0;">'
                    '<div style="background:linear-gradient(90deg,#0000ff,#01f0fc,#ff00a4);'
                    'width:' + str(int((completed_count / nb_found) * 100)) + '%;height:6px;border-radius:4px;"></div>'
                    '</div>'
                    + ('Temps restant : ~' + str(reste_min) + 'min ' + str(reste_sec) + 's'
                       if reste_t > 0 else 'Finalisation...')
                    + '</div>',
                    unsafe_allow_html=True,
                )

                try:
                    res_item = future.result()
                except Exception as exc_f:
                    errors.append("Thread exception: " + str(exc_f))
                    logger.error("Thread exception", exc_info=True)
                    continue

                if "error" in res_item:
                    errors.append(res_item.get("vid", {}).get("titre", "?") + ": " + res_item["error"])
                else:
                    analyses_results.append(res_item)
                    titre_short = (res_item.get("titre") or "")[:50]
                    video_status.markdown("✅ " + titre_short + " — "
                                         + str(res_item.get("elapsed", 0)) + "s"
                                         + (" 👁 vision réelle" if res_item.get("vision_reelle") else ""))

        # Temps économisé (estimé séquentiel vs parallèle)
        elapsed_total_parallel = int(time.time() - start_time)
        avg_per_video = elapsed_total_parallel / max(len(analyses_results), 1)
        sequential_estimate = int(avg_per_video * nb_found)
        time_saved = max(0, sequential_estimate - elapsed_total_parallel)

        progress_global.progress(90)
        video_status.empty()

        total_cout = sum(r.get("cout", 0) for r in analyses_results)
        elapsed_total = int(time.time() - start_time)

        if not analyses_results:
            st.error("Aucune vidéo n'a pu être analysée.")
            if errors:
                with st.expander("Erreurs"):
                    for err in errors:
                        st.text(err)
            st.stop()

        # Rapport Claude
        status_global.markdown("**🧠 Génération du rapport (Claude)...**")
        analyses_for_claude = [
            {
                "titre":        r["titre"],
                "vues":         r["vues"],
                "likes":        r["likes"],
                "duree":        r["duree"],
                "nb_plans":     r["nb_plans"],
                "score_potentiel": r["score_potentiel"],
                "hook_texte":   r["hook_texte"],
                "hook_score":   r["hook_score"],
                "transcription": r["whisper_texte"][:300] if r["whisper_texte"] else "",
                "hook_analyse": r.get("pegasus", {}).get("hook_analyse", {}),
                "metriques":    r.get("pegasus", {}).get("metriques_globales", {}),
                "perf_tag":     r.get("perf_tag", ""),
            }
            for r in analyses_results
        ]

        rapport, claude_usage = generate_account_report(username, plateforme_p, analyses_for_claude)
        total_cout += claude_usage.get("cout_estime", 0)

        progress_global.progress(100)
        _saved_str = (f" | ⚡ ~{time_saved // 60}min {time_saved % 60}s économisés (parallèle ×{MAX_WORKERS})"
                      if time_saved > 10 else "")
        status_global.success(
            "✅ " + str(len(analyses_results)) + "/" + str(nb_found) + " vidéos analysées | "
            "Coût total : ~$" + str(round(total_cout, 3))
            + " | Durée : " + str(elapsed_total_parallel // 60) + "min " + str(elapsed_total_parallel % 60) + "s"
            + _saved_str
        )
        if errors:
            with st.expander("⚠️ " + str(len(errors)) + " erreurs"):
                for err in errors:
                    st.text(err)

        # Sauvegarde résultats + nettoyage preview
        st.session_state["last_compte_analysis"] = {
            "username":     username,
            "plateforme":   plateforme_p,
            "analyses":     analyses_results,
            "rapport":      rapport,
            "total_cout":   total_cout,
            "elapsed":      elapsed_total_parallel,
            "time_saved":   time_saved,
            "mode":         mode_analyse,
        }
        if "compte_preview" in st.session_state:
            del st.session_state["compte_preview"]


# ─── Section F — Résultats ────────────────────────────────────────────────────
if "last_compte_analysis" in st.session_state:
    data      = st.session_state["last_compte_analysis"]
    username  = data["username"]
    plateforme = data["plateforme"]
    rapport   = data.get("rapport", {})
    analyses  = data.get("analyses", [])
    resume    = rapport.get("resume_compte", {})
    mode_res  = data.get("mode", "meilleures")

    st.markdown("---")

    # Badge mode utilisé
    mode_info_r = MODES.get(mode_res, {})
    st.markdown(
        '<div style="display:inline-block;background:#1a0010;border:1px solid #ff00a4;'
        'border-radius:6px;padding:0.2rem 0.7rem;font-size:0.8rem;color:#ff00a4;margin-bottom:0.5rem;">'
        + (mode_info_r.get("emoji","") + " " + mode_info_r.get("label","")) + '</div>',
        unsafe_allow_html=True,
    )

    # ── BLOC 1 — Fiche compte ─────────────────────────────────────────────────
    score_raw = rapport.get("score_compte_global", None)
    try:
        score_val = float(score_raw)
        score_display = str(round(score_val, 1))
        score_bar = int(score_val * 10)
    except (TypeError, ValueError):
        score_display = "—"
        score_bar = 50

    pf   = resume.get("points_forts_compte", [])
    ppf  = resume.get("points_faibles_compte", [])
    opps = rapport.get("opportunites_insolit", [])

    if rapport.get("_error"):
        st.error("⚠️ Le rapport IA n'a pas pu être généré. Données brutes sauvegardées en base.")

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
        cols_top = st.columns(min(3, len(meilleures)))
        for i, v in enumerate(meilleures[:3]):
            with cols_top[i]:
                if i < len(analyses):
                    vid_id_t = analyses[i].get("video_id", "")
                    shot = os.path.join(SCREENSHOTS_PATH, str(vid_id_t), "plan_01.jpg")
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

    # ── BLOC 4 — Hooks ────────────────────────────────────────────────────────
    hooks = rapport.get("hooks_qui_marchent", [])
    if hooks:
        st.markdown("### 🎣 Top hooks du compte")
        for h in hooks[:5]:
            score_h = h.get("score", 0)
            score_color = "#00C853" if score_h >= 8 else "#FFD700" if score_h >= 6 else "#FF6B35"

            hook_complet  = h.get("hook_complet") or h.get("texte", "—")
            visuel        = h.get("visuel_hook", "")
            auditif       = h.get("auditif_hook", "")
            texte_ecran   = h.get("texte_ecran_hook", "")
            mecanique     = h.get("mecanique") or h.get("pourquoi", "")
            ce_qui_manque = h.get("ce_qui_manque", "")

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

    # ── BLOC Sons ─────────────────────────────────────────────────────────────
    from modules.database import get_session as _gs, Video as _VidM
    _sons_data = []
    _son_vid_ids = [_a.get("video_id") for _a in analyses if _a.get("video_id")]
    if _son_vid_ids:
        _s2 = _gs()
        try:
            _vos = _s2.query(_VidM).filter(_VidM.id.in_(_son_vid_ids)).all()
            for _vo in _vos:
                if _vo.nom_son:
                    _sons_data.append({
                        "son": _vo.nom_son,
                        "auteur": _vo.auteur_son or "",
                        "original": _vo.son_original,
                    })
        finally:
            _s2.close()

    if _sons_data:
        st.markdown("### 🎵 Sons des vidéos analysées")
        from collections import Counter as _Ctr
        sons_counter = _Ctr(_d["son"] for _d in _sons_data if _d.get("son"))
        nb_orig = sum(1 for _d in _sons_data if _d.get("original"))
        st.caption(
            str(len(_sons_data)) + " vidéos avec son · "
            + str(nb_orig) + " sons originaux ("
            + str(round(nb_orig / len(_sons_data) * 100)) + "%)"
        )
        for _son, _cnt in sons_counter.most_common(10):
            _auteur = next((_d["auteur"] for _d in _sons_data
                            if _d["son"] == _son and _d.get("auteur")), "")
            _label = _son + (" — " + _auteur if _auteur else "") + " ×" + str(_cnt)
            st.markdown("- " + _label)

    # ── BLOC 5 — Grille complète ──────────────────────────────────────────────
    if analyses:
        st.markdown("### 📊 Toutes les vidéos analysées")
        analyses_sorted = sorted(analyses, key=lambda x: x.get("vues") or 0, reverse=True)

        from modules.database import Transcription, Plan as PlanDB

        def _load_transcript(video_id):
            """Charge transcription + plans complets (tous les champs) depuis la DB."""
            if not video_id:
                return [], []
            sess = get_session()
            try:
                mots  = sess.query(Transcription).filter_by(video_id=video_id)\
                            .order_by(Transcription.timestamp).all()
                plans = sess.query(PlanDB).filter_by(video_id=video_id)\
                            .order_by(PlanDB.numero_plan).all()
                return (
                    [{"ts": m.timestamp, "mot": m.mot} for m in mots],
                    [{
                        "num":             p.numero_plan,
                        "debut":           p.timestamp_debut or 0,
                        "fin":             p.timestamp_fin or 0,
                        "type_plan":       p.type_plan or "",
                        "description":     p.description or "",
                        "texte":           p.texte_visible or "",
                        "role":            p.role_narratif or "",
                        "changement":      bool(p.changement_scene),
                        "personnes":       p.personnes or "",
                    } for p in plans],
                )
            finally:
                sess.close()

        def _render_transcript(mots, plans):
            """
            Formate la transcription mot-à-mot groupée par plan.
            Affiche : hook mis en avant, overlay text, changements de scène, personnes.
            """
            if not mots and not plans:
                return None

            SEP = "─" * 48
            lines = []

            if plans:
                for p in plans:
                    debut = p["debut"]
                    fin   = p["fin"]
                    num   = p["num"]
                    role  = p["role"]
                    desc  = p["description"]
                    texte = p["texte"]
                    ptype = p["type_plan"]
                    pers  = p["personnes"]

                    # Indicateur changement de scène
                    if p["changement"] and num > 1:
                        lines.append("")
                        lines.append("⬛ " + SEP)
                        lines.append("🔄 CHANGEMENT DE SCÈNE")
                        lines.append("⬛ " + SEP)

                    # En-tête du plan
                    role_emoji = {
                        "hook": "🎣 HOOK",
                        "contexte": "📍 CONTEXTE",
                        "preuve": "✅ PREUVE",
                        "ambiance": "🎬 AMBIANCE",
                        "cta": "📣 CTA",
                        "branding": "🏷 BRANDING",
                    }.get(role, "🎬 PLAN")

                    header = (
                        role_emoji + " " + str(num)
                        + " (" + str(round(debut, 1)) + "s → " + str(round(fin, 1)) + "s)"
                    )
                    if ptype:
                        header += " | " + ptype
                    lines.append(header)

                    # Description de la scène
                    if desc:
                        lines.append("  👁  " + desc)
                    if pers and pers not in ("", "na", "None"):
                        lines.append("  👤  " + pers)

                    # Overlay / texte à l'écran — mis en avant
                    if texte:
                        lines.append("  📝  OVERLAY : « " + texte + " »")

                    # Mots prononcés dans ce plan
                    mots_plan = [m["mot"] for m in mots if debut <= m["ts"] <= fin]
                    if mots_plan:
                        lines.append('  🗣  "' + " ".join(mots_plan) + '"')
                    elif not texte and not desc:
                        lines.append("  (plan silencieux / pas de texte)")

                    lines.append("")
            else:
                # Fallback : pas de plans — mot-à-mot brut
                if not mots:
                    return None
                lines.append("🗣 TRANSCRIPTION MOT-À-MOT")
                lines.append(SEP)
                chunk = []
                for m in mots:
                    chunk.append("[" + str(round(m["ts"], 1)) + "s] " + m["mot"])
                    if len(chunk) >= 8:
                        lines.append("  " + "  ".join(chunk))
                        chunk = []
                if chunk:
                    lines.append("  " + "  ".join(chunk))

            return "\n".join(lines) if lines else None

        # Pre-check transcriptions disponibles
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

        TAG_COLORS = {"viral": "#ff00a4", "bon": "#00C853", "moyen": "#FFD700", "mauvais": "#FF6B35"}

        cols_grid = st.columns(3)
        for idx, a in enumerate(analyses_sorted):
            col = cols_grid[idx % 3]
            with col:
                vid_id = a.get("video_id", "")
                shot = os.path.join(SCREENSHOTS_PATH, str(vid_id), "plan_01.jpg")
                if os.path.exists(shot):
                    st.image(shot, use_container_width=True)
                else:
                    st.markdown(
                        '<div style="background:#111;height:100px;border-radius:8px;'
                        'display:flex;align-items:center;justify-content:center;'
                        'color:#333;font-size:1.5rem;">🎬</div>',
                        unsafe_allow_html=True,
                    )

                vues     = a.get("vues")
                vues_str = "{:,}".format(vues) if vues else "—"
                score_v  = a.get("score_potentiel", "—")
                titre_v  = str(a.get("titre") or "—")
                hook_txt = str(a.get("hook_texte") or "")
                perf_tag = a.get("perf_tag", "")
                tag_color = TAG_COLORS.get(perf_tag, "#555")
                tag_html = (
                    '<span style="background:' + tag_color + '22;color:' + tag_color + ';'
                    'font-size:0.7rem;padding:1px 6px;border-radius:4px;border:1px solid '
                    + tag_color + ';">' + (perf_tag or "—") + '</span>'
                ) if perf_tag else ""

                st.markdown(
                    '<div style="padding:0.4rem 0;">'
                    '<div style="font-size:0.85rem;font-weight:600;">' + _e(titre_v[:45]) + '</div>'
                    '<div style="color:#888;font-size:0.78rem;margin-top:2px;">'
                    '👁 ' + vues_str + ' · Score ' + str(score_v) + '/10 ' + tag_html + '</div>'
                    '<div style="color:#555;font-size:0.78rem;font-style:italic;">'
                    + _e(hook_txt[:50]) + '</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

                if vid_id in _vids_with_transcript:
                    with st.expander("▶ Voir le script transcrit"):
                        mots_db, plans_db = _load_transcript(vid_id)
                        script_txt = _render_transcript(mots_db, plans_db)
                        if script_txt:
                            st.text(script_txt)
                            st.button(
                                "📋 Copier",
                                key="copy_script_" + str(vid_id) + "_" + str(idx),
                                on_click=lambda t=script_txt: st.session_state.update(
                                    {"_copied_script": t}
                                ),
                            )
                            if st.session_state.get("_copied_script") == script_txt:
                                st.code(script_txt, language="")
                        else:
                            st.caption("Script structuré non disponible.")
                else:
                    st.caption("🔇 Whisper non disponible — configurez OPENAI_API_KEY sur Railway.")

    # ── BLOC 6 — Comparaison ──────────────────────────────────────────────────
    all_my_videos = get_all_videos_with_stats()
    my_annotated  = [v for v in all_my_videos if v.get("performance_tag") in ["viral", "bon"]]

    if len(my_annotated) >= 5 and analyses:
        st.markdown("### ⚡ Ce compte vs tes meilleures vidéos")

        def _avg(lst, key):
            vals = [v.get(key) for v in lst if v.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else "—"

        import pandas as pd
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
        df_cmp = pd.DataFrame({
            "Variable": list(compte_data.keys()),
            "@" + username: list(compte_data.values()),
            "Tes meilleures": list(mes_data.values()),
        })
        st.dataframe(df_cmp.set_index("Variable"), use_container_width=True)

    # ── Boutons d'action ──────────────────────────────────────────────────────
    st.markdown("---")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.button("💾 Tout dans la bibliothèque ✓", disabled=True,
                  use_container_width=True, key="lib_btn")

    with col_b:
        if st.button("🎯 Générer brief inspiré de ce compte",
                     use_container_width=True, key="brief_btn"):
            st.session_state["brief_from_compte"] = username
            st.switch_page("pages/4_Generer.py")

    with col_c:
        if rapport and not rapport.get("_error"):
            rapport_txt = "RAPPORT COMPTE @" + username + " — " + plateforme + "\n" + "="*50 + "\n\n"
            rapport_txt += "Score global : " + str(rapport.get("score_compte_global")) + "/10\n"
            rapport_txt += "Mode analyse : " + mode_res + "\n"
            rapport_txt += "Verdict : " + str(rapport.get("verdict","")) + "\n\n"
            rapport_txt += "Style : " + str(resume.get("style_visuel_dominant","")) + "\n"
            rapport_txt += "Ton : " + str(resume.get("ton_editorial","")) + "\n\n"
            rapport_txt += "PATTERNS GAGNANTS :\n"
            for p in patterns[:5]:
                rapport_txt += "  • " + str(p.get("pattern")) + " (" + str(p.get("frequence")) + ")\n"
            rapport_txt += "\nOPPORTUNITÉS INSOLIT :\n"
            for o in opps:
                rapport_txt += "  • " + str(o) + "\n"
            st.download_button(
                "📄 Exporter le rapport",
                data=rapport_txt,
                file_name="rapport_" + username + ".txt",
                mime="text/plain",
                use_container_width=True,
                key="export_btn",
            )

    nb_ann, niveau = get_precision_level()
    st.markdown(
        '<div style="text-align:center;padding:1rem;color:#444;font-size:0.85rem;">'
        + str(len(analyses)) + " vidéos analysées · "
        "Coût total : ~$" + str(round(data.get("total_cout", 0), 3)) + " · "
        "Durée : " + str(data.get("elapsed", 0) // 60) + "min "
        + str(data.get("elapsed", 0) % 60) + "s · "
        "Base : " + str(nb_ann) + " annotées"
        '</div>',
        unsafe_allow_html=True,
    )
