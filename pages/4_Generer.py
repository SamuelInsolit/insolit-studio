import json
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Générer — Insolit Studio", page_icon="✨", layout="wide")


def _render_brief_text(brief: dict, partenaire: str, ville: str) -> str:
    """Formate le brief en texte lisible."""
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎬 BRIEF — {partenaire.upper()} {ville}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    duree = brief.get("duree_totale_estimee")
    if duree:
        lines.append(f"⏱ DURÉE : {duree}s")
        lines.append("")
    hook = brief.get("hook_suggere")
    if hook:
        lines.append(f"🎣 HOOK : \"{hook}\"")
        justif = brief.get("hook_justification", "")
        if justif:
            lines.append(f"   Basé sur : {justif}")
        lines.append("")
    script = brief.get("script_complet", [])
    if script:
        lines.append("📋 SCRIPT :")
        for s in script:
            ts = s.get("timestamp", "")
            texte = s.get("texte_a_dire", "")
            ecran = s.get("texte_ecran", "")
            lines.append(f"   [{ts}] \"{texte}\"")
            if ecran:
                lines.append(f"         Écran : {ecran}")
        lines.append("")
    plans = brief.get("plans", [])
    if plans:
        lines.append("🎥 PLANS :")
        for p in plans:
            num = str(p.get("numero", "?")).zfill(2)
            ts = p.get("timestamp", "")
            desc = p.get("description_precise", "")
            lumiere = p.get("conseil_lumiere", "")
            camera = p.get("conseil_camera", "")
            terrain = p.get("conseil_pratique", "")
            diff = "⭐" * int(p.get("difficulte", 1))
            lines.append(f"   {num} | {ts} | {desc}")
            if lumiere:
                lines.append(f"       Lumière : {lumiere}")
            if camera:
                lines.append(f"       Caméra  : {camera}")
            if terrain:
                lines.append(f"       Astuce  : {terrain}")
            lines.append(f"       Difficulté : {diff}")
        lines.append("")
    tournage = brief.get("temps_tournage_minutes")
    montage = brief.get("temps_montage_minutes")
    niveau = brief.get("niveau_global")
    if tournage or montage:
        lines.append(f"⏰ Tournage : {tournage}min | Montage : {montage}min")
        if niveau:
            lines.append(f"   Niveau : {niveau}")
        lines.append("")
    publi = brief.get("meilleur_moment_publication")
    if publi:
        lines.append(f"📅 Publier : {publi}")
        lines.append("")
    mots_ok = brief.get("mots_cles_a_utiliser", [])
    mots_non = brief.get("mots_a_eviter", [])
    if mots_ok:
        lines.append(f"✅ Mots qui marchent : {' '.join(chr(34)+m+chr(34) for m in mots_ok)}")
    if mots_non:
        lines.append(f"❌ À éviter : {' '.join(chr(34)+m+chr(34) for m in mots_non)}")
    if mots_ok or mots_non:
        lines.append("")
    suggestions = brief.get("suggestions_bonus", [])
    if suggestions:
        lines.append("💡 Suggestions bonus :")
        for s in suggestions:
            lines.append(f"   • {s}")
        lines.append("")
    son = brief.get("son_tendance_conseil")
    if son:
        lines.append(f"🎵 Son : {son}")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


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
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 style="color:#ff00a4;font-weight:900;">✨ Générer un brief</h1>', unsafe_allow_html=True)

from modules.database import get_precision_level, get_best_videos, get_session, Stats, Video, AnalyseCreative, AnalysePegasus
from modules.enrichment import get_precision_badge

nb_annotees, niveau = get_precision_level()
st.markdown(get_precision_badge(nb_annotees, niveau), unsafe_allow_html=True)

if nb_annotees < 5:
    manquantes = 5 - nb_annotees
    st.warning(f"⚠️ Il manque **{manquantes} vidéo{'s' if manquantes > 1 else ''}** annotées pour générer des briefs fiables.")
    st.info("Analyse et enrichis tes vidéos depuis la page **Analyser**.")
    st.stop()

# ─── Layout principal ─────────────────────────────────────────────────────────
col_form, col_result = st.columns([1, 2], gap="large")

with col_form:
    st.markdown("### 📝 Paramètres du brief")

    type_contenu = st.selectbox(
        "Type de partenaire",
        ["Restaurant", "Bar", "Café", "Food hall", "Dark kitchen", "Événement", "Autre"],
        key="brief_type"
    )
    partenaire = st.text_input("Nom du partenaire", placeholder="Ex: Chez Marcel", key="brief_partenaire")
    ville = st.text_input("Ville", placeholder="Ex: Paris 11e", key="brief_ville")
    offre = st.text_area(
        "Offre exacte à mettre en avant",
        placeholder="Ex: Menu déjeuner 3 plats à 18€ avec vin inclus",
        height=80,
        key="brief_offre"
    )
    objectif = st.selectbox(
        "Objectif",
        ["Awareness (faire connaître)", "Conversion (réservations)", "Engagement (likes/partages)", "Viralité"],
        key="brief_objectif"
    )

    duree = st.slider("Durée cible (secondes)", min_value=15, max_value=60, value=30, step=5, key="brief_duree")

    ton = st.selectbox(
        "Ton",
        ["Authentique / spontané", "Enthousiaste / énergie", "Informatif / factuel",
         "Humour / décalé", "Lifestyle / aspirationnel"],
        key="brief_ton"
    )

    source_filter = st.radio(
        "Basé sur",
        ["Mes meilleures vidéos", "Vidéos de concurrents", "Toute la base"],
        horizontal=True,
        key="brief_source"
    )
    source_map = {
        "Mes meilleures vidéos": "mon_compte",
        "Vidéos de concurrents": "concurrent",
        "Toute la base": "all"
    }

    generate_btn = st.button("⚡ GÉNÉRER EN 30s", use_container_width=True, type="primary")

with col_result:
    st.markdown("### 🎬 Brief généré")

    if generate_btn:
        if not partenaire or not offre:
            st.error("Remplis au minimum le nom du partenaire et l'offre.")
            st.stop()

        # Chargement des meilleures vidéos
        filter_key = source_map.get(source_filter, "all")
        best_vids = get_best_videos(source_filter=filter_key, limit=5)

        session = get_session()
        try:
            best_for_claude = []
            for v in best_vids:
                item = {
                    "titre": v.titre,
                    "duree_secondes": v.duree_secondes,
                    "nom_compte": v.nom_compte,
                    "categorie": v.categorie,
                }
                if v.stats:
                    item["vues"] = v.stats.vues
                    item["performance_tag"] = v.stats.performance_tag
                    item["completion_rate"] = v.stats.completion_rate
                if v.analyse_creative:
                    item["hook_texte"] = v.analyse_creative.hook_texte
                    item["hook_type"] = v.analyse_creative.hook_type
                    item["hook_score"] = v.analyse_creative.hook_score
                    item["script_adapte"] = v.analyse_creative.note_adaptation
                if v.analyse_pegasus:
                    item["nb_plans"] = v.analyse_pegasus.nb_plans
                    item["rythme"] = v.analyse_pegasus.rythme_coupes_par_seconde
                best_for_claude.append(item)
        finally:
            session.close()

        # Patterns simples
        patterns = {
            "nb_videos_base": nb_annotees,
            "source_filter": source_filter,
            "top_videos_count": len(best_for_claude),
        }

        from modules.claude_mod import generate_brief as gen_brief
        from modules.database import Brief, Ressource

        # Charge la base de connaissances
        kb_session = get_session()
        knowledge_base = []
        try:
            kb_items = kb_session.query(Ressource).order_by(Ressource.created_at.desc()).all()
            for r in kb_items:
                knowledge_base.append({
                    "type_ressource":     r.type_ressource,
                    "titre":              r.titre,
                    "contenu":            r.contenu,
                    "performance_tag":    r.performance_tag,
                    "vues_approx":        r.vues_approx,
                    "nb_likes":           getattr(r, "nb_likes", None),
                    "nb_commentaires":    getattr(r, "nb_commentaires", None),
                    "nb_partages":        getattr(r, "nb_partages", None),
                    "nb_enregistrements": getattr(r, "nb_enregistrements", None),
                    "taux_completion":    getattr(r, "taux_completion", None),
                    "hook_texte":         getattr(r, "hook_texte", None),
                    "ce_qui_marche":      getattr(r, "ce_qui_marche", None),
                    "a_reproduire":       getattr(r, "a_reproduire", None),
                })
        finally:
            kb_session.close()

        with st.spinner(f"Claude génère ton brief{'  (+ ' + str(len(knowledge_base)) + ' ressources KB)' if knowledge_base else ''}..."):
            brief_data, usage = gen_brief(
                type_contenu=type_contenu,
                partenaire=partenaire,
                ville=ville,
                offre=offre,
                objectif=objectif,
                duree=duree,
                ton=ton,
                best_videos=best_for_claude,
                patterns=patterns,
                knowledge_base=knowledge_base if knowledge_base else None,
            )

        if "_error" in brief_data:
            st.error(f"Erreur: {brief_data.get('_error')}")
            if brief_data.get("_raw"):
                st.text_area("Réponse brute", brief_data["_raw"], height=300)
            st.stop()

        # Sauvegarde en DB
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
                hook_suggere=brief_data.get("hook_suggere"),
                script_complet=json.dumps(brief_data.get("script_complet", []), ensure_ascii=False),
                plans_json=json.dumps(brief_data.get("plans", []), ensure_ascii=False),
                niveau_difficulte=brief_data.get("niveau_global"),
                temps_tournage_estime=brief_data.get("temps_tournage_minutes"),
                temps_montage_estime=brief_data.get("temps_montage_minutes"),
                suggestions=json.dumps(brief_data.get("suggestions_bonus", []), ensure_ascii=False),
            )
            session.add(brief_db)
            session.commit()
        finally:
            session.close()

        st.session_state["last_brief"] = brief_data
        st.session_state["last_brief_meta"] = {
            "partenaire": partenaire, "ville": ville, "cout": usage.get("cout_estime", 0)
        }

        if usage:
            st.caption(f"Généré en ~30s | Coût estimé : ~${usage.get('cout_estime', 0):.4f}")

    # ─── Affichage brief ──────────────────────────────────────────────────────
    if "last_brief" in st.session_state:
        brief = st.session_state["last_brief"]
        meta = st.session_state.get("last_brief_meta", {})
        partenaire_disp = meta.get("partenaire", "—")
        ville_disp = meta.get("ville", "")

        brief_text = _render_brief_text(brief, partenaire_disp, ville_disp)

        st.markdown(f"""
        <div class="brief-box">
            <pre style="white-space:pre-wrap;color:#f0f0f0;font-size:0.85rem;line-height:1.6;">{brief_text}</pre>
        </div>
        """, unsafe_allow_html=True)

        # Boutons d'action
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("📋 Copier", use_container_width=True):
                st.code(brief_text, language="")
        with col_b:
            wa_text = f"🎬 Brief Insolit — {partenaire_disp}\n\n{brief_text[:500]}..."
            wa_url = f"https://wa.me/?text={wa_text.replace(' ', '%20').replace('\n', '%0A')}"
            st.link_button("📱 WhatsApp", url=wa_url, use_container_width=True)
        with col_c:
            if st.button("💾 Sauvegardé ✓", disabled=True, use_container_width=True):
                pass

    elif not generate_btn:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#444;">
            <div style="font-size:3rem;">✨</div>
            <div>Remplis le formulaire et clique sur<br><strong style="color:#FF4444;">⚡ GÉNÉRER EN 30s</strong></div>
        </div>
        """, unsafe_allow_html=True)


