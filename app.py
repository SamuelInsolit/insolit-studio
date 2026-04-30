import os
import sys
import logging
from dotenv import load_dotenv

# Diagnostic startup log — flush immédiat pour Railway
print("[STARTUP] app.py chargé, Python OK", flush=True)
sys.stdout.flush()

load_dotenv()

import streamlit as st
from modules.styles import apply_styles
from modules.enrichment import get_precision_badge

# ─── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Insolit Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(),
    ]
)

# ─── Init DB ──────────────────────────────────────────────────────────────────
from modules.database import (
    get_session, Video, Stats, AnalyseCreative, AnalysePegasus, init_db,
    get_precision_level,
)

try:
    init_db()
except Exception as e:
    st.error(f"Erreur initialisation base de données : {e}")

# ─── Styles ───────────────────────────────────────────────────────────────────
apply_styles()

# Extra CSS for dashboard-specific elements
st.markdown("""
<style>
.kpi-card {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 14px;
    padding: 1.4rem 1.2rem;
    text-align: center;
    height: 100%;
}
.kpi-value {
    font-size: 2.2rem;
    font-weight: 900;
    color: #ff00a4;
    line-height: 1.1;
    margin: 0.3rem 0;
}
.kpi-label {
    font-size: 0.75rem;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 0.2rem;
}
.kpi-sub {
    font-size: 0.8rem;
    color: #888;
    margin-top: 0.3rem;
}
.kpi-icon { font-size: 1.6rem; margin-bottom: 0.3rem; }

.video-card {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.video-thumb {
    width: 56px;
    height: 56px;
    border-radius: 8px;
    object-fit: cover;
    flex-shrink: 0;
    background: #111;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.6rem;
}
.video-title {
    font-weight: 600;
    font-size: 0.9rem;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.video-meta { font-size: 0.78rem; color: #666; margin-top: 2px; }

.banner-warning {
    background: linear-gradient(135deg, #2a1500, #1a0a00);
    border: 1px solid #ff6600;
    border-left: 4px solid #ff6600;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: #ffaa44;
    font-weight: 600;
}
.banner-info {
    background: linear-gradient(135deg, #001a2a, #000f1a);
    border: 1px solid #01f0fc;
    border-left: 4px solid #01f0fc;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: #01f0fc;
    font-weight: 600;
}
.banner-success {
    background: linear-gradient(135deg, #001a0a, #000f05);
    border: 1px solid #00cc66;
    border-left: 4px solid #00cc66;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: #00cc66;
    font-weight: 600;
}
.shortcut-card {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s;
}
.shortcut-card:hover { border-color: #ff00a4; }
.section-title {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: #555;
    margin: 1.8rem 0 0.8rem 0;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:1.2rem 0 1.5rem 0;">
        <div class="logo-text">◎ Insolit Studio</div>
        <div class="logo-sub">Analyse · Stratégie · Brief</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    try:
        nb_annotees, niveau = get_precision_level()
        st.markdown(get_precision_badge(nb_annotees, niveau), unsafe_allow_html=True)
    except Exception:
        st.caption("Base de données non initialisée")

    st.divider()
    try:
        from modules.database import get_costs_summary
        _costs = get_costs_summary()
        _month = _costs.get("total_month", 0)
        _today = _costs.get("total_today", 0)
        _proj  = _costs.get("projection_month", 0)
        _color = "#F44336" if _month > 20 else ("#FF9800" if _month > 10 else "#00C853")
        st.markdown(
            f'<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:2px;margin-bottom:4px;">Coûts API</div>'
            f'<div style="background:#0a0a0a;border:1px solid {_color};border-radius:8px;padding:0.5rem 0.8rem;font-size:0.82em;">'
            f'<span style="color:{_color};font-weight:700;">💰 ${_month:.3f}</span>'
            f'<span style="color:#555;font-size:0.75em;"> ce mois</span><br>'
            f'<span style="color:#666;font-size:0.75em;">Aujourd\'hui : ${_today:.4f} · Projection : ${_proj:.2f}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
        if _month > 10:
            st.warning(f"⚠️ Budget API : ${_month:.2f}/mois", icon="💸")
    except Exception:
        pass

    st.divider()

    st.markdown('<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:2px;margin-bottom:4px;">Principal</div>', unsafe_allow_html=True)
    st.page_link("pages/1_Analyser.py",            label="🎬 Analyseur")
    st.page_link("pages/2_Bibliotheque.py",         label="📚 Bibliothèque")
    st.page_link("pages/3_Patterns.py",             label="📊 Motifs")
    st.page_link("pages/4_Generer.py",              label="⚡ Générer")
    st.page_link("pages/6_Base_Connaissances.py",   label="📖 Base de connaissances")

    st.divider()
    st.markdown('<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:2px;margin-bottom:4px;">Avancé</div>', unsafe_allow_html=True)
    st.page_link("pages/5_Compte.py",               label="🔍 Analyser un compte")
    st.page_link("pages/7_Enrichir.py",             label="⚡ Enrichir")

    st.divider()
    st.caption("Claude Vision · Whisper · ffmpeg")

# ─── Data loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_dashboard_data():
    """Load all KPI data in a single DB pass."""
    session = get_session()
    try:
        # Total videos analysed (any status — count all known)
        total_videos = session.query(Video).count()

        # Annotated = Stats.performance_tag is not null
        total_annotees = (
            session.query(Stats)
            .filter(Stats.performance_tag.isnot(None))
            .count()
        )
        pct_annotees = round(total_annotees / total_videos * 100) if total_videos else 0

        # Durée optimale — average duration of viral/bon videos
        good_videos = (
            session.query(Video)
            .join(Stats, Stats.video_id == Video.id)
            .filter(Stats.performance_tag.in_(["viral", "bon"]))
            .filter(Video.duree_secondes.isnot(None))
            .all()
        )
        duree_opt = None
        if good_videos:
            duree_opt = sum(v.duree_secondes for v in good_videos) / len(good_videos)

        # Hook type gagnant — most common hook_type among viral/bon
        hook_rows = (
            session.query(AnalyseCreative.hook_type)
            .join(Video, AnalyseCreative.video_id == Video.id)
            .join(Stats, Stats.video_id == Video.id)
            .filter(Stats.performance_tag.in_(["viral", "bon"]))
            .filter(AnalyseCreative.hook_type.isnot(None))
            .all()
        )
        hook_winner = None
        if hook_rows:
            from collections import Counter
            counts = Counter(r[0] for r in hook_rows if r[0])
            if counts:
                hook_winner = counts.most_common(1)[0][0]

        # 5 dernières vidéos analysées (toutes statuts)
        recent_videos = (
            session.query(Video)
            .order_by(Video.created_at.desc())
            .limit(5)
            .all()
        )

        recent = []
        for v in recent_videos:
            score = None
            perf_tag = None
            if v.analyse_creative:
                score = v.analyse_creative.score_potentiel
            if v.stats:
                perf_tag = v.stats.performance_tag
            recent.append({
                "id":        v.id,
                "titre":     v.titre or f"Vidéo #{v.id}",
                "score":     score,
                "perf_tag":  perf_tag,
                "created_at": v.created_at,
            })

        return {
            "total_videos":   total_videos,
            "total_annotees": total_annotees,
            "pct_annotees":   pct_annotees,
            "duree_opt":      duree_opt,
            "hook_winner":    hook_winner,
            "recent":         recent,
        }
    finally:
        session.close()


try:
    data = load_dashboard_data()
except Exception as ex:
    data = None
    st.error(f"Impossible de charger les données : {ex}")

# ─── Header ───────────────────────────────────────────────────────────────────
if data and data["total_videos"] == 0:
    st.markdown("""
    <div style="text-align:center; padding:4rem 0 2rem 0;">
        <div style="font-size:3.5rem; margin-bottom:0.5rem;">👋</div>
        <h1 style="color:#ff00a4; font-weight:900; font-size:2.5rem; margin:0;">
            Bienvenue sur Insolit Studio
        </h1>
        <p style="color:#888; font-size:1.1rem; margin-top:0.6rem;">
            Commence par analyser ta première vidéo pour voir tes KPIs ici.
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <h1 style="color:#ff00a4; font-weight:900; margin-bottom:0.2rem;">
        ◎ Dashboard
    </h1>
    <p style="color:#555; font-size:0.85rem; margin-top:0; letter-spacing:1px;">
        VUE D'ENSEMBLE · INSOLIT STUDIO
    </p>
    """, unsafe_allow_html=True)

if data and data["total_videos"] < 3:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d0d1a,#0a0a0a);border:1px solid #2a2a4a;
                border-left:4px solid #ff00a4;border-radius:14px;padding:1.4rem 1.6rem;margin-bottom:1.5rem;">
        <div style="font-size:1.1rem;font-weight:900;color:#ff00a4;margin-bottom:0.8rem;">
            👋 Par où commencer ?
        </div>
        <div style="color:#aaa;font-size:0.88rem;margin-bottom:1rem;">3 étapes pour démarrer :</div>
        <div style="display:flex;flex-direction:column;gap:0.7rem;">
            <div style="display:flex;align-items:flex-start;gap:12px;">
                <div style="background:#ff00a4;color:#000;border-radius:50%;width:24px;height:24px;
                            display:flex;align-items:center;justify-content:center;font-weight:900;
                            font-size:0.75rem;flex-shrink:0;">1</div>
                <div>
                    <div style="color:#fff;font-weight:700;">🎬 Analyse ta première vidéo</div>
                    <div style="color:#555;font-size:0.82rem;">→ page Analyseur</div>
                </div>
            </div>
            <div style="display:flex;align-items:flex-start;gap:12px;">
                <div style="background:#01f0fc;color:#000;border-radius:50%;width:24px;height:24px;
                            display:flex;align-items:center;justify-content:center;font-weight:900;
                            font-size:0.75rem;flex-shrink:0;">2</div>
                <div>
                    <div style="color:#fff;font-weight:700;">⚡ Note sa performance</div>
                    <div style="color:#555;font-size:0.82rem;">→ page Enrichir (45 secondes)</div>
                </div>
            </div>
            <div style="display:flex;align-items:flex-start;gap:12px;">
                <div style="background:#00cc66;color:#000;border-radius:50%;width:24px;height:24px;
                            display:flex;align-items:center;justify-content:center;font-weight:900;
                            font-size:0.75rem;flex-shrink:0;">3</div>
                <div>
                    <div style="color:#fff;font-weight:700;">🔁 Répète sur 10 vidéos</div>
                    <div style="color:#555;font-size:0.82rem;">→ les patterns se débloquent automatiquement</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

if data:
    # ─── ROW 1 — KPI Cards ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Performance</div>', unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-icon">🎬</div>
            <div class="kpi-label">Vidéos analysées</div>
            <div class="kpi-value">{data["total_videos"]}</div>
            <div class="kpi-sub">dans la base</div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        pct = data["pct_annotees"]
        nb  = data["total_annotees"]
        color = "#ff00a4" if pct < 30 else "#01f0fc" if pct < 70 else "#00cc66"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-icon">🏷️</div>
            <div class="kpi-label">Annotées avec stats</div>
            <div class="kpi-value" style="color:{color};">{pct}%</div>
            <div class="kpi-sub">{nb} vidéo{"s" if nb != 1 else ""} taguée{"s" if nb != 1 else ""}</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        if data["duree_opt"] is not None:
            d = data["duree_opt"]
            mins = int(d // 60)
            secs = int(d % 60)
            duree_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
            duree_sub = "moyenne viral + bon"
        else:
            duree_str = "—"
            duree_sub = "annote des vidéos pour calculer"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-icon">⏱️</div>
            <div class="kpi-label">Durée optimale</div>
            <div class="kpi-value" style="color:#01f0fc;">{duree_str}</div>
            <div class="kpi-sub">{duree_sub}</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        hook = data["hook_winner"] or "—"
        hook_sub = "hook dominant viral/bon" if data["hook_winner"] else "pas encore assez de données"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-icon">🎣</div>
            <div class="kpi-label">Hook type gagnant</div>
            <div class="kpi-value" style="font-size:1.3rem; color:#ff00a4;">{hook}</div>
            <div class="kpi-sub">{hook_sub}</div>
        </div>
        """, unsafe_allow_html=True)

    # ─── ROW 2 — Activité récente ─────────────────────────────────────────────
    st.markdown('<div class="section-title">Activité récente</div>', unsafe_allow_html=True)

    BADGE = {
        "viral":   ('<span class="badge-viral">🔥 VIRAL</span>', "#ff00a4"),
        "bon":     ('<span class="badge-bon">✅ BON</span>',     "#01f0fc"),
        "moyen":   ('<span class="badge-moyen">😐 MOYEN</span>', "#0000ff"),
        "mauvais": ('<span class="badge-mauvais">❌ MAUVAIS</span>', "#333"),
    }

    if not data["recent"]:
        st.markdown("""
        <div style="text-align:center; padding:2rem; color:#444; border:1px dashed #222;
             border-radius:12px;">
            Aucune vidéo analysée pour l'instant
        </div>
        """, unsafe_allow_html=True)
    else:
        for vid in data["recent"]:
            vid_id = vid["id"]

            # Thumbnail path
            thumb_path = os.path.join("screenshots", str(vid_id), "plan_01.jpg")
            has_thumb  = os.path.exists(thumb_path)

            import html as _html
            _titre_raw = vid["titre"] or ""
            titre_display = _html.escape((_titre_raw[:40] + "…") if len(_titre_raw) > 40 else _titre_raw)

            badge_html = ""
            if vid["perf_tag"] and vid["perf_tag"] in BADGE:
                badge_html, _ = BADGE[vid["perf_tag"]]

            score_html = ""
            if vid["score"] is not None:
                score_html = f'<span style="color:#ff00a4; font-weight:700;">{vid["score"]:.0f}/10</span>'

            date_str = vid["created_at"].strftime("%d/%m/%Y") if vid["created_at"] else ""

            # Layout: thumb | info | button
            col_thumb, col_info, col_btn = st.columns([1, 6, 2])

            with col_thumb:
                if has_thumb:
                    st.image(thumb_path, width=60)
                else:
                    st.markdown(
                        '<div style="width:56px;height:56px;background:#111;border-radius:8px;'
                        'display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🎬</div>',
                        unsafe_allow_html=True
                    )

            with col_info:
                st.markdown(f"""
                <div style="padding:4px 0;">
                    <div class="video-title">{titre_display}</div>
                    <div class="video-meta">
                        {score_html}{"&nbsp;&nbsp;" if score_html else ""}{badge_html}
                        {"&nbsp;&nbsp;" if badge_html else ""}
                        <span style="color:#444;">{date_str}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_btn:
                if st.button("Voir →", key=f"voir_{vid_id}", use_container_width=True):
                    st.session_state["selected_video_id"] = vid_id
                    st.switch_page("pages/1_Analyser.py")

            st.markdown('<hr style="margin:0.3rem 0; border-color:#111;">', unsafe_allow_html=True)

    # ─── ROW 3 — Alerte apprentissage ─────────────────────────────────────────
    st.markdown('<div class="section-title">Apprentissage</div>', unsafe_allow_html=True)

    nb = data["total_annotees"]
    if nb < 10:
        remaining = 10 - nb
        st.markdown(f"""
        <div class="banner-warning">
            ⚠️ Ta base apprend encore — annote <strong>{remaining} vidéo{"s" if remaining != 1 else ""}</strong>
            de plus pour des briefs précis
        </div>
        """, unsafe_allow_html=True)
    elif nb < 30:
        st.markdown(f"""
        <div class="banner-info">
            📈 Base en construction — <strong>{nb} patterns détectés</strong>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="banner-success">
            ✅ Base solide — tes briefs sont maintenant basés sur <strong>{nb} patterns réels</strong>
        </div>
        """, unsafe_allow_html=True)

    # ─── ROW 3b — Coûts API ───────────────────────────────────────────────────
    try:
        from modules.database import get_costs_summary
        _cs = get_costs_summary()
        if _cs["total_month"] > 0:
            st.markdown('<div class="section-title">Coûts API Claude</div>', unsafe_allow_html=True)
            _c1, _c2, _c3, _c4 = st.columns(4)
            with _c1:
                st.markdown(f"""<div class="kpi-card">
                    <div class="kpi-icon">💰</div>
                    <div class="kpi-label">Ce mois</div>
                    <div class="kpi-value" style="font-size:1.8rem;">${_cs['total_month']:.3f}</div>
                    <div class="kpi-sub">projection : ${_cs['projection_month']:.2f}</div>
                </div>""", unsafe_allow_html=True)
            with _c2:
                _nb = _cs.get("nb_analyses_month", 0)
                _avg = round(_cs["total_month"] / _nb, 4) if _nb > 0 else 0
                st.markdown(f"""<div class="kpi-card">
                    <div class="kpi-icon">🎬</div>
                    <div class="kpi-label">Analyses Vision</div>
                    <div class="kpi-value" style="font-size:1.8rem;">{_nb}</div>
                    <div class="kpi-sub">~${_avg:.4f} / analyse</div>
                </div>""", unsafe_allow_html=True)
            with _c3:
                _briefs = _cs.get("by_operation", {}).get("brief_generation", {})
                st.markdown(f"""<div class="kpi-card">
                    <div class="kpi-icon">⚡</div>
                    <div class="kpi-label">Briefs générés</div>
                    <div class="kpi-value" style="font-size:1.8rem;">{_briefs.get('nb', 0)}</div>
                    <div class="kpi-sub">${_briefs.get('cout', 0):.3f} total</div>
                </div>""", unsafe_allow_html=True)
            with _c4:
                _today = _cs.get("total_today", 0)
                _color = "#F44336" if _today > 2 else ("#FF9800" if _today > 1 else "#01f0fc")
                st.markdown(f"""<div class="kpi-card">
                    <div class="kpi-icon">📅</div>
                    <div class="kpi-label">Aujourd'hui</div>
                    <div class="kpi-value" style="font-size:1.8rem;color:{_color};">${_today:.4f}</div>
                    <div class="kpi-sub">budget seuil : $2/jour</div>
                </div>""", unsafe_allow_html=True)
    except Exception:
        pass

    # ─── ROW 4 — Raccourcis rapides ───────────────────────────────────────────
    st.markdown('<div class="section-title">Raccourcis</div>', unsafe_allow_html=True)

    rc1, rc2, rc3 = st.columns(3)

    with rc1:
        st.markdown("""
        <div class="shortcut-card">
            <div style="font-size:2rem; margin-bottom:0.4rem;">🎬</div>
            <div style="font-weight:700; font-size:0.95rem;">Analyser une vidéo</div>
            <div style="color:#555; font-size:0.8rem; margin-top:0.3rem;">TwelveLabs + Claude</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Analyser →", key="btn_analyser", use_container_width=True):
            st.switch_page("pages/1_Analyser.py")

    with rc2:
        st.markdown("""
        <div class="shortcut-card">
            <div style="font-size:2rem; margin-bottom:0.4rem;">📚</div>
            <div style="font-weight:700; font-size:0.95rem;">Ajouter à la base</div>
            <div style="color:#555; font-size:0.8rem; margin-top:0.3rem;">Enrichir les connaissances</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ajouter →", key="btn_base", use_container_width=True):
            st.switch_page("pages/6_Base_Connaissances.py")

    with rc3:
        st.markdown("""
        <div class="shortcut-card">
            <div style="font-size:2rem; margin-bottom:0.4rem;">⚡</div>
            <div style="font-weight:700; font-size:0.95rem;">Générer un brief</div>
            <div style="color:#555; font-size:0.8rem; margin-top:0.3rem;">Data-driven content</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Générer →", key="btn_brief", use_container_width=True):
            st.switch_page("pages/4_Generer.py")
