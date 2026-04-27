"""
Page 7 — Enrichissement ultra-rapide
Annoter 10 vidéos en moins de 5 minutes avec des cartes compactes one-shot.
"""
import os
from datetime import datetime

import streamlit as st
from modules.database import get_session, Video, Stats, AnalyseCreative, init_db

st.set_page_config(page_title="Enrichissement · Insolit Studio", page_icon="⚡", layout="wide")

init_db()

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background: #0a0a0a; color: #fff; }
[data-testid="stSidebar"] { background: #050505; border-right: 1px solid #111; }
[data-testid="stSidebar"] * { color: #fff !important; }

/* Cards */
.quick-card {
    background: #111;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.2s;
}
.quick-card:hover { border-color: #ff00a4; }
.quick-card-saved {
    background: #0a1a0a;
    border: 1px solid #22c55e;
    border-radius: 12px;
    padding: 0.75rem 1.2rem;
    margin-bottom: 0.75rem;
    opacity: 0.7;
}
.vid-title {
    font-size: 1rem;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 300px;
}
.vid-meta { font-size: 0.78rem; color: #666; margin-top: 2px; }

/* Performance badges */
.badge-viral  { background: #ff00a4; color: #000; padding: 3px 10px; border-radius: 20px; font-size: .8em; font-weight: 800; }
.badge-bon    { background: #01f0fc; color: #000; padding: 3px 10px; border-radius: 20px; font-size: .8em; font-weight: 800; }
.badge-moyen  { background: #f59e0b; color: #000; padding: 3px 10px; border-radius: 20px; font-size: .8em; font-weight: 800; }
.badge-mauvais{ background: #ef4444; color: #fff; padding: 3px 10px; border-radius: 20px; font-size: .8em; font-weight: 800; }

/* Orange banner */
.banner-warn {
    background: linear-gradient(90deg, #ff6b00, #ff00a4);
    color: #fff;
    border-radius: 10px;
    padding: 0.7rem 1.2rem;
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: 1.2rem;
}

/* Radio style override */
.stRadio > div { flex-direction: row; gap: 6px; }
.stRadio label { font-size: 0.85rem; }

/* Inputs */
.stTextInput input, .stTextArea textarea, .stSelectbox div {
    background: #0a0a0a !important;
    color: #fff !important;
    border-color: #222 !important;
}
.stNumberInput input { background: #0a0a0a !important; color: #fff !important; border-color: #222 !important; }
.stSlider { color: #fff; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #ff00a4, #0000ff);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-weight: 700;
}
.stButton > button:hover { opacity: .85; }
.stButton > button[kind="secondary"] {
    background: #1a1a1a;
    border: 1px solid #333;
}

/* Table */
.hist-table { width: 100%; border-collapse: collapse; }
.hist-table th { background: #111; color: #666; font-size: 0.78rem; text-transform: uppercase; padding: 6px 10px; border-bottom: 1px solid #222; }
.hist-table td { padding: 8px 10px; border-bottom: 1px solid #1a1a1a; font-size: 0.9rem; vertical-align: middle; }
.hist-table tr:hover td { background: #111; }

/* Progress */
.stProgress > div > div { background: linear-gradient(90deg, #0000ff, #01f0fc, #ff00a4); }

/* Divider */
hr { border-color: #222; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────
PERF_OPTIONS = {
    "🔥 Viral": "viral",
    "✅ Bon": "bon",
    "😐 Moyen": "moyen",
    "❌ Mauvais": "mauvais",
}
PERF_LABELS = {v: k for k, v in PERF_OPTIONS.items()}
PERF_BADGE = {
    "viral":   "<span class='badge-viral'>🔥 Viral</span>",
    "bon":     "<span class='badge-bon'>✅ Bon</span>",
    "moyen":   "<span class='badge-moyen'>😐 Moyen</span>",
    "mauvais": "<span class='badge-mauvais'>❌ Mauvais</span>",
}
PERF_COLORS = {
    "viral":   "#ff00a4",
    "bon":     "#01f0fc",
    "moyen":   "#f59e0b",
    "mauvais": "#ef4444",
}


def _thumb_path(video_id: int) -> str | None:
    p = f"./screenshots/{video_id}/plan_01.jpg"
    return p if os.path.exists(p) else None


def _fmt_dur(secs) -> str:
    if not secs:
        return "—"
    s = int(secs)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def _fmt_date(dt) -> str:
    if not dt:
        return "—"
    try:
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(dt)[:10]


def _extract_note_section(note: str, section_key: str) -> str:
    if not note or section_key not in note:
        return ""
    try:
        for p in note.split("\n\n"):
            if section_key in p:
                lines = p.split("\n", 1)
                return lines[1].strip() if len(lines) > 1 else ""
    except Exception:
        pass
    return ""


def _save_quick(video_id: int, perf_tag: str, vues: int, completion: float):
    session = get_session()
    try:
        existing = session.query(Stats).filter_by(video_id=video_id).first()
        if existing:
            existing.performance_tag = perf_tag
            if vues > 0:
                existing.vues = vues
            if completion > 0:
                existing.completion_rate = completion
            existing.annotee_le = datetime.utcnow()
        else:
            session.add(Stats(
                video_id=video_id,
                performance_tag=perf_tag,
                vues=vues if vues > 0 else None,
                completion_rate=completion if completion > 0 else None,
                annotee_le=datetime.utcnow(),
            ))
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()


# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _load_unannotated():
    session = get_session()
    try:
        videos = (
            session.query(Video)
            .outerjoin(Stats, Video.id == Stats.video_id)
            .filter(
                Video.statut_analyse == "complete",
                Stats.performance_tag.is_(None),
            )
            .order_by(Video.created_at.desc())
            .limit(50)
            .all()
        )
        result = []
        for v in videos:
            result.append({
                "id": v.id,
                "titre": v.titre or f"Vidéo #{v.id}",
                "duree": v.duree_secondes,
                "created_at": v.created_at,
                "partenaire": v.partenaire or "",
                "nom_compte": v.nom_compte or "",
            })
        return result
    finally:
        session.close()


@st.cache_data(ttl=30, show_spinner=False)
def _load_all_complete():
    session = get_session()
    try:
        videos = (
            session.query(Video)
            .filter(Video.statut_analyse == "complete")
            .order_by(Video.created_at.desc())
            .limit(200)
            .all()
        )
        result = []
        for v in videos:
            s = v.stats
            result.append({
                "id": v.id,
                "titre": v.titre or f"Vidéo #{v.id}",
                "duree": v.duree_secondes,
                "created_at": v.created_at,
                "partenaire": v.partenaire or "",
                "nom_compte": v.nom_compte or "",
                "performance_tag": s.performance_tag if s else None,
                "vues": s.vues if s else None,
                "likes": s.likes if s else None,
                "comments": s.comments if s else None,
                "shares": s.shares if s else None,
                "saves": s.saves if s else None,
                "completion_rate": s.completion_rate if s else None,
                "note_humaine": s.note_humaine if s else None,
                "annotee_le": s.annotee_le if s else None,
            })
        return result
    finally:
        session.close()


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding:1.2rem 0 0.5rem 0;'>
    <h1 style='font-size:2rem;font-weight:900;color:#ff00a4;margin:0;'>
        ⚡ Enrichissement ultra-rapide
    </h1>
</div>
""", unsafe_allow_html=True)

unannotated_raw = _load_unannotated()

# Filter out videos already saved in this session
saved_keys = {k for k in st.session_state if k.startswith("saved_quick_") and st.session_state[k]}
saved_ids = {int(k.replace("saved_quick_", "")) for k in saved_keys}
unannotated = [v for v in unannotated_raw if v["id"] not in saved_ids]
n_unannotated = len(unannotated)

# Counter
st.markdown(f"""
<div style='color:#aaa;font-size:0.95rem;margin-bottom:0.8rem;'>
    <b style='color:#fff;font-size:1.15rem;'>{n_unannotated}</b> vidéo{'s' if n_unannotated != 1 else ''} non annotée{'s' if n_unannotated != 1 else ''} — annote-les pour améliorer tes briefs
</div>
""", unsafe_allow_html=True)

if n_unannotated > 0:
    st.markdown(f"""
    <div class='banner-warn'>
        ⚡ {n_unannotated} vidéo{'s' if n_unannotated != 1 else ''} attendent ta note — objectif : 10 vidéos annotées en moins de 5 minutes !
    </div>
    """, unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_quick, tab_full, tab_history = st.tabs(["⚡ Annoter rapidement", "📝 Annotation complète", "📊 Historique"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Annotation rapide
# ══════════════════════════════════════════════════════════════════════════════
with tab_quick:

    if not unannotated:
        st.markdown("""
        <div style='text-align:center;padding:3rem 0;'>
            <div style='font-size:3rem;'>🎉</div>
            <h3 style='color:#22c55e;'>Toutes les vidéos sont annotées !</h3>
            <p style='color:#666;'>Reviens après avoir analysé de nouvelles vidéos.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='color:#666;font-size:0.88rem;margin-bottom:1rem;'>Scroll et clique [💾 Sauvegarder →] pour chaque vidéo.</p>", unsafe_allow_html=True)

        for video in unannotated:
            vid_id = video["id"]
            key_saved = f"saved_quick_{vid_id}"

            # Already saved this session — show compact green card
            if st.session_state.get(key_saved):
                titre_short = video["titre"][:40] + ("…" if len(video["titre"]) > 40 else "")
                st.markdown(f"""
                <div class='quick-card-saved'>
                    ✅ <b>#{vid_id}</b> — {titre_short} <span style='color:#22c55e;'>sauvegardé</span>
                </div>
                """, unsafe_allow_html=True)
                continue

            # Active card
            thumb = _thumb_path(vid_id)
            titre_short = video["titre"][:40] + ("…" if len(video["titre"]) > 40 else "")
            meta_parts = []
            if video["duree"]:
                meta_parts.append(_fmt_dur(video["duree"]))
            if video["created_at"]:
                meta_parts.append(_fmt_date(video["created_at"]))
            if video["partenaire"]:
                meta_parts.append(video["partenaire"])
            elif video["nom_compte"]:
                meta_parts.append(video["nom_compte"])
            meta_str = " · ".join(meta_parts)

            with st.container():
                st.markdown(f"<div class='quick-card'>", unsafe_allow_html=True)

                col_thumb, col_info, col_actions = st.columns([1, 3, 4])

                with col_thumb:
                    if thumb:
                        st.image(thumb, width=90)
                    else:
                        st.markdown("""
                        <div style='width:90px;height:60px;background:#1a1a1a;border-radius:8px;
                                    display:flex;align-items:center;justify-content:center;
                                    font-size:1.6rem;color:#444;border:1px solid #222;'>
                            🎬
                        </div>
                        """, unsafe_allow_html=True)

                with col_info:
                    st.markdown(f"""
                    <div class='vid-title'>#{vid_id} — {titre_short}</div>
                    <div class='vid-meta'>{meta_str}</div>
                    """, unsafe_allow_html=True)

                with col_actions:
                    perf_key = f"perf_{vid_id}"
                    vues_key = f"vues_{vid_id}"
                    comp_key = f"comp_{vid_id}"

                    perf_choice = st.radio(
                        "Performance",
                        options=list(PERF_OPTIONS.keys()),
                        key=perf_key,
                        horizontal=True,
                        label_visibility="collapsed",
                    )

                    col_v, col_c, col_btn = st.columns([2, 2, 2])
                    with col_v:
                        vues_val = st.number_input(
                            "👁 Vues",
                            min_value=0,
                            value=0,
                            step=1000,
                            format="%d",
                            key=vues_key,
                            label_visibility="visible",
                        )
                    with col_c:
                        comp_val = st.number_input(
                            "⏱️ Complétion %",
                            min_value=0,
                            max_value=100,
                            value=0,
                            step=5,
                            format="%d",
                            key=comp_key,
                            label_visibility="visible",
                        )
                    with col_btn:
                        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                        if st.button("💾 Sauvegarder →", key=f"save_{vid_id}", use_container_width=True):
                            tag = PERF_OPTIONS[perf_choice]
                            ok = _save_quick(vid_id, tag, int(vues_val), float(comp_val))
                            if ok:
                                st.session_state[key_saved] = True
                                _load_unannotated.clear()
                                _load_all_complete.clear()
                                st.rerun()
                            else:
                                st.error("Erreur sauvegarde.")

                st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Annotation complète
# ══════════════════════════════════════════════════════════════════════════════
with tab_full:
    all_videos = _load_all_complete()

    if not all_videos:
        st.info("Aucune vidéo analysée. Lance d'abord une analyse depuis la page **Analyser**.")
    else:
        video_options = {
            f"#{v['id']} — {v['titre'][:50]} ({v['nom_compte'] or '?'})": v
            for v in all_videos
        }
        selected_label = st.selectbox("Choisir une vidéo", list(video_options.keys()), key="full_select")
        sel = video_options[selected_label]
        sel_id = sel["id"]

        st.markdown("---")

        # Show thumbnail if available
        thumb = _thumb_path(sel_id)
        if thumb:
            col_t, col_info = st.columns([1, 5])
            with col_t:
                st.image(thumb, width=120)
            with col_info:
                st.markdown(f"**#{sel_id} — {sel['titre']}**")
                st.caption(f"{_fmt_dur(sel['duree'])} · {_fmt_date(sel['created_at'])} · {sel['partenaire'] or sel['nom_compte'] or '—'}")
        else:
            st.markdown(f"**#{sel_id} — {sel['titre']}**")
            st.caption(f"{_fmt_dur(sel['duree'])} · {_fmt_date(sel['created_at'])}")

        st.markdown("#### 📊 Stats réelles")
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        with col_s1:
            f_vues = st.number_input("👁 Vues", min_value=0, value=sel["vues"] or 0, step=1000, format="%d", key="f_vues")
            f_likes = st.number_input("❤️ Likes", min_value=0, value=sel["likes"] or 0, step=100, format="%d", key="f_likes")
        with col_s2:
            f_comments = st.number_input("💬 Commentaires", min_value=0, value=sel["comments"] or 0, step=10, format="%d", key="f_comments")
            f_shares = st.number_input("↗️ Partages", min_value=0, value=sel["shares"] or 0, step=10, format="%d", key="f_shares")
        with col_s3:
            f_saves = st.number_input("🔖 Sauvegardes", min_value=0, value=sel["saves"] or 0, step=10, format="%d", key="f_saves")
            f_completion = st.slider("⏱ Watch time %", 0, 100, int(sel["completion_rate"] or 50), key="f_comp")
        with col_s4:
            # Default index for performance tag
            perf_vals = list(PERF_OPTIONS.values())
            default_perf_idx = perf_vals.index(sel["performance_tag"]) if sel["performance_tag"] in perf_vals else 0
            f_perf_label = st.radio(
                "Performance globale",
                options=list(PERF_OPTIONS.keys()),
                index=default_perf_idx,
                key="f_perf",
            )

        st.markdown("#### 📝 Analyse humaine")
        existing_note = sel["note_humaine"] or ""
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            f_marche = st.text_area(
                "✅ Ce qui a marché",
                value=_extract_note_section(existing_note, "CE QUI A MARCHÉ"),
                height=100, key="f_marche",
                placeholder="Hook, plan produit, rythme...",
            )
            f_nmarche = st.text_area(
                "❌ Ce qui n'a pas marché",
                value=_extract_note_section(existing_note, "CE QUI N'A PAS MARCHÉ"),
                height=100, key="f_nmarche",
                placeholder="Fin trop longue, éclairage froid...",
            )
        with col_h2:
            f_lecon = st.text_area(
                "💡 Leçon principale",
                value=_extract_note_section(existing_note, "LEÇON"),
                height=100, key="f_lecon",
                placeholder="La clé de ce format...",
            )
            f_repro = st.text_area(
                "🔁 À reproduire",
                value=_extract_note_section(existing_note, "À REPRODUIRE"),
                height=100, key="f_repro",
                placeholder="Plan, angle, technique...",
            )

        if st.button("💾 SAUVEGARDER L'ANNOTATION COMPLÈTE", key="save_full", use_container_width=True, type="primary"):
            parts = []
            if f_marche: parts.append(f"✅ CE QUI A MARCHÉ:\n{f_marche}")
            if f_nmarche: parts.append(f"❌ CE QUI N'A PAS MARCHÉ:\n{f_nmarche}")
            if f_lecon: parts.append(f"💡 LEÇON:\n{f_lecon}")
            if f_repro: parts.append(f"🔁 À REPRODUIRE:\n{f_repro}")
            full_note = "\n\n".join(parts)
            perf_tag = PERF_OPTIONS[f_perf_label]

            session = get_session()
            try:
                existing = session.query(Stats).filter_by(video_id=sel_id).first()
                if existing:
                    existing.performance_tag = perf_tag
                    if f_vues > 0: existing.vues = f_vues
                    if f_likes > 0: existing.likes = f_likes
                    if f_comments > 0: existing.comments = f_comments
                    if f_shares > 0: existing.shares = f_shares
                    if f_saves > 0: existing.saves = f_saves
                    existing.completion_rate = float(f_completion)
                    existing.note_humaine = full_note or existing.note_humaine
                    existing.annotee_le = datetime.utcnow()
                else:
                    session.add(Stats(
                        video_id=sel_id,
                        performance_tag=perf_tag,
                        vues=f_vues if f_vues > 0 else None,
                        likes=f_likes if f_likes > 0 else None,
                        comments=f_comments if f_comments > 0 else None,
                        shares=f_shares if f_shares > 0 else None,
                        saves=f_saves if f_saves > 0 else None,
                        completion_rate=float(f_completion),
                        note_humaine=full_note or None,
                        annotee_le=datetime.utcnow(),
                    ))
                session.commit()
                st.success(f"✅ Annotation complète sauvegardée pour #{sel_id} !")
                st.session_state[f"saved_quick_{sel_id}"] = True
                _load_unannotated.clear()
                _load_all_complete.clear()
            except Exception as e:
                session.rollback()
                st.error(f"Erreur : {e}")
            finally:
                session.close()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Historique
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    all_videos_hist = _load_all_complete()
    annotated = [v for v in all_videos_hist if v["performance_tag"]]

    if not annotated:
        st.info("Aucune vidéo annotée pour l'instant. Utilise l'onglet **⚡ Annoter rapidement** pour commencer.")
    else:
        col_f1, col_f2 = st.columns([3, 2])
        with col_f1:
            search_q = st.text_input("🔍 Rechercher (titre, partenaire...)", placeholder="restaurant, hook, viral...", key="hist_search")
        with col_f2:
            perf_filter = st.multiselect(
                "Filtrer par performance",
                options=["viral", "bon", "moyen", "mauvais"],
                default=["viral", "bon", "moyen", "mauvais"],
                format_func=lambda x: PERF_LABELS.get(x, x),
                key="hist_perf_filter",
            )

        # Apply filters
        filtered = []
        for v in annotated:
            if perf_filter and v["performance_tag"] not in perf_filter:
                continue
            if search_q:
                haystack = f"{v['titre']} {v['partenaire']} {v['nom_compte']} {v.get('note_humaine','') or ''}".lower()
                if search_q.lower() not in haystack:
                    continue
            filtered.append(v)

        st.markdown(f"<p style='color:#666;font-size:0.88rem;margin-bottom:0.8rem;'>{len(filtered)} vidéo{'s' if len(filtered)!=1 else ''} annotée{'s' if len(filtered)!=1 else ''}</p>", unsafe_allow_html=True)

        # Table header
        st.markdown("""
        <table class='hist-table'>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Titre</th>
                    <th>Performance</th>
                    <th>Vues</th>
                    <th>Complétion</th>
                    <th>Date annotée</th>
                </tr>
            </thead>
            <tbody>
        """, unsafe_allow_html=True)

        rows_html = ""
        for v in filtered:
            badge = PERF_BADGE.get(v["performance_tag"], f"<span>{v['performance_tag']}</span>")
            vues_str = f"{v['vues']:,}" if v["vues"] else "—"
            comp_str = f"{int(v['completion_rate'])}%" if v["completion_rate"] else "—"
            date_str = _fmt_date(v["annotee_le"])
            titre_disp = v["titre"][:45] + ("…" if len(v["titre"]) > 45 else "")
            rows_html += f"""
            <tr>
                <td style='color:#666;'>#{v['id']}</td>
                <td><span title='{v["titre"]}'>{titre_disp}</span></td>
                <td>{badge}</td>
                <td style='color:#aaa;'>{vues_str}</td>
                <td style='color:#aaa;'>{comp_str}</td>
                <td style='color:#555;'>{date_str}</td>
            </tr>
            """

        st.markdown(rows_html + "</tbody></table>", unsafe_allow_html=True)

        # Expanded note view for selected video
        if filtered:
            st.markdown("---")
            st.markdown("#### 📝 Voir la note complète")
            note_opts = {f"#{v['id']} — {v['titre'][:40]}": v for v in filtered if v.get("note_humaine")}
            if note_opts:
                chosen_lbl = st.selectbox("Sélectionner une vidéo annotée", list(note_opts.keys()), key="hist_note_sel")
                chosen_v = note_opts[chosen_lbl]
                note_txt = chosen_v["note_humaine"] or ""
                if note_txt:
                    st.markdown(f"```\n{note_txt}\n```")
                else:
                    st.caption("Aucune note textuelle pour cette vidéo.")
            else:
                st.caption("Aucune note textuelle dans la sélection.")
