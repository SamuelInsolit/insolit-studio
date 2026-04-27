import json
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Base de Connaissances — Insolit Studio", page_icon="📖", layout="wide")

from modules.styles import apply_styles
apply_styles()

from modules.database import get_session, init_db, Ressource
from datetime import datetime

init_db()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown('<h1 style="color:#ff00a4;font-weight:900;">📖 Base de Connaissances</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:#888;">Enrichis ta base avec des scripts, patterns et insights qui marchent — '
    'Claude s\'en servira pour générer de meilleurs briefs.</p>',
    unsafe_allow_html=True
)

# ─── Types ────────────────────────────────────────────────────────────────────
TYPE_OPTIONS = {
    "📝 Script": "script",
    "🎯 Pattern / Format": "pattern",
    "💡 Inspiration": "inspiration",
    "🔍 Concurrent": "competitor",
    "📐 Guideline Insolit": "guideline",
}

TYPE_COLORS = {
    "script":     "#ff00a4",
    "pattern":    "#0000ff",
    "inspiration":"#01f0fc",
    "competitor": "#ff6600",
    "guideline":  "#00cc66",
}

TYPE_LABELS = {
    "script":     "📝 Script",
    "pattern":    "🎯 Pattern",
    "inspiration":"💡 Inspiration",
    "competitor": "🔍 Concurrent",
    "guideline":  "📐 Guideline",
}

PERF_OPTIONS = {
    "🔥 Viral +500k": "viral",
    "✅ Bon 50-500k":  "bon",
    "😐 Moyen 10-50k": "moyen",
    "—": None,
}

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_add, tab_browse, tab_stats = st.tabs(["➕ Ajouter", "📚 Parcourir", "📊 Stats"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Ajouter une ressource
# ══════════════════════════════════════════════════════════════════════════════
with tab_add:
    st.markdown("### Ajouter une ressource")

    col1, col2 = st.columns([1, 1])

    with col1:
        type_label = st.selectbox("Type", list(TYPE_OPTIONS.keys()), key="new_type")
        titre = st.text_input("Titre *", placeholder="Ex: Hook prix choc O'Tacos Chamigny", key="new_titre")
        compte_source = st.text_input("Compte source (optionnel)", placeholder="@otacos", key="new_compte")
        tags_input = st.text_input(
            "Tags (séparés par des virgules)",
            placeholder="hook, prix, restaurant, tiktok",
            key="new_tags"
        )

    with col2:
        perf_label = st.selectbox("Performance (si connue)", list(PERF_OPTIONS.keys()), key="new_perf")
        vues = st.number_input("Vues approx.", min_value=0, value=0, step=10000, key="new_vues")
        notes = st.text_area("Notes personnelles", placeholder="Pourquoi ça marche, contexte...", height=80, key="new_notes")

    contenu = st.text_area(
        "Contenu *  (script, description du pattern, ou toute donnée utile)",
        placeholder="""Ex. script :
[0-1s] Prix affiché en gros : 6,99€
[1-3s] Zoom sur le plat, voix off : \"Et c'est chaud, c'est là, c'est maintenant\"
[3-5s] Réaction client avec badge \\\"Meilleur rapport qualité/prix\\\"

Ex. pattern :
Hook = prix en gros + durée < 1s
Proof = 1 client réel
CTA = localisation + heure""",
        height=220,
        key="new_contenu"
    )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("💾 ENREGISTRER", use_container_width=True, type="primary"):
            if not titre.strip() or not contenu.strip():
                st.error("Titre et Contenu sont obligatoires.")
            else:
                tags_list = [t.strip() for t in tags_input.split(",") if t.strip()]
                perf_val = PERF_OPTIONS.get(perf_label)
                session = get_session()
                try:
                    r = Ressource(
                        type_ressource=TYPE_OPTIONS[type_label],
                        titre=titre.strip(),
                        contenu=contenu.strip(),
                        tags=json.dumps(tags_list, ensure_ascii=False),
                        compte_source=compte_source.strip() or None,
                        vues_approx=int(vues) if vues > 0 else None,
                        performance_tag=perf_val,
                        notes=notes.strip() or None,
                    )
                    session.add(r)
                    session.commit()
                    st.success(f"✅ «{titre}» ajouté à la base !")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"Erreur : {e}")
                finally:
                    session.close()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Parcourir
# ══════════════════════════════════════════════════════════════════════════════
with tab_browse:
    session = get_session()
    try:
        all_resources = session.query(Ressource).order_by(Ressource.created_at.desc()).all()
    finally:
        session.close()

    if not all_resources:
        st.info("Aucune ressource encore. Va dans **Ajouter** pour commencer ! 💪")
        st.stop()

    # Filtres
    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
    with col_f1:
        filter_type = st.selectbox(
            "Filtrer par type",
            ["Tous"] + list(TYPE_OPTIONS.keys()),
            key="filter_type"
        )
    with col_f2:
        filter_perf = st.selectbox(
            "Filtrer par performance",
            ["Tous", "🔥 Viral", "✅ Bon", "😐 Moyen"],
            key="filter_perf"
        )
    with col_f3:
        search_q = st.text_input("🔍 Rechercher", placeholder="mot clé...", key="search_ressources")

    # Filtrage
    filtered = all_resources
    if filter_type != "Tous":
        type_val = TYPE_OPTIONS[filter_type]
        filtered = [r for r in filtered if r.type_ressource == type_val]
    if filter_perf != "Tous":
        perf_map = {"🔥 Viral": "viral", "✅ Bon": "bon", "😐 Moyen": "moyen"}
        pv = perf_map.get(filter_perf)
        filtered = [r for r in filtered if r.performance_tag == pv]
    if search_q.strip():
        q = search_q.lower()
        filtered = [r for r in filtered if (
            q in (r.titre or "").lower() or
            q in (r.contenu or "").lower() or
            q in (r.notes or "").lower() or
            q in (r.tags or "").lower()
        )]

    st.markdown(f"**{len(filtered)} ressource(s)**")

    for r in filtered:
        color = TYPE_COLORS.get(r.type_ressource, "#333")
        type_label_display = TYPE_LABELS.get(r.type_ressource, r.type_ressource)
        tags_list = json.loads(r.tags) if r.tags else []

        perf_html = ""
        if r.performance_tag:
            perf_colors = {"viral": "#ff00a4", "bon": "#01f0fc", "moyen": "#0000ff"}
            pc = perf_colors.get(r.performance_tag, "#333")
            tc = "#000" if r.performance_tag == "bon" else "#fff"
            perf_html = f'<span style="background:{pc};color:{tc};padding:2px 8px;border-radius:10px;font-size:0.7em;font-weight:700;">{r.performance_tag.upper()}</span>'

        vues_html = f'&nbsp;·&nbsp;👁 {r.vues_approx:,}' if r.vues_approx else ""

        tags_html = " ".join([
            f'<span style="background:#111;border:1px solid #333;padding:1px 6px;border-radius:8px;font-size:0.7em;color:#aaa;">{t}</span>'
            for t in tags_list[:6]
        ])

        with st.expander(f"{type_label_display} · {r.titre}", expanded=False):
            st.markdown(f"""
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
                <span style="background:{color};color:#fff;padding:2px 10px;border-radius:10px;font-size:0.75em;font-weight:700;">{type_label_display}</span>
                {perf_html}
                {f'<span style="color:#888;font-size:0.8em;">{r.compte_source}{vues_html}</span>' if r.compte_source or r.vues_approx else ''}
                {tags_html}
            </div>
            """, unsafe_allow_html=True)

            # Contenu
            st.markdown("**📄 Contenu :**")
            st.code(r.contenu, language=None)

            if r.notes:
                st.markdown(f"**💭 Notes :** {r.notes}")

            col_copy, col_edit, col_del = st.columns([2, 1, 1])
            with col_copy:
                if st.button("📋 Copier", key=f"copy_{r.id}", use_container_width=True):
                    st.code(r.contenu)
                    st.toast("Copié dans la zone ci-dessus !")

            with col_del:
                if st.button("🗑️ Supprimer", key=f"del_{r.id}", use_container_width=True):
                    if st.session_state.get(f"confirm_del_{r.id}"):
                        s2 = get_session()
                        try:
                            s2.query(Ressource).filter_by(id=r.id).delete()
                            s2.commit()
                            st.success("Supprimé !")
                            st.rerun()
                        finally:
                            s2.close()
                    else:
                        st.session_state[f"confirm_del_{r.id}"] = True
                        st.warning("Re-clique pour confirmer la suppression.")

            st.caption(f"Ajouté le {r.created_at.strftime('%d/%m/%Y à %H:%M')}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Stats
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    session = get_session()
    try:
        all_r = session.query(Ressource).all()
    finally:
        session.close()

    if not all_r:
        st.info("Aucune donnée encore.")
        st.stop()

    # Comptage par type
    type_counts = {}
    for r in all_r:
        t = r.type_ressource or "autre"
        type_counts[t] = type_counts.get(t, 0) + 1

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total ressources", len(all_r))
    with col2:
        scripts = type_counts.get("script", 0)
        st.metric("Scripts", scripts)
    with col3:
        patterns = type_counts.get("pattern", 0)
        st.metric("Patterns", patterns)
    with col4:
        viraux = sum(1 for r in all_r if r.performance_tag == "viral")
        st.metric("Ressources virales", viraux)

    st.markdown("---")
    st.markdown("### 📊 Répartition par type")

    for type_key, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        label = TYPE_LABELS.get(type_key, type_key)
        color = TYPE_COLORS.get(type_key, "#333")
        pct = count / len(all_r) * 100
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
            <span style="width:120px;font-size:0.85em;">{label}</span>
            <div style="flex:1;background:#111;border-radius:4px;height:16px;overflow:hidden;">
                <div style="width:{pct:.0f}%;background:{color};height:100%;border-radius:4px;"></div>
            </div>
            <span style="width:40px;text-align:right;font-size:0.85em;color:#aaa;">{count}</span>
        </div>
        """, unsafe_allow_html=True)

    # Top scripts par vues
    top_vues = sorted([r for r in all_r if r.vues_approx], key=lambda x: -x.vues_approx)[:5]
    if top_vues:
        st.markdown("---")
        st.markdown("### 🏆 Top ressources par vues")
        for r in top_vues:
            color = TYPE_COLORS.get(r.type_ressource, "#333")
            st.markdown(f"""
            <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-left:4px solid {color};
                        border-radius:8px;padding:10px 14px;margin-bottom:8px;">
                <strong>{r.titre}</strong>
                <span style="color:#888;font-size:0.8em;"> · 👁 {r.vues_approx:,} vues</span>
            </div>
            """, unsafe_allow_html=True)
