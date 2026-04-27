import json
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Patterns — Insolit Studio", page_icon="📊", layout="wide")

from modules.styles import apply_styles
apply_styles()

st.markdown('<h1 style="color:#ff00a4;font-weight:900;">📊 Patterns & Insights</h1>', unsafe_allow_html=True)

from modules.database import get_all_videos_with_stats, get_precision_level, get_session, AnalyseCreative, Stats, Video

nb_annotees, niveau = get_precision_level()

if nb_annotees < 10:
    manquantes = 10 - nb_annotees
    st.warning(f"⚠️ Analyse encore **{manquantes} vidéo{'s' if manquantes > 1 else ''}** avec enrichissement pour débloquer les patterns.")
    st.info(f"Vidéos annotées actuellement : **{nb_annotees}/10**")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
            <h3 style="color:#FF4444;">🔒 Graphiques verrouillés</h3>
            <p>Débloque avec 10 vidéos annotées</p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="card">
            <h3 style="color:#FF4444;">🔒 Rapport IA verrouillé</h3>
            <p>Débloque avec 10 vidéos annotées</p>
        </div>
        """, unsafe_allow_html=True)
    st.stop()

# ─── Chargement des données ───────────────────────────────────────────────────
all_videos = get_all_videos_with_stats()
annotated = [v for v in all_videos if v.get("performance_tag")]

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

df = pd.DataFrame(annotated)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_analyse, tab_compare = st.tabs(["📊 Analyse & Graphiques", "⚡ Marche vs Marche Pas"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Analyse & Graphiques
# ══════════════════════════════════════════════════════════════════════════════
with tab_analyse:

    # ─── 4 métriques clés ─────────────────────────────────────────────────────
    st.markdown("### Métriques clés")
    col1, col2, col3, col4 = st.columns(4)

    virales = df[df["performance_tag"] == "viral"] if not df.empty else pd.DataFrame()
    bonnes = df[df["performance_tag"].isin(["viral", "bon"])] if not df.empty else pd.DataFrame()

    with col1:
        if not virales.empty and "duree_secondes" in virales.columns:
            duree_opt = virales["duree_secondes"].mean()
            st.metric("Durée optimale", f"{duree_opt:.0f}s")
        else:
            st.metric("Durée optimale", "—")

    with col2:
        if not bonnes.empty and "rythme_coupes_par_seconde" in bonnes.columns:
            rythme_opt = bonnes["rythme_coupes_par_seconde"].mean()
            st.metric("Rythme optimal", f"{rythme_opt:.2f} c/s")
        else:
            st.metric("Rythme optimal", "—")

    with col3:
        if not df.empty and "hook_score" in df.columns:
            hook_virales = virales["hook_score"].mean() if not virales.empty else 0
            st.metric("Hook score moyen viral", f"{hook_virales:.1f}/10")
        else:
            st.metric("Hook moyen viral", "—")

    with col4:
        if not df.empty and "hook_type" in df.columns:
            hook_types_virales = virales["hook_type"].mode()
            top_hook = hook_types_virales.iloc[0] if not hook_types_virales.empty else "—"
            st.metric("Hook gagnant", top_hook)
        else:
            st.metric("Hook gagnant", "—")

    # ─── Graphique 1 — Durée vs Performance ───────────────────────────────────
    if not df.empty and "duree_secondes" in df.columns and "performance_tag" in df.columns:
        st.markdown("### 📈 Durée vs Performance")

        color_map = {"viral": "#ff00a4", "bon": "#01f0fc", "moyen": "#0000ff", "mauvais": "#333333"}
        fig1 = px.scatter(
            df.dropna(subset=["duree_secondes", "score_potentiel"]),
            x="duree_secondes",
            y="score_potentiel",
            color="performance_tag",
            color_discrete_map=color_map,
            hover_data=["titre", "nom_compte", "vues"],
            labels={
                "duree_secondes": "Durée (secondes)",
                "score_potentiel": "Score potentiel",
                "performance_tag": "Performance"
            },
            title="Durée vs Score potentiel"
        )
        fig1.update_layout(
            paper_bgcolor="#0a0a0a",
            plot_bgcolor="#0a0a0a",
            font_color="#ffffff",
            title_font_color="#ff00a4",
        )
        st.plotly_chart(fig1, use_container_width=True)

    # ─── Graphique 2 — Types de hook ──────────────────────────────────────────
    session = get_session()
    try:
        hook_data = []
        rows = (
            session.query(AnalyseCreative, Stats)
            .join(Stats, AnalyseCreative.video_id == Stats.video_id)
            .filter(Stats.performance_tag.isnot(None))
            .all()
        )
        for ac, stat in rows:
            if ac.hook_type:
                hook_data.append({
                    "hook_type": ac.hook_type,
                    "performance_tag": stat.performance_tag,
                    "hook_score": ac.hook_score,
                })
    finally:
        session.close()

    if hook_data:
        st.markdown("### 🎣 Types de hook par performance")
        df_hook = pd.DataFrame(hook_data)
        success_rate = (
            df_hook.groupby("hook_type")
            .apply(lambda x: (x["performance_tag"].isin(["viral", "bon"]).sum() / len(x)) * 100)
            .reset_index()
            .rename(columns={0: "taux_succes"})
            .sort_values("taux_succes", ascending=True)
        )

        fig2 = px.bar(
            success_rate,
            x="taux_succes",
            y="hook_type",
            orientation="h",
            color="taux_succes",
            color_continuous_scale=["#0a0a0a", "#0000ff", "#ff00a4"],
            labels={"taux_succes": "Taux de succès (%)", "hook_type": "Type de hook"},
            title="Taux de succès par type de hook"
        )
        fig2.update_layout(
            paper_bgcolor="#0a0a0a", plot_bgcolor="#0a0a0a",
            font_color="#ffffff", title_font_color="#ff00a4",
            showlegend=False
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ─── Graphique 3 — Matrice de corrélation ─────────────────────────────────
    st.markdown("### 🔬 Matrice de corrélation")

    if not df.empty and len(df) >= 5:
        perf_order = ["viral", "bon", "moyen", "mauvais"]
        df_perf = df[df["performance_tag"].isin(perf_order)].copy()

        if len(df_perf) > 0:
            matrix_data = {}

            def _safe_pct(series, condition):
                if len(series) == 0:
                    return 0
                return round((condition.sum() / len(series)) * 100)

            for perf in perf_order:
                sub = df_perf[df_perf["performance_tag"] == perf]
                if len(sub) == 0:
                    matrix_data[perf] = ["—"] * 6
                    continue
                matrix_data[perf] = [
                    f"{_safe_pct(sub, sub.get('hook_score', pd.Series(dtype=float)) >= 7)}%" if 'hook_score' in sub else "—",
                    f"{_safe_pct(sub, sub.get('nb_plans', pd.Series(dtype=int)) > 5)}%" if 'nb_plans' in sub else "—",
                    f"{_safe_pct(sub, sub.get('duree_secondes', pd.Series(dtype=float)) < 30)}%" if 'duree_secondes' in sub else "—",
                    f"{_safe_pct(sub, sub.get('score_potentiel', pd.Series(dtype=float)) >= 7)}%" if 'score_potentiel' in sub else "—",
                    f"{_safe_pct(sub, sub.get('rythme_coupes_par_seconde', pd.Series(dtype=float)) > 0.3)}%" if 'rythme_coupes_par_seconde' in sub else "—",
                    f"{_safe_pct(sub, sub.get('completion_rate', pd.Series(dtype=float)) > 60)}%" if 'completion_rate' in sub else "—",
                ]

            criterias = [
                "Hook score ≥ 7",
                "Plus de 5 plans",
                "Durée < 30s",
                "Score potentiel ≥ 7",
                "Rythme > 0.3 c/s",
                "Completion > 60%",
            ]

            matrix_df = pd.DataFrame(matrix_data, index=criterias)
            st.dataframe(
                matrix_df.style.set_properties(**{
                    "background-color": "#1a1a1a",
                    "color": "#f0f0f0",
                    "border": "1px solid #2a2a2a",
                }),
                use_container_width=True
            )
    else:
        st.info("Matrice disponible avec 5+ vidéos annotées.")

    # ─── Top 5 vidéos ─────────────────────────────────────────────────────────
    st.markdown("### 🏆 Top 5 vidéos les plus performantes")
    top5 = sorted(annotated, key=lambda v: v.get("vues") or 0, reverse=True)[:5]

    if top5:
        for i, v in enumerate(top5):
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                with c1:
                    st.markdown(f"**{i+1}. {v.get('titre', '—')[:60]}**")
                    st.caption(f"@{v.get('nom_compte', '—')} · {v.get('categorie', '—')}")
                with c2:
                    vues = v.get("vues", 0) or 0
                    st.metric("Vues", f"{vues:,}")
                with c3:
                    st.metric("Score", f"{v.get('score_potentiel', '—')}/10")
                with c4:
                    st.metric("Hook", f"{v.get('hook_score', '—')}/10")

    # ─── Rapport IA ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🤖 Rapport de patterns par IA")

    if st.button("🤖 Générer le rapport de patterns", use_container_width=True):
        from modules.claude_mod import generate_patterns_report

        videos_for_report = [
            {
                "titre": v.get("titre"),
                "duree_secondes": v.get("duree_secondes"),
                "nb_plans": v.get("nb_plans"),
                "hook_score": v.get("hook_score"),
                "score_potentiel": v.get("score_potentiel"),
                "vues": v.get("vues"),
                "performance_tag": v.get("performance_tag"),
                "completion_rate": v.get("completion_rate"),
                "rythme": v.get("rythme_coupes_par_seconde"),
            }
            for v in annotated
        ]

        with st.spinner("Claude analyse ta base..."):
            rapport, usage = generate_patterns_report(videos_for_report)

        st.markdown(rapport)
        if usage:
            st.caption(f"Coût estimé : ~${usage.get('cout_estime', 0):.4f}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Comparaison Marche vs Marche Pas
# ══════════════════════════════════════════════════════════════════════════════
with tab_compare:

    st.markdown("""
    <div style="margin-bottom:1rem;">
        <p style="color:#888;font-size:0.9rem;">
            Compare tes <strong style="color:#00cc66;">Top 5 vidéos qui cartonnent</strong>
            vs tes <strong style="color:#ef4444;">5 qui n'ont pas marché</strong>
            — identifie les différences clés.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Séparer les vidéos
    top_videos  = sorted(
        [v for v in annotated if v.get("performance_tag") in ("viral", "bon")],
        key=lambda v: (v.get("vues") or 0) + (float(v.get("score_potentiel") or 0) * 1000),
        reverse=True
    )[:5]

    flop_videos = sorted(
        [v for v in annotated if v.get("performance_tag") in ("moyen", "mauvais")],
        key=lambda v: (v.get("vues") or 0),
        reverse=False
    )[:5]

    if not top_videos and not flop_videos:
        st.info("Annote tes vidéos depuis la page **⚡ Enrichir** pour débloquer la comparaison.")
        st.stop()

    # ── CSS comparaison ────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .comp-card-top {
        background: #001a0a;
        border: 1px solid #22c55e;
        border-left: 4px solid #22c55e;
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.55rem;
    }
    .comp-card-flop {
        background: #1a0000;
        border: 1px solid #ef4444;
        border-left: 4px solid #ef4444;
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.55rem;
    }
    .comp-title { font-weight: 700; font-size: 0.9rem; color: #fff; }
    .comp-meta  { font-size: 0.78rem; color: #888; margin-top: 3px; }
    .comp-stat  { font-size: 0.82rem; color: #aaa; margin-top: 4px; }
    </style>
    """, unsafe_allow_html=True)

    col_top, col_flop = st.columns(2, gap="large")

    def _fmt_vues(n):
        if not n: return "— vues"
        n = int(n)
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M vues"
        if n >= 1_000:     return f"{n//1_000}k vues"
        return f"{n} vues"

    def _fmt_dur(s):
        if not s: return "—"
        s = int(s)
        return f"{s//60}m{s%60:02d}s" if s >= 60 else f"{s}s"

    # ── Colonne TOP ────────────────────────────────────────────────────────────
    with col_top:
        st.markdown(f"""
        <div style="background:#001a0a;border:1px solid #22c55e;border-radius:8px;
                    padding:0.6rem 1rem;margin-bottom:1rem;font-weight:700;color:#22c55e;">
            🔥 TOP {len(top_videos)} — CE QUI MARCHE
        </div>
        """, unsafe_allow_html=True)

        if not top_videos:
            st.markdown("<div style='color:#555;'>Aucune vidéo bonne/virale annotée.</div>", unsafe_allow_html=True)
        else:
            for i, v in enumerate(top_videos, 1):
                thumb_path = f"./screenshots/{v.get('video_id', '')}/plan_01.jpg"
                titre_short = (v.get("titre") or "—")[:45]
                vues_str   = _fmt_vues(v.get("vues"))
                dur_str    = _fmt_dur(v.get("duree_secondes"))
                hook_type  = v.get("hook_type") or "—"
                hook_score = v.get("hook_score") or "—"
                score_pot  = v.get("score_potentiel") or "—"
                nb_plans   = v.get("nb_plans") or "—"
                perf_badge = "🔥 VIRAL" if v.get("performance_tag") == "viral" else "✅ BON"

                col_th, col_inf = st.columns([1, 4])
                with col_th:
                    if os.path.exists(thumb_path):
                        st.image(thumb_path, width=70)
                    else:
                        st.markdown("""
                        <div style='width:70px;height:50px;background:#0a2a0a;border-radius:6px;
                                    display:flex;align-items:center;justify-content:center;
                                    font-size:1.3rem;'>🎬</div>
                        """, unsafe_allow_html=True)
                with col_inf:
                    st.markdown(f"""
                    <div class='comp-card-top'>
                        <div class='comp-title'>#{i} {titre_short}</div>
                        <div class='comp-meta'>{vues_str} · {dur_str} · <strong style="color:#22c55e;">{perf_badge}</strong></div>
                        <div class='comp-stat'>
                            Hook : <strong>{hook_type}</strong> ({hook_score}/10) ·
                            Score : <strong style="color:#ff00a4;">{score_pot}/10</strong> ·
                            {nb_plans} plans
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # ── Colonne FLOP ───────────────────────────────────────────────────────────
    with col_flop:
        st.markdown(f"""
        <div style="background:#1a0000;border:1px solid #ef4444;border-radius:8px;
                    padding:0.6rem 1rem;margin-bottom:1rem;font-weight:700;color:#ef4444;">
            ❌ FLOP {len(flop_videos)} — CE QUI N'A PAS MARCHÉ
        </div>
        """, unsafe_allow_html=True)

        if not flop_videos:
            st.markdown("<div style='color:#555;'>Aucune vidéo moyen/mauvais annotée.</div>", unsafe_allow_html=True)
        else:
            for i, v in enumerate(flop_videos, 1):
                thumb_path = f"./screenshots/{v.get('video_id', '')}/plan_01.jpg"
                titre_short = (v.get("titre") or "—")[:45]
                vues_str   = _fmt_vues(v.get("vues"))
                dur_str    = _fmt_dur(v.get("duree_secondes"))
                hook_type  = v.get("hook_type") or "—"
                hook_score = v.get("hook_score") or "—"
                score_pot  = v.get("score_potentiel") or "—"
                nb_plans   = v.get("nb_plans") or "—"
                perf_badge = "😐 MOYEN" if v.get("performance_tag") == "moyen" else "❌ MAUVAIS"
                badge_color = "#f59e0b" if v.get("performance_tag") == "moyen" else "#ef4444"

                col_th, col_inf = st.columns([1, 4])
                with col_th:
                    if os.path.exists(thumb_path):
                        st.image(thumb_path, width=70)
                    else:
                        st.markdown("""
                        <div style='width:70px;height:50px;background:#2a0000;border-radius:6px;
                                    display:flex;align-items:center;justify-content:center;
                                    font-size:1.3rem;'>🎬</div>
                        """, unsafe_allow_html=True)
                with col_inf:
                    st.markdown(f"""
                    <div class='comp-card-flop'>
                        <div class='comp-title'>#{i} {titre_short}</div>
                        <div class='comp-meta'>{vues_str} · {dur_str} · <strong style="color:{badge_color};">{perf_badge}</strong></div>
                        <div class='comp-stat'>
                            Hook : <strong>{hook_type}</strong> ({hook_score}/10) ·
                            Score : <strong style="color:#ff00a4;">{score_pot}/10</strong> ·
                            {nb_plans} plans
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # ── Analyse IA des différences ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🤖 Analyse Claude — Pourquoi l'écart ?")

    if top_videos and flop_videos:
        if st.button("⚡ Analyser les différences avec Claude", use_container_width=True, type="primary",
                     key="btn_compare_ia"):
            from modules.claude_mod import _call_claude, MODEL_FAST

            top_summary = "\n".join([
                f"- «{v.get('titre','?')[:50]}» | {_fmt_vues(v.get('vues'))} | "
                f"Hook: {v.get('hook_type','?')} ({v.get('hook_score','?')}/10) | "
                f"Durée: {_fmt_dur(v.get('duree_secondes'))} | Score: {v.get('score_potentiel','?')}/10 | "
                f"{v.get('nb_plans','?')} plans"
                for v in top_videos
            ])
            flop_summary = "\n".join([
                f"- «{v.get('titre','?')[:50]}» | {_fmt_vues(v.get('vues'))} | "
                f"Hook: {v.get('hook_type','?')} ({v.get('hook_score','?')}/10) | "
                f"Durée: {_fmt_dur(v.get('duree_secondes'))} | Score: {v.get('score_potentiel','?')}/10 | "
                f"{v.get('nb_plans','?')} plans"
                for v in flop_videos
            ])

            prompt = f"""Tu es un expert en contenu TikTok/Instagram pour les restaurants et lieux de vie parisiens.

VIDÉOS QUI ONT MARCHÉ (viral/bon) :
{top_summary}

VIDÉOS QUI N'ONT PAS MARCHÉ (moyen/mauvais) :
{flop_summary}

Analyse les différences clés entre ces deux groupes. Réponds en markdown avec :

## 🎯 Les 3 différences cruciales
(liste numérotée, concrète et actionnable)

## ✅ Ce qui fait marcher les tops
(2-3 points clés)

## ❌ Ce qui plombe les flops
(2-3 points clés)

## 💡 Action immédiate
(1 seule recommandation ultra-concrète pour la prochaine vidéo)

Sois direct, précis, sans blabla."""

            with st.spinner("Claude compare les deux groupes..."):
                rapport_compare, usage_compare = _call_claude(
                    prompt=prompt,
                    max_tokens=800,
                    model=MODEL_FAST,
                    use_context=True,
                )

            st.markdown(rapport_compare)
            if usage_compare:
                cout = usage_compare.get("cout_estime", 0)
                st.caption(f"Analyse générée · Coût ~${cout:.4f}")

            st.session_state["last_compare_rapport"] = rapport_compare

    elif not top_videos:
        st.info("Annote au moins 1 vidéo **viral/bon** pour activer la comparaison IA.")
    elif not flop_videos:
        st.info("Annote au moins 1 vidéo **moyen/mauvais** pour activer la comparaison IA.")

    # Afficher le dernier rapport si déjà généré
    if "last_compare_rapport" in st.session_state and not st.session_state.get("btn_compare_ia"):
        with st.expander("📄 Dernier rapport de comparaison", expanded=False):
            st.markdown(st.session_state["last_compare_rapport"])
