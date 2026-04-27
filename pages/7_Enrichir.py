"""
Page 7 — Enrichir ma base
Importe une vidéo (fichier ou URL), entre les stats réelles + commentaires humains.
Stockage léger : pas d'analyse IA complète, uniquement extraction plans + enrichissement manuel.
"""
import time
import threading
import streamlit as st
from modules.database import (
    get_session, init_db,
    Video, AnalysePegasus, Plan, Transcription, AnalyseCreative, Stats,
)
from modules.enrichment import PERFORMANCE_OPTIONS, PERFORMANCE_LABELS, PERFORMANCE_COLORS, save_enrichment

st.set_page_config(page_title="Enrichir · Insolit Studio", page_icon="📥", layout="wide")

init_db()


# ── Helpers ────────────────────────────────────────────────────────────────────
def _extract_note_section(note: str, section_key: str) -> str:
    """Extrait une section d'une note structurée."""
    if not note or section_key not in note:
        return ""
    try:
        parts = note.split("\n\n")
        for p in parts:
            if section_key in p:
                lines = p.split("\n", 1)
                return lines[1].strip() if len(lines) > 1 else ""
    except Exception:
        pass
    return ""

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp{background:#000;color:#fff;}
[data-testid="stSidebar"]{background:#050505;border-right:1px solid #111;}
[data-testid="stSidebar"] *{color:#fff!important;}
.card{background:#0a0a0a;border:1px solid #1a1a1a;border-radius:12px;padding:1.2rem;margin-bottom:1rem;}
.stTextInput input,.stTextArea textarea,.stSelectbox div{background:#0a0a0a!important;color:#fff!important;border-color:#222!important;}
.stButton>button{background:linear-gradient(135deg,#ff00a4,#0000ff);color:#fff;border:none;border-radius:8px;font-weight:700;}
.stButton>button:hover{opacity:.85;}
.stProgress>div>div{background:linear-gradient(90deg,#0000ff,#01f0fc,#ff00a4);}
.badge-viral{background:#ff00a4;color:#fff;padding:2px 8px;border-radius:12px;font-size:.75em;font-weight:700;}
.badge-bon{background:#01f0fc;color:#000;padding:2px 8px;border-radius:12px;font-size:.75em;font-weight:700;}
.badge-moyen{background:#0000ff;color:#fff;padding:2px 8px;border-radius:12px;font-size:.75em;font-weight:700;}
.badge-mauvais{background:#333;color:#fff;padding:2px 8px;border-radius:12px;font-size:.75em;font-weight:700;}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding:1.5rem 0 1rem 0;'>
    <h1 style='font-size:2rem;font-weight:900;color:#ff00a4;margin:0;'>📥 Enrichir ma base</h1>
    <p style='color:#666;margin-top:.3rem;'>Importe une vidéo · Entre les vraies stats · Ajoute ton analyse humaine</p>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_new, tab_annotate, tab_history = st.tabs(["➕ Nouvelle vidéo", "✏️ Annoter existante", "📋 Historique annotations"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Nouvelle vidéo
# ══════════════════════════════════════════════════════════════════════════════
with tab_new:
    st.markdown("### 1. Source de la vidéo")
    col_src1, col_src2 = st.columns(2)
    with col_src1:
        input_mode = st.radio("Mode d'import", ["📁 Upload fichier", "🔗 URL (TikTok / Instagram)"], horizontal=True)
    with col_src2:
        analyse_mode = st.radio(
            "Niveau d'analyse IA",
            ["⚡ Rapide (plans uniquement, ~10s)", "🧠 Complète (+ transcription Whisper, ~35s)", "🚫 Aucune (stats manuelles seulement)"],
            horizontal=False,
        )

    st.divider()
    st.markdown("### 2. Vidéo")

    video_source = None
    file_bytes = None
    filename = None
    file_size = 0

    if "📁 Upload fichier" in input_mode:
        uploaded = st.file_uploader("Vidéo (MP4, MOV, AVI)", type=["mp4", "mov", "avi", "mkv"])
        if uploaded:
            file_bytes = uploaded.read()
            filename = uploaded.name
            file_size = len(file_bytes)
            video_source = filename
            st.success(f"✅ {filename} · {file_size/1024/1024:.1f} MB")
    else:
        video_source = st.text_input("URL TikTok ou Instagram", placeholder="https://www.tiktok.com/@...")

    st.divider()
    st.markdown("### 3. Métadonnées")

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        type_source = st.selectbox("Type de source", ["mon_compte", "concurrent", "inspiration", "secteur"],
                                   format_func=lambda x: {"mon_compte":"📱 Mon compte","concurrent":"🎯 Concurrent","inspiration":"💡 Inspiration","secteur":"🏪 Secteur"}.get(x,x))
        nom_compte = st.text_input("Compte (@)", placeholder="@insolitparis")
    with col_m2:
        partenaire = st.text_input("Partenaire / Restaurant", placeholder="O'Tacos République")
        ville = st.text_input("Ville", placeholder="Paris 11e")
    with col_m3:
        categorie = st.selectbox("Catégorie", ["", "fast_food", "gastronomique", "bar", "experience", "tendance", "autre"],
                                  format_func=lambda x: {"fast_food":"🍟 Fast food","gastronomique":"🍽️ Gastronomique","bar":"🍸 Bar","experience":"✨ Expérience","tendance":"📈 Tendance","autre":"📦 Autre"}.get(x, x) if x else "— Choisir —")
        date_pub = st.date_input("Date de publication", value=None)

    st.divider()
    st.markdown("### 4. Stats réelles (si disponibles)")

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        vues = st.number_input("👁 Vues", min_value=0, value=0, step=1000, format="%d")
        likes = st.number_input("❤️ Likes", min_value=0, value=0, step=100, format="%d")
    with col_s2:
        comments = st.number_input("💬 Commentaires", min_value=0, value=0, step=10, format="%d")
        shares = st.number_input("↗️ Partages", min_value=0, value=0, step=10, format="%d")
    with col_s3:
        saves = st.number_input("🔖 Sauvegardes", min_value=0, value=0, step=10, format="%d")
        completion = st.slider("⏱ Watch time %", 0, 100, 50)
    with col_s4:
        perf_label = st.radio(
            "Performance globale",
            options=list(PERFORMANCE_OPTIONS.keys()),
            index=0,
        )

    st.divider()
    st.markdown("### 5. Ton analyse humaine")

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        ce_qui_a_marche = st.text_area(
            "✅ Ce qui a marché",
            placeholder="Ex: hook prix choc en 1s, plan macro plat très appétissant, réaction authentique...",
            height=100,
        )
        ce_qui_na_pas_marche = st.text_area(
            "❌ Ce qui n'a pas marché",
            placeholder="Ex: fin trop longue, éclairage froid, voix trop faible...",
            height=100,
        )
    with col_h2:
        lecon_principale = st.text_area(
            "💡 Leçon principale",
            placeholder="Ex: toujours montrer le prix dans les 2 premières secondes pour ce type de format",
            height=100,
        )
        a_reproduire = st.text_area(
            "🔁 À reproduire dans nos prochaines vidéos",
            placeholder="Ex: plan main qui attrape le burger, zoom slow sur texture...",
            height=100,
        )

    tags_input = st.text_input("🏷️ Tags (séparés par virgule)", placeholder="prix_choc, macro_plat, fast_food, hook_fort")

    # Note composite
    note_humaine_parts = []
    if ce_qui_a_marche:
        note_humaine_parts.append(f"✅ CE QUI A MARCHÉ:\n{ce_qui_a_marche}")
    if ce_qui_na_pas_marche:
        note_humaine_parts.append(f"❌ CE QUI N'A PAS MARCHÉ:\n{ce_qui_na_pas_marche}")
    if lecon_principale:
        note_humaine_parts.append(f"💡 LEÇON:\n{lecon_principale}")
    if a_reproduire:
        note_humaine_parts.append(f"🔁 À REPRODUIRE:\n{a_reproduire}")
    note_humaine = "\n\n".join(note_humaine_parts)

    st.divider()

    # Bouton import
    can_import = bool(video_source and (file_bytes or "http" in str(video_source)))
    if not can_import:
        st.info("👆 Ajoute d'abord une vidéo (upload ou URL) pour continuer.")

    if st.button("📥 IMPORTER & ENRICHIR", disabled=not can_import, use_container_width=True, type="primary"):

        perf_tag = PERFORMANCE_OPTIONS[perf_label]

        # ── Progress UI ──
        progress_bar = st.progress(0.0)
        status_ph = st.empty()

        result_holder = {"result": None, "error": None}
        steps_done = []

        def _import_video():
            try:
                from modules.analyzer import (
                    copy_uploaded_video, download_video,
                    get_video_duration, compress_video,
                    detect_scene_changes, extract_frames_for_vision,
                )
                from modules.claude_mod import analyze_frames_with_vision

                # 1. Init DB entry
                steps_done.append("init")
                session = get_session()
                video = Video(
                    url_source=video_source if "http" in str(video_source) else None,
                    type_source=type_source,
                    nom_compte=nom_compte or "",
                    categorie=categorie or "",
                    partenaire=partenaire or "",
                    ville=ville or "",
                    date_publication=str(date_pub) if date_pub else None,
                    statut_analyse="en_cours",
                )
                session.add(video)
                session.commit()
                vid_id = video.id

                # 2. Récupération
                steps_done.append("download")
                if file_bytes:
                    path = copy_uploaded_video(file_bytes, filename, vid_id)
                else:
                    path = download_video(video_source, vid_id)

                duree = get_video_duration(path)
                video.fichier_path = path
                video.duree_secondes = duree
                session.commit()

                if "🚫 Aucune" not in analyse_mode:
                    # 3. Compression
                    steps_done.append("compress")
                    working_path = compress_video(path)

                    # 4. Détection plans
                    steps_done.append("scenes")
                    timestamps = detect_scene_changes(working_path, duree)
                    frames = extract_frames_for_vision(working_path, timestamps)

                    # 5. Vision (rapide, sans Whisper)
                    steps_done.append("vision")
                    pegasus_data, v_usage = analyze_frames_with_vision(frames, duree)
                    plans_data = pegasus_data.get("plans", [])
                    metriques = pegasus_data.get("metriques_globales", {})
                    hook = pegasus_data.get("hook_analyse", {})

                    import json
                    ap = AnalysePegasus(
                        video_id=vid_id,
                        raw_json=json.dumps(pegasus_data, ensure_ascii=False),
                        nb_plans=len(plans_data),
                        duree_moyenne_plan=duree / max(len(plans_data), 1),
                        rythme_coupes_par_seconde=float(metriques.get("rythme_coupes_par_seconde", 0)),
                        luminosite_moyenne=float(metriques.get("luminosite_moyenne", 5)),
                        presence_visage=False,
                        presence_texte_ecran=False,
                        qualite_production=float(metriques.get("qualite_globale", 5)),
                        type_tournage=metriques.get("type_tournage", ""),
                        mouvement_dominant="",
                    )
                    session.add(ap)

                    for i, p in enumerate(plans_data):
                        session.add(Plan(
                            video_id=vid_id,
                            numero_plan=i + 1,
                            timestamp_debut=float(p.get("timestamp_debut", 0)),
                            timestamp_fin=float(p.get("timestamp_fin", duree)),
                            duree=float(p.get("timestamp_fin", duree)) - float(p.get("timestamp_debut", 0)),
                            type_plan=p.get("type_plan", ""),
                            description=p.get("sujet_principal", ""),
                            luminosite=float(p.get("luminosite", 5)),
                            mouvement=p.get("mouvement_camera", ""),
                            presence_visage=bool(p.get("presence_visage", False)),
                            expression=p.get("expression_visage", ""),
                            texte_visible=p.get("texte_visible_ecran"),
                            qualite=float(p.get("qualite_production", 5)),
                            role_narratif=p.get("role_narratif", ""),
                        ))

                    # 6. Whisper si mode complet
                    if "🧠 Complète" in analyse_mode:
                        steps_done.append("whisper")
                        from modules.whisper_mod import transcribe
                        w = transcribe(working_path)
                        for word in w.get("mots", []):
                            session.add(Transcription(
                                video_id=vid_id,
                                timestamp=word["start"],
                                mot=word["mot"],
                                confiance=word["confiance"],
                            ))

                    titre = partenaire or nom_compte or f"Vidéo {vid_id}"
                    video.titre = titre

                else:
                    # Mode sans IA — titre minimal
                    video.titre = partenaire or nom_compte or f"Vidéo importée #{vid_id}"

                session.commit()

                # 7. Stats + enrichissement
                steps_done.append("stats")
                tags_list = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
                full_note = note_humaine
                if tags_list:
                    full_note = f"🏷️ TAGS: {', '.join(tags_list)}\n\n" + full_note if full_note else f"🏷️ TAGS: {', '.join(tags_list)}"

                import json as _json
                stats = Stats(
                    video_id=vid_id,
                    vues=vues if vues > 0 else None,
                    likes=likes if likes > 0 else None,
                    comments=comments if comments > 0 else None,
                    shares=shares if shares > 0 else None,
                    saves=saves if saves > 0 else None,
                    completion_rate=float(completion),
                    performance_tag=perf_tag,
                    note_humaine=full_note or None,
                    annotee_le=__import__("datetime").datetime.utcnow(),
                )
                session.add(stats)

                video.statut_analyse = "complete"
                session.commit()
                session.close()

                result_holder["result"] = {
                    "video_id": vid_id,
                    "titre": video.titre,
                    "plans_count": len(plans_data) if "🚫 Aucune" not in analyse_mode else 0,
                    "perf_tag": perf_tag,
                }

            except Exception as e:
                result_holder["error"] = str(e)

        # Lancer thread
        t = threading.Thread(target=_import_video, daemon=True)
        t.start()
        start_ts = time.time()

        step_labels = {
            "init": "🔧 Initialisation...",
            "download": "⬇️ Récupération vidéo...",
            "compress": "🗜️ Compression...",
            "scenes": "📸 Détection des plans...",
            "vision": "🎬 Analyse visuelle (Claude)...",
            "whisper": "📝 Transcription audio...",
            "stats": "💾 Sauvegarde stats...",
        }

        while t.is_alive():
            elapsed = time.time() - start_ts
            current_step = steps_done[-1] if steps_done else "init"
            label = step_labels.get(current_step, "⏳ En cours...")
            pct = min(0.95, elapsed / 40)
            progress_bar.progress(pct)
            status_ph.markdown(f"**{label}** ({int(elapsed)}s)")
            time.sleep(1)

        t.join()

        if result_holder["error"]:
            st.error(f"❌ Erreur : {result_holder['error']}")
        elif result_holder["result"]:
            r = result_holder["result"]
            progress_bar.progress(1.0)
            status_ph.empty()

            color = PERFORMANCE_COLORS.get(r["perf_tag"], "#333")
            label_perf = PERFORMANCE_LABELS.get(r["perf_tag"], r["perf_tag"])

            st.success(f"✅ Vidéo #{r['video_id']} importée et enrichie !")
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.metric("Video ID", f"#{r['video_id']}")
            with col_r2:
                st.metric("Plans détectés", r["plans_count"] if r["plans_count"] > 0 else "—")
            with col_r3:
                st.markdown(f"<span class='badge-{r[\"perf_tag\"]}'>{label_perf}</span>", unsafe_allow_html=True)

            if note_humaine:
                st.markdown("**📝 Annotation sauvegardée :**")
                st.markdown(f"> {note_humaine[:300]}..." if len(note_humaine) > 300 else f"> {note_humaine}")

            st.info("💡 Cette vidéo est maintenant dans ta bibliothèque et enrichit la génération de briefs.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Annoter une vidéo existante
# ══════════════════════════════════════════════════════════════════════════════
with tab_annotate:
    st.markdown("### Sélectionner une vidéo à annoter")

    session = get_session()
    try:
        videos = (
            session.query(Video)
            .filter(Video.statut_analyse == "complete")
            .order_by(Video.created_at.desc())
            .limit(100)
            .all()
        )

        if not videos:
            st.info("Aucune vidéo analysée. Lance d'abord une analyse depuis la page **Analyser**.")
        else:
            # Sélecteur
            video_options = {
                f"#{v.id} — {v.titre or 'Sans titre'} ({v.nom_compte or '?'})": v.id
                for v in videos
            }
            selected_label = st.selectbox("Vidéo", list(video_options.keys()))
            sel_id = video_options[selected_label]

            sel_video = next(v for v in videos if v.id == sel_id)
            existing_stats = None
            if sel_video.stats:
                existing_stats = {
                    "vues": sel_video.stats.vues or 0,
                    "likes": sel_video.stats.likes or 0,
                    "comments": sel_video.stats.comments or 0,
                    "shares": sel_video.stats.shares or 0,
                    "saves": sel_video.stats.saves or 0,
                    "completion_rate": sel_video.stats.completion_rate or 50,
                    "performance_tag": sel_video.stats.performance_tag or "",
                    "note_humaine": sel_video.stats.note_humaine or "",
                }

            # Infos vidéo
            with st.expander("📋 Infos vidéo analysée", expanded=False):
                col_i1, col_i2, col_i3 = st.columns(3)
                with col_i1:
                    st.caption(f"**Partenaire:** {sel_video.partenaire or '—'}")
                    st.caption(f"**Compte:** {sel_video.nom_compte or '—'}")
                with col_i2:
                    st.caption(f"**Durée:** {sel_video.duree_secondes:.0f}s" if sel_video.duree_secondes else "**Durée:** —")
                    if sel_video.analyse_creative:
                        st.caption(f"**Score potentiel:** {sel_video.analyse_creative.score_potentiel or '—'}/10")
                with col_i3:
                    if sel_video.analyse_pegasus:
                        st.caption(f"**Plans détectés:** {sel_video.analyse_pegasus.nb_plans or '—'}")

            st.divider()

            # Formulaire annotation
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.markdown("#### 📊 Stats réelles")
                a_vues = st.number_input("Vues", min_value=0, value=existing_stats["vues"] if existing_stats else 0, step=1000, key="a_vues")
                a_likes = st.number_input("Likes", min_value=0, value=existing_stats["likes"] if existing_stats else 0, step=100, key="a_likes")
                a_comments = st.number_input("Commentaires", min_value=0, value=existing_stats["comments"] if existing_stats else 0, key="a_comments")
                a_shares = st.number_input("Partages", min_value=0, value=existing_stats["shares"] if existing_stats else 0, key="a_shares")
                a_saves = st.number_input("Sauvegardes", min_value=0, value=existing_stats["saves"] if existing_stats else 0, key="a_saves")
                a_completion = st.slider("Watch time %", 0, 100,
                                         int(existing_stats["completion_rate"]) if existing_stats else 50, key="a_compl")

                # Performance tag
                perf_opts = list(PERFORMANCE_OPTIONS.keys())
                default_perf = 0
                if existing_stats and existing_stats["performance_tag"]:
                    vals = list(PERFORMANCE_OPTIONS.values())
                    if existing_stats["performance_tag"] in vals:
                        default_perf = vals.index(existing_stats["performance_tag"])
                a_perf_label = st.radio("Performance", perf_opts, index=default_perf, key="a_perf")

            with col_a2:
                st.markdown("#### 📝 Analyse humaine")
                existing_note = existing_stats["note_humaine"] if existing_stats else ""

                a_marche = st.text_area("✅ Ce qui a marché", height=90, key="a_marche",
                    value=_extract_note_section(existing_note, "CE QUI A MARCHÉ") if existing_note else "")
                a_nmarche = st.text_area("❌ Ce qui n'a pas marché", height=90, key="a_nmarche",
                    value=_extract_note_section(existing_note, "CE QUI N'A PAS MARCHÉ") if existing_note else "")
                a_lecon = st.text_area("💡 Leçon principale", height=90, key="a_lecon",
                    value=_extract_note_section(existing_note, "LEÇON") if existing_note else "")
                a_repro = st.text_area("🔁 À reproduire", height=90, key="a_repro",
                    value=_extract_note_section(existing_note, "À REPRODUIRE") if existing_note else "")

            if st.button("💾 SAUVEGARDER L'ANNOTATION", key="save_annot", use_container_width=True, type="primary"):
                parts = []
                if a_marche: parts.append(f"✅ CE QUI A MARCHÉ:\n{a_marche}")
                if a_nmarche: parts.append(f"❌ CE QUI N'A PAS MARCHÉ:\n{a_nmarche}")
                if a_lecon: parts.append(f"💡 LEÇON:\n{a_lecon}")
                if a_repro: parts.append(f"🔁 À REPRODUIRE:\n{a_repro}")
                full_note = "\n\n".join(parts)

                tag = PERFORMANCE_OPTIONS[a_perf_label]
                ok = save_enrichment(
                    video_id=sel_id,
                    performance_tag=tag,
                    vues=a_vues if a_vues > 0 else None,
                    completion_rate=float(a_completion),
                    note_humaine=full_note or None,
                )

                # Sauvegarder aussi les autres stats
                if ok:
                    s = get_session()
                    try:
                        stats_obj = s.query(Stats).filter_by(video_id=sel_id).first()
                        if stats_obj:
                            if a_likes > 0: stats_obj.likes = a_likes
                            if a_comments > 0: stats_obj.comments = a_comments
                            if a_shares > 0: stats_obj.shares = a_shares
                            if a_saves > 0: stats_obj.saves = a_saves
                        s.commit()
                    finally:
                        s.close()

                    st.success(f"✅ Annotation sauvegardée pour #{sel_id} !")
                    st.balloons()
                else:
                    st.error("Erreur lors de la sauvegarde.")

    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Historique
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    st.markdown("### Vidéos annotées manuellement")

    session = get_session()
    try:
        annotated = (
            session.query(Video)
            .join(Stats, isouter=True)
            .filter(
                Video.statut_analyse == "complete",
                Stats.note_humaine.isnot(None),
            )
            .order_by(Stats.annotee_le.desc())
            .limit(50)
            .all()
        )

        if not annotated:
            st.info("Aucune vidéo annotée pour l'instant. Utilise l'onglet **Annoter existante** pour commencer.")
        else:
            # Filtres
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                search_q = st.text_input("🔍 Rechercher dans les notes", placeholder="hook, prix, macro...")
            with col_f2:
                perf_filter = st.multiselect("Performance", ["viral", "bon", "moyen", "mauvais"],
                                              default=["viral", "bon"])

            st.markdown(f"**{len(annotated)} vidéos annotées**")

            for v in annotated:
                if perf_filter and v.stats and v.stats.performance_tag not in perf_filter:
                    continue
                note = v.stats.note_humaine if v.stats else ""
                if search_q and search_q.lower() not in (note or "").lower():
                    continue

                perf = v.stats.performance_tag if v.stats else "—"
                perf_color = PERFORMANCE_COLORS.get(perf, "#333")

                with st.expander(f"#{v.id} — {v.titre or 'Sans titre'} · {v.nom_compte or '?'}"):
                    col_h1, col_h2, col_h3 = st.columns(3)
                    with col_h1:
                        st.markdown(f"<span style='background:{perf_color};color:{'#000' if perf=='bon' else '#fff'};padding:2px 8px;border-radius:8px;font-size:.8em;font-weight:700;'>{PERFORMANCE_LABELS.get(perf, perf)}</span>", unsafe_allow_html=True)
                        if v.stats and v.stats.vues:
                            st.caption(f"👁 {v.stats.vues:,} vues")
                    with col_h2:
                        if v.stats and v.stats.completion_rate:
                            st.caption(f"⏱ Watch time: {v.stats.completion_rate:.0f}%")
                        if v.analyse_pegasus:
                            st.caption(f"📸 {v.analyse_pegasus.nb_plans} plans")
                    with col_h3:
                        if v.stats and v.stats.annotee_le:
                            st.caption(f"📅 {v.stats.annotee_le.strftime('%d/%m/%Y')}")

                    if note:
                        st.markdown("**📝 Notes :**")
                        st.markdown(f"```\n{note[:800]}\n```" if len(note) > 800 else f"```\n{note}\n```")

    finally:
        session.close()
