import json
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Bibliothèque — Insolit Studio", page_icon="📚", layout="wide")

from modules.styles import apply_styles
apply_styles()

st.markdown("""
<style>
.video-card {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.2s;
}
.video-card:hover { border-color: #ff00a4; }
.video-card-selected {
    background: #0a0a0a;
    border: 2px solid #ff00a4;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.5rem;
}
.delete-zone {
    background: #150005;
    border: 2px dashed #ff00a4;
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 1.5rem;
}
.count-pill {
    background: #ff00a4;
    color: white;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.8rem;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 style="color:#ff00a4;font-weight:900;">📚 Ma bibliothèque</h1>', unsafe_allow_html=True)

from modules.database import get_all_videos_with_stats, get_precision_level, delete_video
from modules.enrichment import get_precision_badge, PERFORMANCE_LABELS, PERFORMANCE_COLORS

# ─── Initialisation session state ────────────────────────────────────────────
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = set()
if "delete_mode" not in st.session_state:
    st.session_state.delete_mode = False
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = False

# ─── Indicateur précision ─────────────────────────────────────────────────────
nb_annotees, niveau = get_precision_level()
st.markdown(get_precision_badge(nb_annotees, niveau), unsafe_allow_html=True)

# ─── Barre d'outils ───────────────────────────────────────────────────────────
st.markdown("---")
col_search, col_delete_toggle = st.columns([4, 1])

with col_search:
    search_query = st.text_input(
        "🔍",
        placeholder="Recherche — ex: hook prix choc, extérieur, visage...",
        label_visibility="collapsed",
        key="search_query"
    )

with col_delete_toggle:
    if st.button(
        "🗑️ Supprimer" if not st.session_state.delete_mode else "✕ Annuler",
        use_container_width=True,
        type="secondary" if not st.session_state.delete_mode else "primary",
    ):
        st.session_state.delete_mode = not st.session_state.delete_mode
        st.session_state.selected_ids = set()
        st.session_state.confirm_delete = False
        st.rerun()

# ─── Zone de suppression (si mode actif) ─────────────────────────────────────
if st.session_state.delete_mode:
    nb_sel = len(st.session_state.selected_ids)
    st.markdown(f"""
    <div class="delete-zone">
        <strong style="color:#ff00a4;">🗑️ Mode suppression actif</strong>
        &nbsp;&nbsp;
        <span class="count-pill">{nb_sel} sélectionnée{'s' if nb_sel > 1 else ''}</span>
        <br>
        <span style="color:#888;font-size:0.85rem;">
            Coche les vidéos à supprimer, puis confirme. La suppression est définitive (DB + fichiers).
        </span>
    </div>
    """, unsafe_allow_html=True)

    if nb_sel > 0:
        col_sel, col_conf, col_cancel = st.columns([2, 2, 1])
        with col_sel:
            st.caption(f"**{nb_sel}** vidéo{'s' if nb_sel > 1 else ''} sélectionnée{'s' if nb_sel > 1 else ''}")
        with col_conf:
            if not st.session_state.confirm_delete:
                if st.button(f"⚠️ Supprimer {nb_sel} vidéo{'s' if nb_sel > 1 else ''}", type="primary", use_container_width=True):
                    st.session_state.confirm_delete = True
                    st.rerun()
            else:
                st.markdown('<p style="color:#ff00a4;font-weight:700;">⚠️ Confirme la suppression :</p>', unsafe_allow_html=True)
                if st.button(f"🔴 OUI — Supprimer définitivement", type="primary", use_container_width=True):
                    errors = []
                    for vid_id in list(st.session_state.selected_ids):
                        res = delete_video(vid_id)
                        if not res["success"]:
                            errors.append(res["message"])
                    st.session_state.selected_ids = set()
                    st.session_state.delete_mode = False
                    st.session_state.confirm_delete = False
                    if errors:
                        st.error(f"Erreurs: {', '.join(errors)}")
                    else:
                        st.success(f"✅ Supprimé avec succès !")
                    st.rerun()
        with col_cancel:
            if st.session_state.confirm_delete:
                if st.button("Non, annuler", use_container_width=True):
                    st.session_state.confirm_delete = False
                    st.rerun()

# ─── Recherche sémantique (exemples rapides) ──────────────────────────────────
ex_cols = st.columns(4)
examples = [
    "hook prix choc",
    "extérieur plein air",
    "réaction visage",
    "texte à l'écran",
]
for i, ex in enumerate(examples):
    with ex_cols[i]:
        if st.button(f'"{ex}"', key=f"ex_{i}", use_container_width=True):
            st.session_state["search_query"] = ex
            search_query = ex

# ─── Filtres ──────────────────────────────────────────────────────────────────
st.markdown("---")
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    filter_source = st.selectbox(
        "Source", ["Toutes", "Mon compte", "Concurrent", "Inspiration", "Secteur"],
        key="filter_source"
    )
with col2:
    filter_perf = st.selectbox(
        "Performance", ["Toutes", "🔥 Viral", "✅ Bon", "😐 Moyen", "❌ Mauvais", "⬜ Non annoté"],
        key="filter_perf"
    )
with col3:
    filter_cat = st.selectbox(
        "Catégorie",
        ["Toutes", "Restaurant", "Bar", "Café", "Expérience", "Bon plan", "Tendance food", "Lifestyle", "Autre"],
        key="filter_cat"
    )
with col4:
    filter_sort = st.selectbox(
        "Trier par", ["Plus récent", "Plus de vues", "Score le plus élevé", "Hook le plus fort", "Durée croissante"],
        key="filter_sort"
    )
with col5:
    view_mode = st.selectbox("Affichage", ["Grille (3 col)", "Grille (4 col)", "Liste"], key="view_mode")

# ─── Chargement des vidéos ────────────────────────────────────────────────────
all_videos = get_all_videos_with_stats()

# Filtres
source_map = {"Mon compte": "mon_compte", "Concurrent": "concurrent", "Inspiration": "inspiration", "Secteur": "secteur"}
if filter_source != "Toutes":
    all_videos = [v for v in all_videos if v.get("type_source") == source_map.get(filter_source)]

perf_map = {"🔥 Viral": "viral", "✅ Bon": "bon", "😐 Moyen": "moyen", "❌ Mauvais": "mauvais"}
if filter_perf == "⬜ Non annoté":
    all_videos = [v for v in all_videos if not v.get("performance_tag")]
elif filter_perf != "Toutes":
    tag = perf_map.get(filter_perf)
    all_videos = [v for v in all_videos if v.get("performance_tag") == tag]

if filter_cat != "Toutes":
    all_videos = [v for v in all_videos if v.get("categorie") == filter_cat]

# Recherche textuelle locale
if search_query:
    q = search_query.lower()
    all_videos = [
        v for v in all_videos
        if q in (v.get("titre") or "").lower()
        or q in (v.get("hook_texte") or "").lower()
        or q in (v.get("nom_compte") or "").lower()
        or q in (v.get("partenaire") or "").lower()
        or q in (v.get("categorie") or "").lower()
    ]

# Tri
if filter_sort == "Plus de vues":
    all_videos.sort(key=lambda v: v.get("vues") or 0, reverse=True)
elif filter_sort == "Score le plus élevé":
    all_videos.sort(key=lambda v: v.get("score_potentiel") or 0, reverse=True)
elif filter_sort == "Hook le plus fort":
    all_videos.sort(key=lambda v: v.get("hook_score") or 0, reverse=True)
elif filter_sort == "Durée croissante":
    all_videos.sort(key=lambda v: v.get("duree_secondes") or 0)

# ─── Header résultats ─────────────────────────────────────────────────────────
st.markdown("---")
h_col1, h_col2 = st.columns([3, 1])
with h_col1:
    total = len(all_videos)
    st.caption(f"**{total}** vidéo{'s' if total != 1 else ''} affichée{'s' if total != 1 else ''}")
with h_col2:
    if st.session_state.delete_mode and all_videos:
        if st.button("Tout sélectionner", use_container_width=True):
            st.session_state.selected_ids = {v["id"] for v in all_videos}
            st.rerun()

if not all_videos:
    st.markdown("""
    <div style="text-align:center;padding:4rem 0;color:#444;">
        <div style="font-size:3rem;">📭</div>
        <div style="margin-top:1rem;">Aucune vidéo trouvée</div>
        <div style="font-size:0.85rem;color:#333;margin-top:0.5rem;">
            Essaie d'autres filtres ou analyse ta première vidéo
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─── Affichage ────────────────────────────────────────────────────────────────
nb_cols = 4 if view_mode == "Grille (4 col)" else (1 if view_mode == "Liste" else 3)

if view_mode == "Liste":
    # ── Vue liste ─────────────────────────────────────────────────────────────
    for video in all_videos:
        vid_id = video["id"]
        is_selected = vid_id in st.session_state.selected_ids
        perf = video.get("performance_tag", "")
        perf_label = PERFORMANCE_LABELS.get(perf, "")
        perf_color = PERFORMANCE_COLORS.get(perf, "#333")

        with st.container():
            cols = st.columns([0.4, 3, 1, 1, 1, 1, 0.6] if not st.session_state.delete_mode else [0.4, 0.3, 3, 1, 1, 1, 1])

            if st.session_state.delete_mode:
                with cols[0]:
                    checked = st.checkbox("", key=f"chk_{vid_id}", value=is_selected, label_visibility="collapsed")
                    if checked and vid_id not in st.session_state.selected_ids:
                        st.session_state.selected_ids.add(vid_id)
                        st.rerun()
                    elif not checked and vid_id in st.session_state.selected_ids:
                        st.session_state.selected_ids.discard(vid_id)
                        st.rerun()
                offset = 1
            else:
                offset = 0

            with cols[offset]:
                shot_file = os.path.join("./screenshots", str(vid_id), "plan_01.jpg")
                if os.path.exists(shot_file):
                    st.image(shot_file, width=60)
                else:
                    st.markdown('<div style="width:60px;height:60px;background:#111;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🎬</div>', unsafe_allow_html=True)

            with cols[offset + 1]:
                st.markdown(f"**{video.get('titre', 'Sans titre')[:55]}**")
                st.caption(f"@{video.get('nom_compte','—')} · {video.get('categorie','—')} · {video.get('duree_secondes',0):.0f}s")

            with cols[offset + 2]:
                vues = video.get("vues") or 0
                st.markdown(f"👁 **{vues:,}**" if vues else "👁 —")

            with cols[offset + 3]:
                score = video.get("score_potentiel")
                color = "#ff00a4" if score and score >= 7 else "#888"
                st.markdown(f'<span style="color:{color};font-weight:700;">{score}/10</span>' if score else "—", unsafe_allow_html=True)

            with cols[offset + 4]:
                if perf:
                    st.markdown(f'<span style="background:{perf_color};color:{"#000" if perf=="bon" else "#fff"};padding:2px 8px;border-radius:10px;font-size:0.75em;font-weight:700;">{perf_label}</span>', unsafe_allow_html=True)
                else:
                    st.caption("non annoté")

            with cols[offset + 5]:
                if not st.session_state.delete_mode:
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("📊", key=f"voir_l_{vid_id}", help="Voir détails", use_container_width=True):
                            st.session_state["view_video_id"] = vid_id
                    with c2:
                        if st.button("🎯", key=f"brief_l_{vid_id}", help="Générer brief", use_container_width=True):
                            st.session_state["brief_from_video_id"] = vid_id
                            st.switch_page("pages/4_Generer.py")

        st.divider()

else:
    # ── Vue grille ────────────────────────────────────────────────────────────
    cols = st.columns(nb_cols)
    for idx, video in enumerate(all_videos):
        vid_id = video["id"]
        is_selected = vid_id in st.session_state.selected_ids
        col = cols[idx % nb_cols]

        with col:
            # Screenshot
            shot_file = os.path.join("./screenshots", str(vid_id), "plan_01.jpg")
            if os.path.exists(shot_file):
                st.image(shot_file, use_container_width=True)
            else:
                st.markdown(f"""
                <div style="background:#111;height:110px;border-radius:8px;
                display:flex;align-items:center;justify-content:center;color:#333;font-size:2rem;">🎬</div>
                """, unsafe_allow_html=True)

            perf = video.get("performance_tag", "")
            perf_label = PERFORMANCE_LABELS.get(perf, "")
            perf_color = PERFORMANCE_COLORS.get(perf, "#333")
            score = video.get("score_potentiel")
            score_color = "#ff00a4" if score and score >= 7 else ("#01f0fc" if score and score >= 5 else "#555")

            st.markdown(f"""
            <div style="padding:0.4rem 0;">
                <div style="font-weight:700;font-size:0.85rem;line-height:1.3;">{video.get('titre','Sans titre')[:45]}</div>
                <div style="color:#666;font-size:0.75rem;margin-top:2px;">@{video.get('nom_compte','—')}</div>
                <div style="margin-top:4px;display:flex;align-items:center;gap:6px;">
                    <span style="color:#555;font-size:0.75rem;">⏱{video.get('duree_secondes',0):.0f}s</span>
                    <span style="color:#555;font-size:0.75rem;">📐{video.get('nb_plans','?')}</span>
                    <span style="color:{score_color};font-size:0.75rem;font-weight:700;">{score}/10</span>
                </div>
                <div style="margin-top:4px;">
                    {'<span style="background:' + perf_color + ';color:' + ("#000" if perf=="bon" else "#fff") + ';padding:1px 7px;border-radius:10px;font-size:0.7em;font-weight:700;">' + perf_label + '</span>' if perf else '<span style="color:#333;font-size:0.7em;">non annoté</span>'}
                    {f'<span style="color:#666;font-size:0.7rem;margin-left:4px;">{video.get("vues",0):,}v</span>' if video.get("vues") else ''}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.session_state.delete_mode:
                # Checkbox de sélection
                checked = st.checkbox(
                    f"Sélectionner",
                    key=f"chk_g_{vid_id}",
                    value=is_selected,
                )
                if checked and vid_id not in st.session_state.selected_ids:
                    st.session_state.selected_ids.add(vid_id)
                    st.rerun()
                elif not checked and vid_id in st.session_state.selected_ids:
                    st.session_state.selected_ids.discard(vid_id)
                    st.rerun()

                # Suppression rapide (1 vidéo)
                if st.button(f"🗑️ Suppr.", key=f"del1_{vid_id}", use_container_width=True):
                    res = delete_video(vid_id)
                    if res["success"]:
                        st.success(f"Supprimée !")
                    else:
                        st.error(res["message"])
                    st.session_state.selected_ids.discard(vid_id)
                    st.rerun()
            else:
                c_a, c_b = st.columns(2)
                with c_a:
                    if st.button("📊 Voir", key=f"voir_{vid_id}", use_container_width=True):
                        st.session_state["view_video_id"] = vid_id
                with c_b:
                    if st.button("🎯 Brief", key=f"brief_{vid_id}", use_container_width=True):
                        st.session_state["brief_from_video_id"] = vid_id
                        st.switch_page("pages/4_Generer.py")

            st.markdown("<hr style='border:none;border-top:1px solid #111;margin:0.5rem 0;'>", unsafe_allow_html=True)

# ─── Pied de page ─────────────────────────────────────────────────────────────
st.markdown("---")
col_info, col_export = st.columns([3, 1])
with col_info:
    st.caption(f"{total} vidéos · {nb_annotees} annotées · Précision : **{niveau}**")
with col_export:
    if st.button("📊 Exporter Excel", use_container_width=True):
        import pandas as pd
        from io import BytesIO

        df = pd.DataFrame(all_videos)
        cols_keep = [
            "id", "titre", "nom_compte", "type_source", "categorie",
            "duree_secondes", "nb_plans", "hook_score", "score_potentiel",
            "vues", "performance_tag", "completion_rate", "created_at"
        ]
        df = df[[c for c in cols_keep if c in df.columns]]
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Bibliothèque")
        buf.seek(0)
        st.download_button(
            "⬇️ Télécharger",
            data=buf,
            file_name="insolit_bibliotheque.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
