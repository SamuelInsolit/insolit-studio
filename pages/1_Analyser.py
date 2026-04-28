import json
import os
import time
import threading
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
    type_map = {"Mon compte": "mon_compte", "Concurrent": "concurrent",
                "Inspiration": "inspiration", "Secteur": "secteur"}

    categorie = st.selectbox(
        "Catégorie",
        ["Restaurant", "Bar", "Café", "Expérience", "Bon plan", "Tendance food",
         "Lifestyle", "Voyage IDF", "Autre"],
        key="categorie"
    )
    type_offre = st.selectbox(
        "Type d'offre",
        ["Non spécifié", "Prix choc", "Exclusivité", "Nouveauté", "Événement limité",
         "Découverte", "Comparaison", "Gratuit / Offert", "Autre"],
        key="type_offre"
    )

with col2:
    nom_compte = st.text_input("Compte source (@...)", placeholder="@nomducompte", key="nom_compte")
    partenaire = st.text_input("Partenaire / Lieu (optionnel)", placeholder="Ex: Chez Marcel, Paris 11e", key="partenaire")
    ville = st.text_input("Ville", placeholder="Ex: Paris", key="ville")

# ─── Options d'analyse ────────────────────────────────────────────────────────
st.markdown("---")
col_mode, col_btn = st.columns([2, 3])
with col_mode:
    mode_rapide = st.toggle(
        "⚡ Mode rapide",
        value=False,
        help="Mode rapide : 5 frames au lieu de 12, pas de retry. 2× plus vite, ~40% moins cher. Recommandé pour trier rapidement.",
        key="mode_rapide_toggle"
    )
    if mode_rapide:
        st.caption("⚡ Rapide : ~20s · moins précis")
    else:
        st.caption("🔬 Complet : ~40s · analyse maximale")

with col_btn:
    launch_analysis = st.button("🔍 ANALYSER", use_container_width=True, type="primary")

if launch_analysis:
    has_url  = bool(video_url and video_url.strip())
    has_file = uploaded_file is not None

    if not has_url and not has_file:
        st.error("Fournis une URL ou un fichier vidéo.")
        st.stop()

    # ── Opt 1 — Anti-doublons ────────────────────────────────────────────────
    if has_url:
        from modules.database import get_session, Video as _Video
        _dup_session = get_session()
        try:
            _existing = _dup_session.query(_Video).filter_by(url_source=video_url.strip()).first()
        finally:
            _dup_session.close()

        if _existing:
            st.warning(
                f"⚠️ **Cette URL a déjà été analysée** (vidéo #{_existing.id} — "
                f"*{(_existing.titre or 'Sans titre')[:50]}*)  \n"
                "Tu peux la retrouver dans ta **📚 Bibliothèque**."
            )
            col_force, col_cancel = st.columns(2)
            with col_force:
                force_reanalyze = st.button("🔄 Ré-analyser quand même", key="force_reanalyze")
            with col_cancel:
                if st.button("📚 Voir dans la bibliothèque", key="goto_biblio"):
                    st.switch_page("pages/2_Bibliotheque.py")
            if not force_reanalyze:
                st.stop()

    # Lecture fichier AVANT le thread (Streamlit exige ça)
    file_bytes = uploaded_file.read() if has_file else None
    file_size  = len(file_bytes) if file_bytes else 0
    file_name  = uploaded_file.name if has_file else None
    size_mb    = file_size / 1024 / 1024 if file_size else 5

    # Estimation temps basée sur taille du fichier
    estimated_s = int(25 + size_mb * 0.8)
    estimated_s = max(25, min(90, estimated_s))

    # ─── Section C — Progression ─────────────────────────────────────────────
    st.markdown("---")

    st.markdown(f"""
    <div style="background:#0a0a0a;border:1px solid #222;border-left:4px solid #ff00a4;
                border-radius:10px;padding:1rem 1.4rem;margin-bottom:1rem;">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
            <span style="color:#ff00a4;font-weight:700;font-size:0.9em;">⚡ ANALYSE EN COURS</span>
            <span style="color:#888;font-size:0.8em;">{'📁 ' + f'{size_mb:.1f} MB' if file_size else '🔗 URL'}</span>
        </div>
        <div style="color:#888;font-size:0.82em;">
            Vision + Whisper en parallèle &nbsp;·&nbsp;
            Durée estimée : <strong style="color:#01f0fc;">{estimated_s}–{estimated_s+20}s</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

    progress_bar = st.progress(0.0)
    col_s, col_t = st.columns([5, 1])
    with col_s:
        status_ph = st.empty()
    with col_t:
        timer_ph = st.empty()
    steps_ph = st.empty()

    # Timeline des étapes (t0, t1, icon, label)
    TIMELINE = [
        (0,   6,  "⬇️",  "Acquisition vidéo"),
        (6,   13, "🗜️",  "Compression"),
        (13,  18, "📸",  "Détection des plans"),
        (18,  38, "🎬",  "Vision + Transcription Whisper"),
        (38,  50, "🧠",  "Analyse créative Claude"),
        (50,  55, "📸",  "Screenshots"),
        (55,  60, "✅",  "Finalisation"),
    ]

    def _steps_html(elapsed: float) -> str:
        parts = []
        for (t0, t1, icon, label) in TIMELINE:
            if elapsed >= t1:
                style = "color:#555;text-decoration:line-through;"
                mark = "✅"
            elif elapsed >= t0:
                style = "color:#ff00a4;font-weight:700;"
                mark = "⏳"
            else:
                style = "color:#444;"
                mark = "⬜"
            parts.append(f'<span style="{style}">{mark} {icon} {label}</span>')
        return ' &nbsp;·&nbsp; '.join(parts)

    # ─── Lancement analyse en thread de fond ──────────────────────────────────
    result_holder = {"result": None, "error": None}
    metadata = {
        "type_source": type_map.get(type_source, "inspiration"),
        "nom_compte": nom_compte,
        "categorie": categorie,
        "partenaire": partenaire,
        "ville": ville,
        "type_offre": type_offre,
    }

    from modules.analyzer import analyze_video

    _quick_mode = st.session_state.get("mode_rapide_toggle", False)

    def _run_analysis():
        try:
            if has_url:
                result_holder["result"] = analyze_video(
                    source=video_url.strip(), metadata=metadata,
                    progress_callback=None, is_url=True,
                    quick_mode=_quick_mode,
                )
            else:
                result_holder["result"] = analyze_video(
                    source=file_name, metadata=metadata,
                    progress_callback=None, is_url=False,
                    file_bytes=file_bytes, filename=file_name,
                    file_size_bytes=file_size,
                    quick_mode=_quick_mode,
                )
        except Exception as e:
            result_holder["error"] = str(e)

    analysis_thread = threading.Thread(target=_run_analysis, daemon=True)
    analysis_thread.start()
    start_ts = time.time()

    # ─── BOUCLE DE POLLING — UI mise à jour chaque seconde ───────────────────
    while analysis_thread.is_alive():
        elapsed = time.time() - start_ts

        # Barre de progression (linéaire jusqu'à 95%)
        pct = min(0.95, elapsed / max(estimated_s, 30))
        progress_bar.progress(pct)

        # Étape courante
        current_icon, current_label = "🔄", "En cours..."
        for (t0, t1, icon, label) in TIMELINE:
            if t0 <= elapsed < t1 + 8:
                current_icon, current_label = icon, label
                break

        status_ph.markdown(f"**{current_icon} {current_label}...**")

        # Timer + estimation restante
        m, s   = divmod(int(elapsed), 60)
        remain = max(0, estimated_s - int(elapsed))
        rm, rs = divmod(remain, 60)
        rest_str = f" | ~{rm}:{rs:02d} restant" if remain > 3 else ""
        timer_ph.markdown(f"⏱️ **{m}:{s:02d}**{rest_str}")

        # Steps visuels
        steps_ph.markdown(
            f'<div style="font-size:0.78em;line-height:2.2;padding:4px 0;">{_steps_html(elapsed)}</div>',
            unsafe_allow_html=True,
        )

        time.sleep(1)  # Polling chaque seconde

    analysis_thread.join()

    # Finalisation UI
    progress_bar.progress(1.0)
    status_ph.empty()
    timer_ph.empty()
    steps_ph.empty()

    elapsed_total = round(time.time() - start_ts)

    if result_holder["error"]:
        st.error(f"Erreur : {result_holder['error']}")
        st.stop()

    result = result_holder["result"]
    if not result or not result.get("success"):
        err = result.get("error", "Erreur inconnue") if result else "Pas de résultat"
        st.error(f"Erreur : {err}")
        st.stop()

    st.session_state["last_analysis"] = result
    st.session_state["last_analysis_meta"] = metadata  # pour KB matching
    m, s = divmod(elapsed_total, 60)
    cout = result.get("cout_total", 0)
    st.success(
        f"✅ Analysé en **{m}:{s:02d}** "
        f"| {result.get('plans_count', 0)} plans détectés "
        f"| Coût ~${cout:.4f}"
    )

# ─── Section D — Résultats ────────────────────────────────────────────────────
if "last_analysis" in st.session_state:
    result    = st.session_state["last_analysis"]
    pegasus   = result.get("pegasus_data", {})
    whisper   = result.get("whisper_data", {})
    creative  = result.get("creative_data", {})
    similar   = result.get("similar_videos", [])
    hook      = pegasus.get("hook_analyse", {})
    metriques = pegasus.get("metriques_globales", {})
    plans     = pegasus.get("plans", [])

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

        hook_texte = hook.get("texte_dit") or creative.get("hook_texte", "")
        hook_type  = hook.get("type_hook")  or creative.get("hook_type", "")
        hook_score = hook.get("score_accroche") or creative.get("hook_score", 5)
        if hook_texte:
            st.markdown(f"""
            <div class="card card-pink">
                <strong>🎣 Hook :</strong> «{hook_texte}»<br>
                <span style="color:#01f0fc;">Type : {hook_type}</span> &nbsp;|&nbsp;
                <span style="color:#ff00a4;">Score : {hook_score}/10</span>
            </div>
            """, unsafe_allow_html=True)

        pf    = creative.get("points_forts", [])
        ppf   = creative.get("points_faibles", [])
        recos = creative.get("recommandations", [])
        for lst in [pf, ppf, recos]:
            pass  # Already lists from JSON
        if isinstance(pf,    str): pf    = json.loads(pf)    if pf.startswith("[")    else [pf]
        if isinstance(ppf,   str): ppf   = json.loads(ppf)   if ppf.startswith("[")   else [ppf]
        if isinstance(recos, str): recos = json.loads(recos)  if recos.startswith("[") else [recos]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**✅ Ce qui marche**")
            for pt in (pf[:3] if pf else ["—"]): st.markdown(f"- {pt}")
        with col_b:
            st.markdown("**⚠️ Ce qui pénalise**")
            for pt in (ppf[:2] if ppf else ["—"]): st.markdown(f"- {pt}")
        with col_c:
            st.markdown("**💡 Recommandations**")
            for r in (recos[:3] if recos else ["—"]): st.markdown(f"- {r}")

    # ── BLOC 1b — Scoring avec référentiel personnel ──────────────────────────
    score_val = creative.get("score_potentiel")
    if score_val:
        from modules.database import get_scoring_referentiel
        ref = get_scoring_referentiel()
        nb_ann = ref.get("nb_annotees", 0)

        if nb_ann >= 5:
            # Déterminer où se situe la vidéo
            viral_avg = ref.get("viral")
            bon_avg   = ref.get("bon")
            moyen_avg = ref.get("moyen")

            position = ""
            action   = ""
            pos_color = "#888"
            try:
                sv = float(score_val)
                if viral_avg and sv >= viral_avg:
                    position = "Au niveau de tes vidéos **virales** 🔥"
                    pos_color = "#ff00a4"
                    action = "Déjà au top — optimise la distribution (heure de post, hashtags)"
                elif bon_avg and sv >= bon_avg:
                    position = "Entre **bonne** et **virale**"
                    pos_color = "#01f0fc"
                    action = creative.get("recommandations", ["Améliore le hook"])[0] if creative.get("recommandations") else "Renforce le hook"
                elif moyen_avg and sv >= moyen_avg:
                    position = "Entre **moyenne** et **bonne**"
                    pos_color = "#f59e0b"
                    action = creative.get("recommandations", ["Travaille le hook"])[0] if creative.get("recommandations") else "Travaille le hook"
                else:
                    position = "En dessous de tes vidéos **moyennes**"
                    pos_color = "#ef4444"
                    action = creative.get("recommandations", ["Refonte complète nécessaire"])[0] if creative.get("recommandations") else "Refonte complète"
            except Exception:
                pass

            ref_lines = []
            if viral_avg: ref_lines.append(f"🔥 Virales : <strong>{viral_avg}</strong> moy.")
            if bon_avg:   ref_lines.append(f"✅ Bonnes : <strong>{bon_avg}</strong> moy.")
            if moyen_avg: ref_lines.append(f"😐 Moyennes : <strong>{moyen_avg}</strong> moy.")

            st.markdown(f"""
            <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-radius:12px;
                        padding:1rem 1.4rem;margin:1rem 0;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
                    <div>
                        <div style="font-size:0.8em;color:#888;margin-bottom:4px;">SCORE POTENTIEL</div>
                        <div style="font-size:2.2em;font-weight:900;color:#ff00a4;">{score_val}/10</div>
                        <div style="margin-top:6px;font-size:0.85em;color:{pos_color};">{position}</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:0.78em;color:#666;margin-bottom:6px;">RÉFÉRENTIEL INSOLIT ({nb_ann} vidéos)</div>
                        {"".join(f'<div style="font-size:0.82em;color:#aaa;">{l}</div>' for l in ref_lines)}
                    </div>
                </div>
                {f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #1a1a1a;font-size:0.85em;color:#01f0fc;">→ Pour passer à 8+ : <strong>{action}</strong></div>' if action else ''}
            </div>
            """, unsafe_allow_html=True)
        else:
            needed = 5 - nb_ann
            st.caption(f"📊 Référentiel insuffisant — annote **{needed} vidéo(s) de plus** dans Enrichir pour activer le scoring contextualisé.")

    # ── BLOC 1c — Base de Connaissances — ressources similaires ───────────────
    hook_type_val = hook.get("type_hook") or creative.get("hook_type", "")
    hook_text_val = hook.get("texte_dit") or creative.get("hook_texte", "")
    categorie_val = result.get("metadata_categorie", "") or ""  # récupéré via session_state si dispo

    # Récupérer la catégorie depuis le résultat (stockée dans le titre ou les métadonnées)
    # On utilise st.session_state pour passer la catégorie choisie lors de l'analyse
    if "last_analysis_meta" in st.session_state:
        categorie_val = st.session_state["last_analysis_meta"].get("categorie", "")

    from modules.database import find_matching_kb_resources
    # Clé de cache : (video_id, hook_type, hook_text) — évite re-appel API sur chaque rerender
    _kb_cache_key = f"kb_matches_{result.get('video_id','?')}_{hook_type_val}_{hook_text_val[:30]}"
    if _kb_cache_key not in st.session_state:
        with st.spinner("📚 Recherche dans ta base de connaissances..."):
            st.session_state[_kb_cache_key] = find_matching_kb_resources(
                hook_type=hook_type_val,
                categorie=categorie_val,
                hook_texte=hook_text_val,
                limit=3,
            )
    kb_matches = st.session_state[_kb_cache_key]

    if kb_matches:
        st.markdown("### 📚 Ta Base de Connaissances dit...")

        from modules.claude_mod import compare_video_to_kb_resource

        for match in kb_matches:
            perf = match.get("performance_tag", "")
            vues = match.get("vues_approx")
            vues_str = f"{vues:,} vues" if vues else "vues inconnues"

            # Couleur et icône selon performance
            if perf == "viral":
                border_color = "#00cc66"
                badge = "🔥 Ce format a déjà prouvé sa performance dans ta base"
                badge_color = "#00cc66"
                badge_bg    = "#001a0a"
            elif perf in ("mauvais",):
                border_color = "#f59e0b"
                badge = "⚠️ Attention : un contenu similaire n'a pas performé"
                badge_color = "#f59e0b"
                badge_bg    = "#1a1000"
            elif perf == "bon":
                border_color = "#01f0fc"
                badge = "✅ Format qui a bien performé dans ta base"
                badge_color = "#01f0fc"
                badge_bg    = "#001a1a"
            else:
                border_color = "#444"
                badge = "📊 Contenu similaire dans ta base"
                badge_color = "#888"
                badge_bg    = "#0a0a0a"

            # Comparaison Claude (Haiku, ~$0.001) — mise en cache session_state pour éviter re-appel
            _cmp_key = f"kb_cmp_{result.get('video_id','?')}_{match.get('id','?')}"
            if _cmp_key not in st.session_state:
                st.session_state[_cmp_key] = compare_video_to_kb_resource(
                    video_hook_type=hook_type_val,
                    video_hook_text=hook_text_val,
                    video_score=float(creative.get("score_potentiel") or 5),
                    video_categorie=categorie_val,
                    resource=match,
                )
            comparison = st.session_state[_cmp_key]
            points_communs = comparison.get("points_communs", [])
            differences    = comparison.get("differences", [])
            conseil        = comparison.get("conseil_cle", "")

            overlap_str = ", ".join(match.get("overlap_tags", [])[:4])

            st.markdown(f"""
            <div style="background:{badge_bg};border:1px solid {border_color};border-left:4px solid {border_color};
                        border-radius:10px;padding:1rem 1.4rem;margin-bottom:0.8rem;">
                <div style="color:{badge_color};font-size:0.8em;font-weight:700;margin-bottom:6px;">{badge}</div>
                <div style="font-weight:700;font-size:0.95em;margin-bottom:4px;">
                    «{match.get("titre")}»
                    <span style="color:#666;font-size:0.8em;font-weight:400;"> · {vues_str}</span>
                </div>
                <div style="font-size:0.78em;color:#666;margin-bottom:10px;">
                    Tags communs : {overlap_str}
                </div>
            """, unsafe_allow_html=True)

            if points_communs or differences:
                col_kb_a, col_kb_b = st.columns(2)
                with col_kb_a:
                    if points_communs:
                        st.markdown("**Ce qui se ressemble :**")
                        for pt in points_communs[:2]:
                            st.markdown(f"<span style='color:#aaa;font-size:0.85em;'>↔ {pt}</span>", unsafe_allow_html=True)
                with col_kb_b:
                    if differences:
                        st.markdown("**Ce qui diffère :**")
                        for d in differences[:2]:
                            st.markdown(f"<span style='color:#aaa;font-size:0.85em;'>≠ {d}</span>", unsafe_allow_html=True)

            if conseil:
                st.markdown(f"""
                <div style="margin-top:8px;padding:6px 10px;background:#0d0d0d;border-radius:6px;
                            font-size:0.83em;color:#01f0fc;">
                    💡 <strong>Action :</strong> {conseil}
                </div>""", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
    else:
        # Pas de match = discret, pas intrusif
        pass

    # ── BLOC 2 — Timeline des plans ───────────────────────────────────────────
    if plans:
        st.markdown("### 🎬 Timeline des plans")
        for i, plan in enumerate(plans):
            with st.expander(
                f"Plan {i+1} | {plan.get('timestamp_debut', 0):.1f}s–{plan.get('timestamp_fin', 0):.1f}s | {plan.get('type_plan', '')}",
                expanded=(i == 0)
            ):
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
                    texte_ecran = plan.get("texte_visible_ecran")
                    if texte_ecran:
                        st.markdown(f"**Texte écran :** «{texte_ecran}»")
                    pf_plan = plan.get("points_forts", [])
                    if pf_plan:
                        st.markdown(f"**Points forts :** {', '.join(pf_plan) if isinstance(pf_plan, list) else pf_plan}")
                    sug = plan.get("suggestion_amelioration")
                    if sug:
                        st.caption(f"💡 {sug}")

    # ── BLOC 3 — Hook détaillé ────────────────────────────────────────────────
    st.markdown("### 🎣 Hook détaillé")
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

    # ── BLOC 4 — Script complet ───────────────────────────────────────────────
    st.markdown("### 📝 Script complet")
    mots          = whisper.get("mots", [])
    texte_complet = whisper.get("texte_complet", "")
    nb_mots       = whisper.get("nb_mots", 0)
    debit         = whisper.get("debit_parole", 0)
    info_msg      = whisper.get("_info", "")
    err_msg       = whisper.get("_error", "")

    from modules.whisper_mod import format_transcript_display

    if mots:
        # ── Cas 1 : mots avec timestamps → affichage riche ────────────────────
        transcript_timed = format_transcript_display(mots)
        meta_label = f"📄 {nb_mots} mots · {debit} mots/s · avec timestamps"

        # Texte continu lisible (sans timestamps) pour lecture rapide
        texte_continu = " ".join(w["mot"] for w in mots) if mots else texte_complet

        tab_lire, tab_timestamps = st.tabs(["📖 Lire le script", "⏱ Avec timestamps"])

        with tab_lire:
            st.text_area(
                meta_label,
                texte_continu,
                height=220,
                key="transcript_continu"
            )
            if st.button("📋 Copier", key="copy_script_continu"):
                st.code(texte_continu)

        with tab_timestamps:
            st.text_area(
                "Script mot par mot avec timestamps",
                transcript_timed,
                height=220,
                key="transcript_timed"
            )
            if st.button("📋 Copier (avec timestamps)", key="copy_script_timed"):
                st.code(transcript_timed)

    elif texte_complet:
        # ── Cas 2 : texte complet sans word-timestamps ─────────────────────────
        st.text_area(
            f"📄 {len(texte_complet.split())} mots transcrits",
            texte_complet,
            height=220,
            key="transcript_display"
        )
        if st.button("📋 Copier le script", key="copy_script"):
            st.code(texte_complet)
        if info_msg:
            st.caption(f"ℹ️ {info_msg}")

    else:
        # ── Cas 3 : transcription indisponible ────────────────────────────────
        # Essai de récupérer le texte depuis le hook Claude (analyse vision)
        hook_text_val = hook.get("texte_dit") or creative.get("hook_texte", "")
        script_adapte_val = creative.get("script_adapte", "") or creative.get("note_adaptation", "")

        if hook_text_val or script_adapte_val:
            st.info(
                "⚠️ La transcription audio n'a pas pu être générée. "
                "Claude a quand même analysé le contenu visuel et les paroles visibles."
            )
            if hook_text_val:
                st.markdown(f"**🎣 Paroles détectées (hook) :** «{hook_text_val}»")
            if script_adapte_val:
                st.markdown(f"**Script reconstruit (Claude Vision) :** {script_adapte_val[:500]}")
        else:
            st.warning(
                "⚠️ Transcription audio non disponible.  \n"
                "Sur Railway : configure `OPENAI_API_KEY` dans les variables d'environnement.  \n"
                "En local : vérifie que le module `whisper` est installé."
            )
            if err_msg:
                st.caption(f"Erreur Whisper : {err_msg}")

    # ── Script visuel reconstruit depuis Vision (toujours affiché) ────────────
    # Reconstruit le script ligne par ligne depuis les textes détectés dans les plans
    hook_dit  = hook.get("texte_dit", "") or creative.get("hook_texte", "")
    hook_vis  = hook.get("texte_visible", "") or ""
    textes_ecran = []
    for plan in plans:
        te = plan.get("texte_visible_ecran")
        if te and str(te).strip() and str(te).strip().lower() not in ("none", "null", "—", "-"):
            ts = plan.get("timestamp_debut", 0)
            textes_ecran.append(f"[{float(ts):.1f}s] {te}")

    if hook_dit or textes_ecran:
        with st.expander("🎬 Textes détectés par Claude Vision (paroles + écran)", expanded=not mots):
            if hook_dit:
                st.markdown(f"**🎣 Hook (dit) :** «{hook_dit}»")
            if hook_vis:
                st.markdown(f"**🔤 Hook (écran) :** {hook_vis}")
            if textes_ecran:
                st.markdown("**📋 Textes visibles dans les plans :**")
                for t in textes_ecran:
                    st.markdown(f"- {t}")

    # ── BLOC 5 — Adaptation Insolit ───────────────────────────────────────────
    if creative.get("adaptable_insolit") is not False:
        st.markdown("### 🎯 Adaptation Insolit")
        script_adapte = creative.get("script_adapte", "")
        if script_adapte:
            st.markdown(f"""
            <div class="card" style="border-left:4px solid #ff00a4;">
                <strong>Script adapté :</strong><br><em>{script_adapte}</em>
            </div>
            """, unsafe_allow_html=True)

        plans_reproduire = creative.get("plans_a_reproduire", [])
        changements      = creative.get("ce_qui_change", [])
        if isinstance(plans_reproduire, str):
            plans_reproduire = json.loads(plans_reproduire) if plans_reproduire.startswith("[") else [plans_reproduire]
        if isinstance(changements, str):
            changements = json.loads(changements) if changements.startswith("[") else [changements]

        col_a, col_b = st.columns(2)
        with col_a:
            if plans_reproduire:
                st.markdown("**Plans à reproduire :**")
                for p in plans_reproduire: st.markdown(f"✅ {p}")
        with col_b:
            if changements:
                st.markdown("**Ce qui change :**")
                for c in changements: st.markdown(f"↔️ {c}")

    # ── BLOC 6 — Enrichissement ───────────────────────────────────────────────
    st.markdown("---")
    from modules.enrichment import render_enrichment_form
    from modules.database import get_session, Stats

    video_id = result.get("video_id")
    if video_id:
        s2 = get_session()
        existing = s2.query(Stats).filter_by(video_id=video_id).first()
        existing_dict = {
            "performance_tag": existing.performance_tag,
            "vues": existing.vues,
            "completion_rate": existing.completion_rate,
            "note_humaine": existing.note_humaine,
        } if existing else None
        s2.close()
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
