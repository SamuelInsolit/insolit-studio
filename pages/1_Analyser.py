import json
import os
import time
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Analyser — Insolit Studio", page_icon="🎬", layout="wide")

from modules.styles import apply_styles
apply_styles()

st.markdown('<h1 style="color:#ff00a4;font-weight:900;">🎬 Analyser une vidéo</h1>', unsafe_allow_html=True)

# ─── Section A — Input ────────────────────────────────────────────────────────
tab_upload, tab_url = st.tabs(["📱 Upload fichier", "🔗 Lien TikTok/Instagram"])

with tab_upload:
    uploaded_file = st.file_uploader(
        "Glisse ta vidéo ici",
        type=["mp4", "mov", "avi", "mkv"],
        key="video_upload"
    )

with tab_url:
    video_url = st.text_input(
        "URL TikTok / Instagram / YouTube",
        placeholder="https://www.tiktok.com/@compte/video/...",
        key="video_url"
    )

# ─── Section B — Contexte ─────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Contexte")

col1, col2 = st.columns(2)
with col1:
    type_source = st.selectbox(
        "Type de vidéo",
        ["Mon compte", "Concurrent", "Inspiration", "Secteur"],
        key="type_source"
    )
    type_map = {
        "Mon compte": "mon_compte",
        "Concurrent": "concurrent",
        "Inspiration": "inspiration",
        "Secteur": "secteur"
    }

    categorie = st.selectbox(
        "Catégorie",
        ["Restaurant", "Bar", "Café", "Expérience", "Bon plan", "Tendance food",
         "Lifestyle", "Voyage IDF", "Autre"],
        key="categorie"
    )

with col2:
    nom_compte = st.text_input("Compte source (@...)", placeholder="@nomducompte", key="nom_compte")
    partenaire = st.text_input("Partenaire / Lieu (optionnel)", placeholder="Ex: Chez Marcel, Paris 11e", key="partenaire")
    ville = st.text_input("Ville", placeholder="Ex: Paris", key="ville")

# ─── Bouton Analyser ──────────────────────────────────────────────────────────
st.markdown("---")
launch_analysis = st.button("🔍 ANALYSER", use_container_width=True, type="primary")

if launch_analysis:
    has_url = bool(video_url and video_url.strip())
    has_file = uploaded_file is not None

    if not has_url and not has_file:
        st.error("Fournis une URL ou un fichier vidéo.")
        st.stop()

    # ─── Section C — Progression ──────────────────────────────────────────────
    st.markdown("---")

    # Container principal de progression
    progress_container = st.container()
    with progress_container:
        progress_bar = st.progress(0)
        col_status, col_timer = st.columns([4, 1])
        with col_status:
            status_placeholder = st.empty()
        with col_timer:
            timer_placeholder = st.empty()

    steps_container = st.empty()

    STEPS = [
        ("⬇️", "Récupération vidéo", 8),
        ("🎬", "Analyse Pegasus + Transcription", 65),
        ("🔍", "Similarités (Marengo)", 75),
        ("🧠", "Analyse créative (Claude)", 90),
        ("📸", "Screenshots", 97),
        ("✅", "Finalisation", 100),
    ]

    steps_state = ["pending"] * len(STEPS)
    current_step_idx = [0]
    start_ts = [time.time()]

    import time as _time

    def _render_steps():
        lines = []
        for i, (icon, label, pct) in enumerate(STEPS):
            state = steps_state[i]
            if state == "done":
                lines.append(f"✅ ~~{label}~~")
            elif state == "running":
                lines.append(f"⏳ **{icon} {label}**")
            else:
                lines.append(f"⬜ {label}")
        steps_container.markdown("  \n".join(lines))

    def update_progress(msg: str):
        # Déterminer l'étape courante selon le message
        msg_low = msg.lower()
        if any(k in msg_low for k in ["récupér", "télécharg", "initialisation", "upload"]):
            idx = 0
        elif any(k in msg_low for k in ["pegasus", "whisper", "transcri", "plan", "parallèle", "indexation", "analyse"]):
            idx = 1
        elif any(k in msg_low for k in ["marengo", "similaire", "embedding"]):
            idx = 2
        elif any(k in msg_low for k in ["claude", "créative", "créatif"]):
            idx = 3
        elif any(k in msg_low for k in ["screenshot", "frame", "capture"]):
            idx = 4
        elif any(k in msg_low for k in ["terminé", "finali", "✅"]):
            idx = 5
        else:
            idx = current_step_idx[0]

        # Marque les étapes précédentes comme done
        for i in range(idx):
            steps_state[i] = "done"
        steps_state[idx] = "running"
        current_step_idx[0] = idx

        # Calcul du % de progression
        target_pct = STEPS[idx][2]
        prev_pct = STEPS[idx - 1][2] if idx > 0 else 0
        pct = min(target_pct, max(prev_pct, target_pct - 5))
        progress_bar.progress(pct)

        # Status
        status_placeholder.markdown(f"**{msg}**")

        # Timer
        elapsed = int(_time.time() - start_ts[0])
        m, s = divmod(elapsed, 60)
        timer_placeholder.markdown(f"⏱️ **{m}:{s:02d}**")

        # Steps visual
        _render_steps()

    _render_steps()

    from modules.analyzer import analyze_video

    metadata = {
        "type_source": type_map.get(type_source, "inspiration"),
        "nom_compte": nom_compte,
        "categorie": categorie,
        "partenaire": partenaire,
        "ville": ville,
    }

    with st.spinner("Analyse en cours..."):
        if has_url:
            result = analyze_video(
                source=video_url.strip(),
                metadata=metadata,
                progress_callback=update_progress,
                is_url=True,
            )
        else:
            file_bytes = uploaded_file.read()
            result = analyze_video(
                source=uploaded_file.name,
                metadata=metadata,
                progress_callback=update_progress,
                is_url=False,
                file_bytes=file_bytes,
                filename=uploaded_file.name,
            )

    progress_bar.progress(100)

    # Mark all steps done
    for i in range(len(STEPS)):
        steps_state[i] = "done"
    _render_steps()
    elapsed_total = int(_time.time() - start_ts[0])
    m, s = divmod(elapsed_total, 60)
    timer_placeholder.markdown(f"⏱️ **{m}:{s:02d}** total")

    if not result.get("success"):
        st.error(f"Erreur lors de l'analyse : {result.get('error')}")
        st.stop()

    # Sauvegarde en session pour affichage
    st.session_state["last_analysis"] = result
    status_placeholder.success(
        f"✅ Terminé en {result.get('elapsed', '?')}s | Coût estimé : ~${result.get('cout_total', 0):.4f}"
    )

# ─── Section D — Résultats ────────────────────────────────────────────────────
if "last_analysis" in st.session_state:
    result = st.session_state["last_analysis"]
    pegasus = result.get("pegasus_data", {})
    whisper = result.get("whisper_data", {})
    creative = result.get("creative_data", {})
    similar = result.get("similar_videos", [])
    hook = pegasus.get("hook_analyse", {})
    metriques = pegasus.get("metriques_globales", {})
    plans = pegasus.get("plans", [])

    st.markdown("---")
    st.markdown(f"## 📋 {result.get('titre', 'Résultats')}")

    # ── BLOC 1 — Rapport exécutif ─────────────────────────────────────────────
    with st.container():
        st.markdown("### 📊 Rapport exécutif")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Durée", f"{result.get('duree_secondes', 0):.0f}s")
        with col2:
            st.metric("Plans", result.get("plans_count", 0))
        with col3:
            rythme = metriques.get("rythme_coupes_par_seconde", 0)
            st.metric("Rythme", f"{rythme} c/s")
        with col4:
            score = creative.get("score_potentiel", 5)
            st.metric("Score potentiel", f"{score}/10")

        # Hook
        hook_texte = hook.get("texte_dit") or creative.get("hook_texte", "")
        hook_type = hook.get("type_hook") or creative.get("hook_type", "")
        hook_score = hook.get("score_accroche") or creative.get("hook_score", 5)
        if hook_texte:
            st.markdown(f"""
            <div class="card card-pink">
                <strong>🎣 Hook :</strong> «{hook_texte}»<br>
                <span style="color:#01f0fc;">Type : {hook_type}</span> &nbsp;|&nbsp;
                <span style="color:#ff00a4;">Score : {hook_score}/10</span>
            </div>
            """, unsafe_allow_html=True)

        # Points forts / faibles
        pf = creative.get("points_forts", [])
        ppf = creative.get("points_faibles", [])
        recos = creative.get("recommandations", [])
        if isinstance(pf, str):
            pf = json.loads(pf) if pf.startswith("[") else [pf]
        if isinstance(ppf, str):
            ppf = json.loads(ppf) if ppf.startswith("[") else [ppf]
        if isinstance(recos, str):
            recos = json.loads(recos) if recos.startswith("[") else [recos]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**✅ Ce qui marche**")
            for pt in (pf[:3] if pf else ["—"]):
                st.markdown(f"- {pt}")
        with col_b:
            st.markdown("**⚠️ Ce qui pénalise**")
            for pt in (ppf[:2] if ppf else ["—"]):
                st.markdown(f"- {pt}")
        with col_c:
            st.markdown("**💡 Recommandations**")
            for r in (recos[:3] if recos else ["—"]):
                st.markdown(f"- {r}")

    # ── BLOC 2 — Comparaison base ─────────────────────────────────────────────
    if similar:
        st.markdown("### 🔍 Vidéos similaires dans ta base")
        for s in similar[:3]:
            with st.container():
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.markdown(f"**{s.get('titre', 'Sans titre')}**")
                with c2:
                    vues = s.get("vues")
                    st.markdown(f"👁 {vues:,}" if vues else "👁 —")
                with c3:
                    st.markdown(f"Similarité : **{s.get('similarite', 0):.0f}%**")

        comparaison = creative.get("comparaison_base", "")
        if comparaison:
            st.info(comparaison)

    # ── BLOC 3 — Timeline des plans ───────────────────────────────────────────
    if plans:
        st.markdown("### 🎬 Timeline des plans")
        for i, plan in enumerate(plans):
            with st.expander(
                f"Plan {i+1} | {plan.get('timestamp_debut', 0):.1f}s–{plan.get('timestamp_fin', 0):.1f}s | {plan.get('type_plan', '')}",
                expanded=i == 0
            ):
                # Screenshot si disponible
                screenshot_path = None
                screenshots_dir = os.path.join("./screenshots", str(result.get("video_id", "")))
                shot_file = os.path.join(screenshots_dir, f"plan_{i+1:02d}.jpg")
                if os.path.exists(shot_file):
                    st.image(shot_file, width=300)

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Sujet :** {plan.get('sujet_principal', '—')}")
                    st.markdown(f"**Lumière :** ⭐ {plan.get('luminosite', '?')}/10 ({plan.get('type_lumiere', '')})")
                    st.markdown(f"**Mouvement :** {plan.get('mouvement_camera', '—')}")
                    st.markdown(f"**Rôle :** {plan.get('role_narratif', '—')}")
                with col_b:
                    st.markdown(f"**Émotion :** {plan.get('emotion_transmise', '—')}")
                    texte = plan.get("texte_visible_ecran")
                    if texte:
                        st.markdown(f"**Texte écran :** «{texte}»")
                    pf = plan.get("points_forts", [])
                    if pf:
                        st.markdown(f"**Points forts :** {', '.join(pf) if isinstance(pf, list) else pf}")
                    sug = plan.get("suggestion_amelioration")
                    if sug:
                        st.caption(f"💡 {sug}")

    # ── BLOC 4 — Hook détaillé ────────────────────────────────────────────────
    st.markdown("### 🎣 Hook détaillé")
    with st.container():
        col_a, col_b = st.columns([1, 2])
        with col_a:
            shot_0 = os.path.join("./screenshots", str(result.get("video_id", "")), "plan_01.jpg")
            if os.path.exists(shot_0):
                st.image(shot_0, caption="Plan 1 (hook)")
        with col_b:
            st.markdown(f"**Texte dit :** {hook.get('texte_dit', '—')}")
            st.markdown(f"**Texte visible :** {hook.get('texte_visible', '—')}")
            st.markdown(f"**Type :** {hook.get('type_hook', '—')}")
            st.markdown(f"**Score :** {hook.get('score_accroche', '?')}/10")
            st.markdown(f"**Ce qui accroche :** {hook.get('ce_qui_accroche', '—')}")
            manque = hook.get("ce_qui_manque")
            if manque:
                st.warning(f"**Ce qui manque :** {manque}")

    # ── BLOC 5 — Script mot par mot ───────────────────────────────────────────
    mots = whisper.get("mots", [])
    if mots:
        st.markdown("### 📝 Script mot par mot")
        from modules.whisper_mod import format_transcript_display
        transcript_text = format_transcript_display(mots)
        st.text_area(
            f"Débit : {whisper.get('debit_parole', 0)} mots/s | {whisper.get('nb_mots', 0)} mots",
            transcript_text,
            height=200,
            key="transcript_display"
        )
        if st.button("📋 Copier la transcription"):
            st.code(transcript_text)

    # ── BLOC 6 — Adaptation Insolit ───────────────────────────────────────────
    if creative.get("adaptable_insolit") is not False:
        st.markdown("### 🎯 Adaptation Insolit")
        script_adapte = creative.get("script_adapte", "")
        if script_adapte:
            st.markdown(f"""
            <div class="card" style="border-left:4px solid #FF4444;">
                <strong>Script adapté :</strong><br>
                <em>{script_adapte}</em>
            </div>
            """, unsafe_allow_html=True)

        plans_reproduire = creative.get("plans_a_reproduire", [])
        changements = creative.get("ce_qui_change", [])
        if isinstance(plans_reproduire, str):
            plans_reproduire = json.loads(plans_reproduire) if plans_reproduire.startswith("[") else [plans_reproduire]
        if isinstance(changements, str):
            changements = json.loads(changements) if changements.startswith("[") else [changements]

        col_a, col_b = st.columns(2)
        with col_a:
            if plans_reproduire:
                st.markdown("**Plans à reproduire :**")
                for p in plans_reproduire:
                    st.markdown(f"✅ {p}")
        with col_b:
            if changements:
                st.markdown("**Ce qui change :**")
                for c in changements:
                    st.markdown(f"↔️ {c}")

    # ── BLOC 7 — Enrichissement ───────────────────────────────────────────────
    st.markdown("---")
    from modules.enrichment import render_enrichment_form
    from modules.database import get_session, Stats

    video_id = result.get("video_id")
    if video_id:
        session = get_session()
        existing = session.query(Stats).filter_by(video_id=video_id).first()
        existing_dict = {
            "performance_tag": existing.performance_tag,
            "vues": existing.vues,
            "completion_rate": existing.completion_rate,
            "note_humaine": existing.note_humaine,
        } if existing else None
        session.close()
        render_enrichment_form(video_id, existing_dict)

    # ── Actions ───────────────────────────────────────────────────────────────
    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 Sauvegardé ✓", disabled=True, use_container_width=True):
            pass
    with col_b:
        if st.button("🎯 Générer un brief basé sur cette vidéo", use_container_width=True):
            st.session_state["brief_from_video_id"] = video_id
            st.switch_page("pages/4_Generer.py")
