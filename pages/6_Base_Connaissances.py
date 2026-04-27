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

# ─── Types & labels ───────────────────────────────────────────────────────────
TYPE_OPTIONS = {
    "📝 Script":          "script",
    "🎯 Pattern / Format": "pattern",
    "💡 Inspiration":     "inspiration",
    "🔍 Concurrent":      "competitor",
    "📐 Guideline Insolit": "guideline",
}
TYPE_COLORS = {
    "script":     "#ff00a4",
    "pattern":    "#7c3aed",
    "inspiration": "#01f0fc",
    "competitor": "#ff6600",
    "guideline":  "#00cc66",
}
TYPE_LABELS = {
    "script":     "📝 Script",
    "pattern":    "🎯 Pattern",
    "inspiration": "💡 Inspiration",
    "competitor": "🔍 Concurrent",
    "guideline":  "📐 Guideline",
}
PERF_OPTIONS = {
    "🔥 Viral +500k": "viral",
    "✅ Bon 50-500k":  "bon",
    "😐 Moyen 10-50k": "moyen",
    "—":              None,
}
PERF_COLORS = {"viral": "#ff00a4", "bon": "#01f0fc", "moyen": "#7c3aed"}


def _engagement_rate(r: Ressource) -> float | None:
    """Taux d'engagement = (likes + commentaires + partages + enregistrements) / vues × 100."""
    if not r.vues_approx or r.vues_approx == 0:
        return None
    total = (r.nb_likes or 0) + (r.nb_commentaires or 0) + (r.nb_partages or 0) + (r.nb_enregistrements or 0)
    return round(total / r.vues_approx * 100, 2)


def _save_rate(r: Ressource) -> float | None:
    """Ratio enregistrements/vues — meilleur indicateur de valeur perçue."""
    if not r.vues_approx or r.vues_approx == 0 or not r.nb_enregistrements:
        return None
    return round(r.nb_enregistrements / r.vues_approx * 100, 2)


def _fmt_num(n) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown('<h1 style="color:#ff00a4;font-weight:900;">📖 Base de Connaissances</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:#888;">Scripts, patterns et insights qui marchent — avec stats réelles. '
    'Claude s\'en sert pour générer de meilleurs briefs et affiner ses analyses.</p>',
    unsafe_allow_html=True
)

tab_add, tab_browse, tab_stats = st.tabs(["➕ Ajouter", "📚 Parcourir", "📊 Stats & Insights"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — AJOUTER
# ══════════════════════════════════════════════════════════════════════════════
with tab_add:
    st.markdown("### Ajouter une ressource")

    # ── Bloc 1 : Type + Source ─────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        type_label = st.selectbox("Type", list(TYPE_OPTIONS.keys()), key="new_type")
        titre      = st.text_input("Titre *", placeholder="Ex: Hook prix choc Chicken Street Clichy", key="new_titre")
        compte_source = st.text_input("Compte source", placeholder="@insolitparis", key="new_compte")
        url_source = st.text_input("URL source (TikTok / Instagram)", placeholder="https://www.tiktok.com/@.../video/...", key="new_url")

    with col2:
        perf_label = st.selectbox("Performance", list(PERF_OPTIONS.keys()), key="new_perf")
        tags_input = st.text_input("Tags (virgules)", placeholder="hook, prix, chicken, clichy", key="new_tags")
        contexte   = st.text_input("Contexte (optionnel)", placeholder="Ex: période soldes, tendance ramen, ouverture...", key="new_contexte")
        hook_texte = st.text_input("Hook exact (texte dit / affiché)", placeholder="Ex: '100 menus offerts Chicken Street Clichy'", key="new_hook")

    # ── Bloc 2 : Stats engagement ──────────────────────────────────────────────
    st.markdown("#### 📊 Stats engagement")
    st.caption("Plus tu remplis, plus Claude peut identifier ce qui fait vraiment performer une vidéo.")

    c1, c2, c3 = st.columns(3)
    with c1:
        vues          = st.number_input("👁 Vues",           min_value=0, value=0, step=1000,  key="new_vues",          format="%d")
        nb_partages   = st.number_input("↗️ Partages",       min_value=0, value=0, step=100,   key="new_partages",      format="%d")
    with c2:
        nb_likes      = st.number_input("❤️ Likes",          min_value=0, value=0, step=100,   key="new_likes",         format="%d")
        nb_enreg      = st.number_input("🔖 Enregistrements",min_value=0, value=0, step=100,   key="new_enregistrements", format="%d")
    with c3:
        nb_comments   = st.number_input("💬 Commentaires",   min_value=0, value=0, step=10,    key="new_commentaires",  format="%d")
        taux_compl    = st.number_input("⏱️ Taux complétion (%)", min_value=0.0, max_value=100.0,
                                        value=0.0, step=1.0, key="new_taux_completion", format="%.1f")

    # Preview taux d'engagement en temps réel
    if vues > 0:
        eng_preview = round(((nb_likes + nb_comments + nb_partages + nb_enreg) / vues) * 100, 2)
        save_preview = round((nb_enreg / vues) * 100, 2) if nb_enreg > 0 else 0
        c_a, c_b, c_c = st.columns(3)
        with c_a:
            st.metric("Taux d'engagement", f"{eng_preview}%", help="(likes+commentaires+partages+enreg) / vues × 100")
        with c_b:
            st.metric("Save rate", f"{save_preview}%", help="Enregistrements / vues × 100 — meilleur indicateur de valeur")
        with c_c:
            like_rate = round((nb_likes / vues) * 100, 2) if nb_likes > 0 else 0
            st.metric("Like rate", f"{like_rate}%")

    st.markdown("---")

    # ── Bloc 3 : Analyse qualitative ─────────────────────────────────────────
    st.markdown("#### 🧠 Analyse qualitative")

    col_a, col_b = st.columns(2)
    with col_a:
        ce_qui_marche = st.text_area(
            "✅ Ce qui marche (pourquoi ça performe)",
            placeholder="Ex: Le chiffre '100 menus offerts' crée une urgence immédiate. Le visage réactif valide socialement. Le lieu précis (Clichy-la-Garenne) filtre une audience locale qualifiée.",
            height=120, key="new_ce_qui_marche"
        )
    with col_b:
        a_reproduire = st.text_area(
            "🎯 À reproduire exactement",
            placeholder="Ex: Toujours afficher le chiffre en grand dès la 1ère seconde. Toujours inclure la ville. Toujours avoir un visage réactif dans les 3 premières secondes.",
            height=120, key="new_a_reproduire"
        )

    # ── Bloc 4 : Contenu/Script ────────────────────────────────────────────────
    contenu = st.text_area(
        "📄 Script / Contenu complet *",
        placeholder="""[0-1s] Texte overlay GROS : '100 MENUS OFFERTS / CHICKEN STREET CLICHY'
[0-3s] Visage caméra, voix : 'Les gars...' (teasing)
[3-8s] Coupe — plan table, les deux présentent des pancartes avec notes
[8-15s] Dégustation / réaction
[15-25s] Résultat final + sous-titres
[25-30s] CTA localisation + @compte

Pattern : Chiffre choc → teasing → preuve → résultat → CTA""",
        height=200, key="new_contenu"
    )

    notes = st.text_area("💭 Notes libres", placeholder="Contexte, idées, variations possibles...", height=60, key="new_notes")

    # ── Bouton save ────────────────────────────────────────────────────────────
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("💾 ENREGISTRER", use_container_width=True, type="primary"):
            if not titre.strip() or not contenu.strip():
                st.error("Titre et Contenu sont obligatoires.")
            else:
                tags_list = [t.strip() for t in tags_input.split(",") if t.strip()]
                perf_val  = PERF_OPTIONS.get(perf_label)
                session   = get_session()
                try:
                    r = Ressource(
                        type_ressource    = TYPE_OPTIONS[type_label],
                        titre             = titre.strip(),
                        contenu           = contenu.strip(),
                        tags              = json.dumps(tags_list, ensure_ascii=False),
                        url_source        = url_source.strip() or None,
                        compte_source     = compte_source.strip() or None,
                        vues_approx       = int(vues)        if vues > 0      else None,
                        nb_likes          = int(nb_likes)    if nb_likes > 0  else None,
                        nb_commentaires   = int(nb_comments) if nb_comments>0 else None,
                        nb_partages       = int(nb_partages) if nb_partages>0 else None,
                        nb_enregistrements= int(nb_enreg)    if nb_enreg > 0  else None,
                        taux_completion   = float(taux_compl) if taux_compl > 0 else None,
                        hook_texte        = hook_texte.strip() or None,
                        ce_qui_marche     = ce_qui_marche.strip() or None,
                        a_reproduire      = a_reproduire.strip() or None,
                        contexte          = contexte.strip() or None,
                        performance_tag   = perf_val,
                        notes             = notes.strip() or None,
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
# TAB 2 — PARCOURIR
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

    # ── Filtres ────────────────────────────────────────────────────────────────
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 2])
    with col_f1:
        filter_type = st.selectbox("Type", ["Tous"] + list(TYPE_OPTIONS.keys()), key="filter_type")
    with col_f2:
        filter_perf = st.selectbox("Performance", ["Toutes", "🔥 Viral", "✅ Bon", "😐 Moyen", "⬜ Non annoté"], key="filter_perf")
    with col_f3:
        filter_sort = st.selectbox("Trier par", ["Plus récent", "Plus de vues", "Meilleur engagement", "Meilleur save rate"], key="filter_sort")
    with col_f4:
        search_q = st.text_input("🔍 Rechercher", placeholder="mot clé...", key="search_ressources", label_visibility="collapsed")

    # ── Filtrage ───────────────────────────────────────────────────────────────
    filtered = all_resources
    if filter_type != "Tous":
        type_val = TYPE_OPTIONS[filter_type]
        filtered = [r for r in filtered if r.type_ressource == type_val]
    perf_map = {"🔥 Viral": "viral", "✅ Bon": "bon", "😐 Moyen": "moyen"}
    if filter_perf == "⬜ Non annoté":
        filtered = [r for r in filtered if not r.performance_tag]
    elif filter_perf != "Toutes":
        pv = perf_map.get(filter_perf)
        filtered = [r for r in filtered if r.performance_tag == pv]
    if search_q.strip():
        q = search_q.lower()
        filtered = [r for r in filtered if
            q in (r.titre or "").lower() or
            q in (r.contenu or "").lower() or
            q in (r.hook_texte or "").lower() or
            q in (r.ce_qui_marche or "").lower() or
            q in (r.tags or "").lower()]

    # ── Tri ────────────────────────────────────────────────────────────────────
    if filter_sort == "Plus de vues":
        filtered.sort(key=lambda r: r.vues_approx or 0, reverse=True)
    elif filter_sort == "Meilleur engagement":
        filtered.sort(key=lambda r: _engagement_rate(r) or 0, reverse=True)
    elif filter_sort == "Meilleur save rate":
        filtered.sort(key=lambda r: _save_rate(r) or 0, reverse=True)

    st.markdown(f"**{len(filtered)} ressource(s)**")

    for r in filtered:
        color       = TYPE_COLORS.get(r.type_ressource, "#333")
        type_lbl    = TYPE_LABELS.get(r.type_ressource, r.type_ressource)
        tags_list   = json.loads(r.tags) if r.tags else []
        eng_rate    = _engagement_rate(r)
        save_rate_v = _save_rate(r)

        # Badge performance
        perf_html = ""
        if r.performance_tag:
            pc = PERF_COLORS.get(r.performance_tag, "#333")
            tc = "#000" if r.performance_tag == "bon" else "#fff"
            perf_html = f'<span style="background:{pc};color:{tc};padding:2px 8px;border-radius:10px;font-size:0.7em;font-weight:700;">{r.performance_tag.upper()}</span>'

        # Tags
        tags_html = " ".join([
            f'<span style="background:#111;border:1px solid #333;padding:1px 6px;border-radius:8px;font-size:0.7em;color:#aaa;">{t}</span>'
            for t in tags_list[:6]
        ])

        # Métriques inline
        metrics_parts = []
        if r.vues_approx:  metrics_parts.append(f"👁 {_fmt_num(r.vues_approx)}")
        if r.nb_likes:      metrics_parts.append(f"❤️ {_fmt_num(r.nb_likes)}")
        if r.nb_commentaires: metrics_parts.append(f"💬 {_fmt_num(r.nb_commentaires)}")
        if r.nb_partages:   metrics_parts.append(f"↗️ {_fmt_num(r.nb_partages)}")
        if r.nb_enregistrements: metrics_parts.append(f"🔖 {_fmt_num(r.nb_enregistrements)}")
        if eng_rate:        metrics_parts.append(f"⚡ {eng_rate}% eng")
        if save_rate_v:     metrics_parts.append(f"🎯 {save_rate_v}% saves")
        metrics_inline = " &nbsp;·&nbsp; ".join(metrics_parts)

        expander_title = f"{type_lbl} · {r.titre}"
        with st.expander(expander_title, expanded=False):
            # Header badges
            st.markdown(f"""
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
                <span style="background:{color};color:#fff;padding:2px 10px;border-radius:10px;font-size:0.75em;font-weight:700;">{type_lbl}</span>
                {perf_html}
                {f'<span style="color:#666;font-size:0.8em;">@{r.compte_source}</span>' if r.compte_source else ''}
                {tags_html}
            </div>
            """, unsafe_allow_html=True)

            # Stats bar
            if metrics_parts:
                st.markdown(f"""
                <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-radius:8px;
                            padding:8px 14px;margin-bottom:10px;font-size:0.82em;color:#aaa;">
                    {metrics_inline}
                </div>
                """, unsafe_allow_html=True)

            # Hook
            if r.hook_texte:
                st.markdown(f"""
                <div style="background:#0d0008;border-left:3px solid #ff00a4;border-radius:0 8px 8px 0;
                            padding:8px 12px;margin-bottom:8px;">
                    <span style="color:#ff00a4;font-size:0.75em;font-weight:700;">🎣 HOOK</span><br>
                    <span style="font-size:0.9em;">«{r.hook_texte}»</span>
                </div>
                """, unsafe_allow_html=True)

            # Analyse qualitative (2 colonnes)
            if r.ce_qui_marche or r.a_reproduire:
                ca, cb = st.columns(2)
                with ca:
                    if r.ce_qui_marche:
                        st.markdown("**✅ Ce qui marche**")
                        st.markdown(f'<p style="color:#aaa;font-size:0.85em;">{r.ce_qui_marche}</p>', unsafe_allow_html=True)
                with cb:
                    if r.a_reproduire:
                        st.markdown("**🎯 À reproduire**")
                        st.markdown(f'<p style="color:#aaa;font-size:0.85em;">{r.a_reproduire}</p>', unsafe_allow_html=True)

            # Contenu/Script
            st.markdown("**📄 Script / Contenu :**")
            st.code(r.contenu, language=None)

            # Contexte + notes
            if r.contexte:
                st.caption(f"🌍 Contexte : {r.contexte}")
            if r.notes:
                st.caption(f"💭 Notes : {r.notes}")

            # Lien source
            if r.url_source:
                st.markdown(f"🔗 [Voir la vidéo source]({r.url_source})")

            # Actions
            col_copy, col_del = st.columns([3, 1])
            with col_copy:
                if st.button("📋 Copier le contenu", key=f"copy_{r.id}", use_container_width=True):
                    st.code(r.contenu)

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
                        st.warning("Re-clique pour confirmer.")

            st.caption(f"Ajouté le {r.created_at.strftime('%d/%m/%Y à %H:%M')}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — STATS & INSIGHTS
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

    # ── KPIs ───────────────────────────────────────────────────────────────────
    viraux   = [r for r in all_r if r.performance_tag == "viral"]
    avec_stats = [r for r in all_r if r.vues_approx]
    avg_eng  = None
    if avec_stats:
        rates = [_engagement_rate(r) for r in avec_stats if _engagement_rate(r)]
        avg_eng = round(sum(rates) / len(rates), 2) if rates else None

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Total ressources", len(all_r))
    with c2: st.metric("🔥 Virales", len(viraux))
    with c3: st.metric("Avec stats", len(avec_stats))
    with c4: st.metric("Taux eng. moyen", f"{avg_eng}%" if avg_eng else "—")
    with c5:
        scripts_count = sum(1 for r in all_r if r.type_ressource == "script")
        st.metric("Scripts", scripts_count)

    st.markdown("---")

    # ── Répartition par type ────────────────────────────────────────────────
    type_counts = {}
    for r in all_r:
        t = r.type_ressource or "autre"
        type_counts[t] = type_counts.get(t, 0) + 1

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 📊 Répartition par type")
        for type_key, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            label = TYPE_LABELS.get(type_key, type_key)
            color = TYPE_COLORS.get(type_key, "#333")
            pct   = count / len(all_r) * 100
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                <span style="width:120px;font-size:0.85em;">{label}</span>
                <div style="flex:1;background:#111;border-radius:4px;height:14px;overflow:hidden;">
                    <div style="width:{pct:.0f}%;background:{color};height:100%;border-radius:4px;"></div>
                </div>
                <span style="width:30px;text-align:right;font-size:0.85em;color:#aaa;">{count}</span>
            </div>
            """, unsafe_allow_html=True)

    with col_right:
        st.markdown("### 🏆 Top save rate (meilleur indicateur)")
        top_save = sorted(
            [r for r in all_r if _save_rate(r) is not None],
            key=lambda r: _save_rate(r), reverse=True
        )[:6]
        if top_save:
            for r in top_save:
                sr = _save_rate(r)
                color = TYPE_COLORS.get(r.type_ressource, "#333")
                st.markdown(f"""
                <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-left:4px solid {color};
                            border-radius:8px;padding:8px 12px;margin-bottom:6px;display:flex;
                            justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-size:0.85em;font-weight:700;">{r.titre[:45]}</div>
                        <div style="font-size:0.75em;color:#666;">
                            {_fmt_num(r.vues_approx)} vues · 🔖 {_fmt_num(r.nb_enregistrements)}
                        </div>
                    </div>
                    <span style="color:#ff00a4;font-weight:900;font-size:1.1em;">{sr}%</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Ajoute des enregistrements pour voir ce classement.")

    st.markdown("---")

    # ── Top engagement rate ──────────────────────────────────────────────────
    st.markdown("### ⚡ Top taux d'engagement")
    top_eng = sorted(
        [r for r in all_r if _engagement_rate(r) is not None],
        key=lambda r: _engagement_rate(r), reverse=True
    )[:8]
    if top_eng:
        for r in top_eng:
            eng  = _engagement_rate(r)
            sr   = _save_rate(r)
            color = TYPE_COLORS.get(r.type_ressource, "#333")
            perf_badge = ""
            if r.performance_tag:
                pc = PERF_COLORS.get(r.performance_tag, "#333")
                tc = "#000" if r.performance_tag == "bon" else "#fff"
                perf_badge = f'<span style="background:{pc};color:{tc};padding:1px 7px;border-radius:8px;font-size:0.7em;font-weight:700;">{r.performance_tag.upper()}</span>'

            st.markdown(f"""
            <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-left:4px solid {color};
                        border-radius:8px;padding:10px 14px;margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                        <div style="font-weight:700;font-size:0.9em;">{r.titre[:55]}</div>
                        <div style="margin-top:4px;font-size:0.78em;color:#666;">
                            {_fmt_num(r.vues_approx)} vues &nbsp;·&nbsp;
                            ❤️ {_fmt_num(r.nb_likes)} &nbsp;·&nbsp;
                            💬 {_fmt_num(r.nb_commentaires)} &nbsp;·&nbsp;
                            ↗️ {_fmt_num(r.nb_partages)} &nbsp;·&nbsp;
                            🔖 {_fmt_num(r.nb_enregistrements)}
                            {f"&nbsp;·&nbsp; ⏱️ {r.taux_completion:.0f}% compl." if r.taux_completion else ""}
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:#ff00a4;font-weight:900;font-size:1.2em;">{eng}%</div>
                        {f'<div style="color:#888;font-size:0.75em;">🎯 {sr}% saves</div>' if sr else ''}
                        {perf_badge}
                    </div>
                </div>
                {f'<div style="margin-top:6px;padding-top:6px;border-top:1px solid #1a1a1a;font-size:0.8em;color:#888;"><em>«{r.hook_texte}»</em></div>' if r.hook_texte else ''}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("Ajoute des stats à tes ressources pour voir les insights d'engagement.")

    st.markdown("---")

    # ── Ce qui marche — synthèse ───────────────────────────────────────────
    ressources_analysees = [r for r in all_r if r.ce_qui_marche]
    if ressources_analysees:
        st.markdown("### 💡 Insights qualitatifs (ce qui marche)")
        for r in sorted(ressources_analysees, key=lambda r: r.vues_approx or 0, reverse=True)[:5]:
            color = TYPE_COLORS.get(r.type_ressource, "#333")
            st.markdown(f"""
            <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-left:3px solid {color};
                        border-radius:8px;padding:10px 14px;margin-bottom:8px;">
                <div style="font-weight:700;font-size:0.85em;margin-bottom:4px;">
                    {r.titre[:60]}
                    {f'&nbsp; <span style="color:#888;font-size:0.75em;">{_fmt_num(r.vues_approx)} vues</span>' if r.vues_approx else ''}
                </div>
                <div style="color:#aaa;font-size:0.82em;">{r.ce_qui_marche}</div>
                {f'<div style="margin-top:6px;color:#01f0fc;font-size:0.8em;">→ <strong>À reproduire :</strong> {r.a_reproduire}</div>' if r.a_reproduire else ''}
            </div>
            """, unsafe_allow_html=True)
