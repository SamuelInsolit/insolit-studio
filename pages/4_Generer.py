import json
import html as html_lib
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Générer — Insolit Studio", page_icon="✨", layout="wide")

from modules.styles import apply_styles
apply_styles()

st.markdown("""
<style>
.brief-box {
    background: #0a0a0a;
    border: 1px solid #ff00a4;
    border-radius: 12px;
    padding: 1.5rem;
    font-family: monospace;
}
.hook-card {
    background: #111;
    border: 2px solid #333;
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.4rem;
}
.hook-card.selected {
    border-color: #ff00a4;
    background: #1a0010;
}
.kb-counter {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    font-size: 0.82rem;
    color: #8b949e;
    margin-bottom: 1rem;
}
.confidence-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    background: #111;
    border: 1px solid #333;
    border-radius: 20px;
    padding: 0.3rem 0.9rem;
    font-size: 0.8rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 style="color:#ff00a4;font-weight:900;">✨ Générer un brief</h1>', unsafe_allow_html=True)

from modules.database import (
    get_precision_level, get_best_videos, get_session,
    get_full_knowledge_context, Brief, Video, Stats, AnalyseCreative,
)
from modules.enrichment import get_precision_badge

nb_annotees, niveau = get_precision_level()
st.markdown(get_precision_badge(nb_annotees, niveau), unsafe_allow_html=True)

if nb_annotees < 5:
    manquantes = 5 - nb_annotees
    st.warning(f"⚠️ Il manque **{manquantes} vidéo{'s' if manquantes > 1 else ''}** annotées pour générer des briefs fiables.")
    st.info("Analyse et enrichis tes vidéos depuis la page **Analyser**.")
    st.stop()

# ── Contexte KB (chargé 1 fois) ───────────────────────────────────────────────
kb_ctx = get_full_knowledge_context()
stats_kb = kb_ctx.get("stats_agregees", {})
nb_scripts_kb = stats_kb.get("nb_ressources_kb", 0)
nb_hooks_kb   = stats_kb.get("nb_hooks_kb", 0)
nb_videos_ann = stats_kb.get("nb_videos_annotees", 0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _confidence_info(n: int):
    if n < 10:
        return "FAIBLE", "#FF6B35", "Annote " + str(10 - n) + " vidéo" + ("s" if 10 - n > 1 else "") + " de plus pour améliorer"
    elif n < 30:
        return "BONNE", "#FFD700", str(30 - n) + " vidéos de plus pour EXCELLENTE"
    else:
        return "EXCELLENTE", "#00C853", "Base mature — briefs très fiables"


def _render_brief_text(brief: dict, partenaire: str, ville: str, hook_idx: int = 0) -> str:
    """Formate le brief sélectionné en texte export (nouveau format multi-hooks)."""
    hooks   = brief.get("hooks", [])
    scripts = brief.get("scripts", [])
    plans   = brief.get("plans", [])

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🎬 BRIEF — " + partenaire.upper() + " " + ville,
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    duree = brief.get("duree_totale_estimee")
    if duree:
        lines.append("⏱ DURÉE : " + str(duree) + "s")
        lines.append("")

    hook = hooks[hook_idx] if hooks and hook_idx < len(hooks) else None
    if hook:
        lines.append("🎣 HOOK : " + chr(171) + hook.get("texte", "") + chr(187))
        inspire = hook.get("inspire_de", "") or ""
        if inspire and inspire not in ("aucune source directe", "Analyse générale", ""):
            lines.append("   Inspiré de : " + inspire)
        lines.append("")

    hook_id_target = hook_idx + 1
    script = next((s for s in scripts if s.get("hook_id") == hook_id_target), scripts[0] if scripts else None)
    if script:
        lignes = script.get("lignes", [])
        if lignes:
            lines.append("📋 SCRIPT :")
            for lg in lignes:
                ts    = lg.get("timestamp", "")
                texte = lg.get("texte_a_dire", "")
                ecran = lg.get("texte_ecran", "")
                lines.append("   [" + ts + "] " + chr(34) + texte + chr(34))
                if ecran:
                    lines.append("         Écran : " + ecran)
            lines.append("")

    if plans:
        lines.append("🎥 PLANS :")
        for p in plans:
            num     = str(p.get("numero", "?")).zfill(2)
            ts      = p.get("timestamp", "")
            desc    = p.get("description_precise", "")
            lumiere = p.get("conseil_lumiere", "")
            camera  = p.get("conseil_camera", "")
            terrain = p.get("conseil_pratique", "")
            try:
                diff = int(p.get("difficulte", 1))
            except (ValueError, TypeError):
                diff = 1
            lines.append("   " + num + " | " + ts + " | " + desc)
            if lumiere: lines.append("       Lumière : " + lumiere)
            if camera:  lines.append("       Caméra  : " + camera)
            if terrain: lines.append("       Astuce  : " + terrain)
            lines.append("       Difficulté : " + "⭐" * diff)
        lines.append("")

    tournage = brief.get("temps_tournage_minutes")
    montage  = brief.get("temps_montage_minutes")
    niv      = brief.get("niveau_global")
    if tournage or montage:
        lines.append("⏰ Tournage : " + str(tournage) + "min | Montage : " + str(montage) + "min")
        if niv:
            lines.append("   Niveau : " + niv)
        lines.append("")

    publi = brief.get("meilleur_moment_publication")
    if publi:
        lines.append("📅 Publier : " + publi)
        lines.append("")

    mots_ok  = brief.get("mots_cles_a_utiliser", [])
    mots_non = brief.get("mots_a_eviter", [])
    if mots_ok:
        lines.append("✅ Mots qui marchent : " + " ".join(chr(34) + m + chr(34) for m in mots_ok))
    if mots_non:
        lines.append("❌ À éviter : " + " ".join(chr(34) + m + chr(34) for m in mots_non))
    if mots_ok or mots_non:
        lines.append("")

    suggestions = brief.get("suggestions_bonus", [])
    if suggestions:
        lines.append("💡 Suggestions bonus :")
        for s in suggestions:
            lines.append("   • " + s)
        lines.append("")

    son = brief.get("son_tendance_conseil")
    if son:
        lines.append("🎵 Son : " + son)
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


# ── Layout ────────────────────────────────────────────────────────────────────
col_form, col_result = st.columns([1, 2], gap="large")

with col_form:
    st.markdown("### 📝 Paramètres du brief")

    # Compteur KB
    parts = []
    if nb_scripts_kb: parts.append("<b>" + str(nb_scripts_kb) + " scripts</b>")
    if nb_hooks_kb:   parts.append("<b>" + str(nb_hooks_kb)   + " hooks</b>")
    parts.append("<b>" + str(nb_videos_ann) + " vidéos</b>")
    st.markdown(
        '<div class="kb-counter">🧠 Basé sur ' + " · ".join(parts) + "</div>",
        unsafe_allow_html=True
    )

    type_contenu = st.selectbox(
        "Type de partenaire",
        ["Restaurant", "Bar", "Café", "Food hall", "Dark kitchen", "Événement", "Autre"],
        key="brief_type",
    )
    partenaire = st.text_input("Nom du partenaire", placeholder="Ex: Chez Marcel", key="brief_partenaire")
    ville      = st.text_input("Ville", placeholder="Ex: Paris 11e", key="brief_ville")
    offre      = st.text_area(
        "Offre exacte à mettre en avant",
        placeholder="Ex: Menu déjeuner 3 plats à 18€ avec vin inclus",
        height=80,
        key="brief_offre",
    )
    objectif = st.selectbox(
        "Objectif",
        ["Awareness (faire connaître)", "Conversion (réservations)", "Engagement (likes/partages)", "Viralité"],
        key="brief_objectif",
    )
    duree = st.slider("Durée cible (secondes)", min_value=15, max_value=60, value=30, step=5, key="brief_duree")
    ton = st.selectbox(
        "Ton",
        ["Authentique / spontané", "Enthousiaste / énergie", "Informatif / factuel",
         "Humour / décalé", "Lifestyle / aspirationnel"],
        key="brief_ton",
    )
    source_filter = st.radio(
        "Basé sur",
        ["Mes meilleures vidéos", "Vidéos de concurrents", "Toute la base"],
        horizontal=True,
        key="brief_source",
    )
    source_map = {
        "Mes meilleures vidéos": "mon_compte",
        "Vidéos de concurrents": "concurrent",
        "Toute la base": "all",
    }

    generate_btn = st.button("⚡ GÉNÉRER EN 30s", use_container_width=True, type="primary")


with col_result:
    # ── Indicateur confiance ──────────────────────────────────────────────────
    conf_label, conf_color, conf_tip = _confidence_info(nb_annotees)
    st.markdown(
        '<div class="confidence-badge">'
        'Précision IA : <span style="color:' + conf_color + ';font-weight:700;">● ' + conf_label + '</span>'
        '<span style="color:#555;margin-left:6px;">' + html_lib.escape(conf_tip) + '</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Génération ────────────────────────────────────────────────────────────
    if generate_btn:
        if not partenaire or not offre:
            st.error("Remplis au minimum le nom du partenaire et l'offre.")
            st.stop()

        filter_key = source_map.get(source_filter, "all")
        best_vids  = get_best_videos(source_filter=filter_key, limit=5)

        session = get_session()
        try:
            best_for_claude = []
            for v in best_vids:
                item = {
                    "titre":          v.titre,
                    "duree_secondes": v.duree_secondes,
                    "nom_compte":     v.nom_compte,
                    "categorie":      v.categorie,
                }
                if v.stats:
                    item["vues"]            = v.stats.vues
                    item["performance_tag"] = v.stats.performance_tag
                    item["completion_rate"] = v.stats.completion_rate
                if v.analyse_creative:
                    item["hook_texte"] = v.analyse_creative.hook_texte
                    item["hook_type"]  = v.analyse_creative.hook_type
                    item["hook_score"] = v.analyse_creative.hook_score
                best_for_claude.append(item)
        finally:
            session.close()

        from modules.claude_mod import generate_brief as gen_brief

        nb_r = stats_kb.get("nb_ressources_kb", 0)
        spinner_msg = (
            "Claude génère ton brief (+" + str(nb_r) + " ressources KB)..."
            if nb_r else "Claude génère ton brief..."
        )

        with st.spinner(spinner_msg):
            brief_data, usage = gen_brief(
                type_contenu=type_contenu,
                partenaire=partenaire,
                ville=ville,
                offre=offre,
                objectif=objectif,
                duree=duree,
                ton=ton,
                best_videos=best_for_claude,
                patterns={"nb_videos_base": nb_annotees, "source_filter": source_filter},
                full_context=kb_ctx,
            )

        if "_error" in brief_data:
            st.error("Erreur: " + str(brief_data.get("_error")))
            if brief_data.get("_raw"):
                st.text_area("Réponse brute", brief_data["_raw"], height=300)
            st.stop()

        # Sauvegarde DB
        hooks_data = brief_data.get("hooks", [])
        session = get_session()
        try:
            brief_db = Brief(
                type_contenu=type_contenu,
                partenaire=partenaire,
                ville=ville,
                offre=offre,
                objectif=objectif,
                duree_cible=duree,
                ton=ton,
                hook_suggere=(hooks_data[0]["texte"] if hooks_data
                              else brief_data.get("hook_suggere")),
                script_complet=json.dumps(
                    brief_data.get("scripts", brief_data.get("script_complet", [])),
                    ensure_ascii=False,
                ),
                plans_json=json.dumps(brief_data.get("plans", []), ensure_ascii=False),
                niveau_difficulte=brief_data.get("niveau_global"),
                temps_tournage_estime=brief_data.get("temps_tournage_minutes"),
                temps_montage_estime=brief_data.get("temps_montage_minutes"),
                suggestions=json.dumps({
                    "hooks":            hooks_data,
                    "suggestions_bonus": brief_data.get("suggestions_bonus", []),
                    "avertissements":   brief_data.get("avertissements", []),
                }, ensure_ascii=False),
            )
            session.add(brief_db)
            session.commit()
        finally:
            session.close()

        st.session_state["last_brief"]      = brief_data
        st.session_state["last_brief_meta"] = {
            "partenaire": partenaire,
            "ville":      ville,
            "cout":       usage.get("cout_estime", 0),
        }
        st.session_state["selected_hook_idx"] = 0

        if usage:
            st.caption("Généré | Coût estimé : ~$" + f"{usage.get('cout_estime', 0):.4f}")

    # ── Résultats ─────────────────────────────────────────────────────────────
    if "last_brief" in st.session_state:
        brief = st.session_state["last_brief"]
        meta  = st.session_state.get("last_brief_meta", {})
        partenaire_disp = meta.get("partenaire", "—")
        ville_disp      = meta.get("ville", "")

        hooks   = brief.get("hooks", [])
        scripts = brief.get("scripts", [])
        plans   = brief.get("plans", [])

        # ── B1 : Sélection du hook ────────────────────────────────────────────
        if hooks:
            st.markdown("### 🎣 Choisissez votre hook")
            selected_idx = st.session_state.get("selected_hook_idx", 0)

            cols_per_row = min(len(hooks), 3)
            rows = [hooks[i:i + cols_per_row] for i in range(0, len(hooks), cols_per_row)]

            for row in rows:
                cols = st.columns(len(row))
                for col_widget, hook in zip(cols, row):
                    g_idx      = hooks.index(hook)
                    is_sel     = g_idx == selected_idx
                    border_col = "#ff00a4" if is_sel else "#333"
                    bg_col     = "#1a0010" if is_sel else "#111"
                    score      = hook.get("score_confiance", 0)
                    htype      = (hook.get("type") or "HOOK").upper()
                    texte_esc  = html_lib.escape(hook.get("texte") or "")
                    inspire    = html_lib.escape((hook.get("inspire_de") or ""))
                    show_ins   = inspire not in ("", "aucune source directe", "Analyse générale")

                    inspire_html = (
                        '<div style="font-size:0.75em;color:#666;margin-top:5px;">💡 ' + inspire + '</div>'
                        if show_ins else ""
                    )
                    selected_badge = "✅ " if is_sel else ""

                    with col_widget:
                        st.markdown(
                            '<div style="background:' + bg_col + ';border:2px solid ' + border_col + ';'
                            'border-radius:10px;padding:0.8rem;margin-bottom:0.3rem;min-height:100px;">'
                            '<div style="font-size:0.78em;color:#888;margin-bottom:5px;">'
                            + selected_badge + htype + " · " + str(score) + "% confiance"
                            '</div>'
                            '<div style="font-weight:600;font-size:0.9em;color:#fff;line-height:1.4;">'
                            '«' + texte_esc + '»'
                            '</div>'
                            + inspire_html +
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "✅ Sélectionné" if is_sel else "Choisir ce hook",
                            key="hook_btn_" + str(g_idx),
                            use_container_width=True,
                            type="primary" if is_sel else "secondary",
                        ):
                            st.session_state["selected_hook_idx"] = g_idx
                            st.rerun()

            st.divider()

        # ── B2 : Scripts ──────────────────────────────────────────────────────
        selected_idx   = st.session_state.get("selected_hook_idx", 0)
        hook_id_target = selected_idx + 1
        hook_scripts   = [s for s in scripts if s.get("hook_id") == hook_id_target]
        if not hook_scripts and scripts:
            hook_scripts = scripts[:2]

        if hook_scripts:
            st.markdown("### 📋 Scripts disponibles")
            for i, script in enumerate(hook_scripts):
                score  = script.get("score_confiance", 0)
                titre  = script.get("titre_scenario") or ("Scénario " + str(i + 1))
                lignes = script.get("lignes", [])

                with st.expander("**" + titre + "** — " + str(score) + "% confiance", expanded=(i == 0)):
                    if lignes:
                        for lg in lignes:
                            ts    = lg.get("timestamp", "")
                            texte = lg.get("texte_a_dire", "")
                            ecran = lg.get("texte_ecran", "")
                            st.markdown("**[" + ts + "]** " + texte)
                            if ecran:
                                st.caption("📺 Écran : " + ecran)
                    else:
                        st.info("Script non disponible pour ce hook.")
            st.divider()

        # ── B3 : Fiche de tournage ─────────────────────────────────────────────
        if plans:
            st.markdown("### 🎥 Fiche de tournage")
            for p in plans:
                num     = str(p.get("numero", "?")).zfill(2)
                ts      = p.get("timestamp", "")
                desc    = p.get("description_precise", "")
                lumiere = p.get("conseil_lumiere", "")
                camera  = p.get("conseil_camera", "")
                terrain = p.get("conseil_pratique", "")
                pourquoi_plan = p.get("pourquoi_ce_plan", "")
                try:
                    diff = int(p.get("difficulte", 1))
                except (ValueError, TypeError):
                    diff = 1

                with st.expander("Plan " + num + " · " + ts + " · " + desc[:55]):
                    if pourquoi_plan:
                        st.caption(pourquoi_plan)
                    pcols = st.columns(3)
                    with pcols[0]:
                        if lumiere:
                            st.markdown("☀️ **Lumière**")
                            st.markdown(lumiere)
                    with pcols[1]:
                        if camera:
                            st.markdown("📷 **Caméra**")
                            st.markdown(camera)
                    with pcols[2]:
                        if terrain:
                            st.markdown("💡 **Astuce terrain**")
                            st.markdown(terrain)
                    st.markdown("⭐ Difficulté : " + "★" * diff + "☆" * max(0, 5 - diff))
            st.divider()

        # ── Métriques ─────────────────────────────────────────────────────────
        tournage_m = brief.get("temps_tournage_minutes", "?")
        montage_m  = brief.get("temps_montage_minutes", "?")
        niv_global = brief.get("niveau_global", "?")
        publi      = brief.get("meilleur_moment_publication", "—")

        mcols = st.columns(4)
        with mcols[0]: st.metric("⏰ Tournage",     str(tournage_m) + " min")
        with mcols[1]: st.metric("🎬 Montage",      str(montage_m) + " min")
        with mcols[2]: st.metric("📊 Niveau",       niv_global)
        with mcols[3]: st.metric("📅 Publication",  publi or "—")

        # ── Avertissements ────────────────────────────────────────────────────
        for a in brief.get("avertissements", []):
            st.warning(a)

        # ── Extras pliables ───────────────────────────────────────────────────
        suggestions = brief.get("suggestions_bonus", [])
        if suggestions:
            with st.expander("💡 Suggestions bonus"):
                for s in suggestions:
                    st.markdown("• " + s)

        mots_ok  = brief.get("mots_cles_a_utiliser", [])
        mots_non = brief.get("mots_a_eviter", [])
        if mots_ok or mots_non:
            with st.expander("🔤 Mots clés"):
                if mots_ok:
                    st.markdown("**✅ À utiliser :** " + ", ".join(mots_ok))
                if mots_non:
                    st.markdown("**❌ À éviter :** " + ", ".join(mots_non))

        son = brief.get("son_tendance_conseil")
        if son:
            st.info("🎵 Son : " + son)

        st.divider()

        # ── Boutons d'action ──────────────────────────────────────────────────
        brief_text = _render_brief_text(brief, partenaire_disp, ville_disp, selected_idx)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("📋 Copier", use_container_width=True):
                st.code(brief_text, language="")
        with col_b:
            wa_preview   = brief_text[:500] + "..."
            wa_encoded   = wa_preview.replace(" ", "%20").replace("\n", "%0A")
            wa_url       = "https://wa.me/?text=" + wa_encoded
            st.link_button("📱 WhatsApp", url=wa_url, use_container_width=True)
        with col_c:
            st.button("💾 Sauvegardé ✓", disabled=True, use_container_width=True)

    elif not generate_btn:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#444;">
            <div style="font-size:3rem;">✨</div>
            <div>Remplis le formulaire et clique sur<br>
            <strong style="color:#FF4444;">⚡ GÉNÉRER EN 30s</strong></div>
        </div>
        """, unsafe_allow_html=True)
