import logging
from datetime import datetime
from modules.database import get_session, Stats, get_precision_level

logger = logging.getLogger(__name__)

PERFORMANCE_OPTIONS = {
    "🔥 Viral +500k": "viral",
    "✅ Bon 50-500k": "bon",
    "😐 Moyen 10-50k": "moyen",
    "❌ Mauvais -10k": "mauvais",
}

PERFORMANCE_COLORS = {
    "viral": "#ff00a4",
    "bon": "#01f0fc",
    "moyen": "#0000ff",
    "mauvais": "#333333",
}

PERFORMANCE_LABELS = {
    "viral": "🔥 VIRAL",
    "bon": "✅ BON",
    "moyen": "😐 MOYEN",
    "mauvais": "❌ MAUVAIS",
}


def save_enrichment(
    video_id: int,
    performance_tag: str,
    vues: int = None,
    completion_rate: float = None,
    note_humaine: str = None,
) -> bool:
    """Sauvegarde l'enrichissement d'une vidéo."""
    session = get_session()
    try:
        stats = session.query(Stats).filter_by(video_id=video_id).first()
        if not stats:
            stats = Stats(video_id=video_id)
            session.add(stats)

        stats.performance_tag = performance_tag
        if vues is not None:
            stats.vues = vues
        if completion_rate is not None:
            stats.completion_rate = completion_rate
        if note_humaine:
            stats.note_humaine = note_humaine
        stats.annotee_le = datetime.utcnow()
        from modules.database import compute_engagement_ratios
        compute_engagement_ratios(stats)

        session.commit()
        logger.info(f"Enrichissement sauvegardé: video_id={video_id}, tag={performance_tag}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Erreur enrichissement: {e}")
        return False
    finally:
        session.close()


def get_precision_badge(nb_annotees: int, niveau: str) -> str:
    """Retourne un badge HTML de précision."""
    colors = {
        "FAIBLE": "#0000ff",
        "BONNE": "#01f0fc",
        "EXCELLENTE": "#ff00a4",
    }
    text_colors = {"FAIBLE": "#fff", "BONNE": "#000", "EXCELLENTE": "#fff"}
    color = colors.get(niveau, "#333")
    tc = text_colors.get(niveau, "#fff")
    return f"""<span style='background:{color};color:{tc};padding:3px 10px;border-radius:12px;font-size:0.75em;font-weight:bold;'>
    {nb_annotees} annotées · Précision {niveau}</span>"""


def render_enrichment_form(video_id: int, existing_stats: dict = None):
    """
    Affiche le formulaire d'enrichissement rapide (< 45s).
    Doit être appelé dans un contexte Streamlit.
    Retourne True si sauvegardé.
    """
    import streamlit as st

    st.markdown("#### ⚡ Enrichissement rapide")
    st.caption("Enrichissez cette vidéo en moins de 45 secondes")

    col1, col2 = st.columns([1, 1])

    with col1:
        perf_label = st.radio(
            "Performance",
            options=list(PERFORMANCE_OPTIONS.keys()),
            index=0 if not existing_stats else _get_perf_index(existing_stats.get("performance_tag")),
            horizontal=False,
            key=f"perf_{video_id}"
        )

    with col2:
        vues = st.number_input(
            "Vues",
            min_value=0,
            value=existing_stats.get("vues", 0) if existing_stats else 0,
            step=1000,
            key=f"vues_{video_id}"
        )
        completion = st.slider(
            "Taux de complétion %",
            min_value=0,
            max_value=100,
            value=int(existing_stats.get("completion_rate", 50)) if existing_stats else 50,
            key=f"completion_{video_id}"
        )

    note = st.text_input(
        "Note rapide (optionnel)",
        value=existing_stats.get("note_humaine", "") if existing_stats else "",
        placeholder="Ex: bon hook mais fin trop longue",
        key=f"note_{video_id}"
    )

    if st.button("💾 ENRICHIR", key=f"enrich_{video_id}", use_container_width=True, type="primary"):
        tag = PERFORMANCE_OPTIONS[perf_label]
        success = save_enrichment(
            video_id=video_id,
            performance_tag=tag,
            vues=vues if vues > 0 else None,
            completion_rate=float(completion),
            note_humaine=note if note else None,
        )
        if success:
            st.success("✅ Enrichissement sauvegardé !")
            nb, niveau = get_precision_level()
            st.markdown(get_precision_badge(nb, niveau), unsafe_allow_html=True)
            return True
        else:
            st.error("Erreur lors de la sauvegarde.")
    return False


def _get_perf_index(tag: str) -> int:
    tags = list(PERFORMANCE_OPTIONS.values())
    try:
        return tags.index(tag)
    except ValueError:
        return 0
