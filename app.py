import os
import logging
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from modules.database import init_db, get_precision_level
from modules.enrichment import get_precision_badge

# ─── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Insolit Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(),
    ]
)

# ─── Init DB ──────────────────────────────────────────────────────────────────
try:
    init_db()
except Exception as e:
    st.error(f"Erreur initialisation base de données : {e}")

# ─── CSS Dark Theme ───────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #000000; color: #ffffff; }
[data-testid="stSidebar"] { background-color: #050505; border-right: 1px solid #111; }
[data-testid="stSidebar"] * { color: #ffffff !important; }
.card { background:#0a0a0a; border:1px solid #1a1a1a; border-radius:12px; padding:1.2rem; margin-bottom:1rem; }
.card-blue  { border-left:4px solid #0000ff; }
.card-cyan  { border-left:4px solid #01f0fc; }
.card-pink  { border-left:4px solid #ff00a4; }
.stTextInput input, .stTextArea textarea, .stSelectbox div {
    background:#0a0a0a !important; color:#ffffff !important; border-color:#222 !important; }
.stButton > button {
    background:linear-gradient(135deg, #ff00a4, #0000ff);
    color:white; border:none; border-radius:8px; font-weight:700; transition:all 0.2s; }
.stButton > button:hover { opacity:0.85; transform:translateY(-1px); }
.stTabs [data-baseweb="tab-list"] { background:#0a0a0a; border-radius:8px; }
.stTabs [data-baseweb="tab"] { color:#888 !important; }
.stTabs [aria-selected="true"] { color:#ff00a4 !important; border-bottom:2px solid #ff00a4; }
[data-testid="stMetric"] { background:#0a0a0a; border-radius:8px; padding:0.8rem; border:1px solid #1a1a1a; }
[data-testid="stMetricValue"] { color:#ff00a4 !important; }
.stProgress > div > div { background:linear-gradient(90deg, #0000ff, #01f0fc, #ff00a4); }
::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background:#000; }
::-webkit-scrollbar-thumb { background:#ff00a4; border-radius:2px; }
.logo-text { font-size:1.5rem; font-weight:900; color:#ff00a4; letter-spacing:-0.5px; }
.logo-sub  { font-size:0.65rem; color:#444; letter-spacing:3px; text-transform:uppercase; }
.badge-viral   { background:#ff00a4; color:#fff; padding:2px 8px; border-radius:12px; font-size:.75em; font-weight:700; }
.badge-bon     { background:#01f0fc; color:#000; padding:2px 8px; border-radius:12px; font-size:.75em; font-weight:700; }
.badge-moyen   { background:#0000ff; color:#fff; padding:2px 8px; border-radius:12px; font-size:.75em; font-weight:700; }
.badge-mauvais { background:#333;    color:#fff; padding:2px 8px; border-radius:12px; font-size:.75em; font-weight:700; }
@media(max-width:768px){.block-container{padding-left:.5rem!important;padding-right:.5rem!important;}}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:1.2rem 0 1.5rem 0;">
        <div class="logo-text">◎ Insolit Studio</div>
        <div class="logo-sub">Analyse · Stratégie · Brief</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Indicateur précision base
    try:
        nb_annotees, niveau = get_precision_level()
        st.markdown(get_precision_badge(nb_annotees, niveau), unsafe_allow_html=True)
    except Exception:
        st.caption("Base de données non initialisée")

    st.divider()

    st.markdown("**Navigation**")
    st.page_link("pages/1_Analyser.py", label="🎬 Analyser une vidéo")
    st.page_link("pages/2_Bibliotheque.py", label="📚 Ma bibliothèque")
    st.page_link("pages/3_Patterns.py", label="📊 Patterns & Insights")
    st.page_link("pages/4_Generer.py", label="✨ Générer un brief")
    st.page_link("pages/5_Compte.py", label="🔭 Analyser un compte")

    st.divider()
    st.caption("Propulsé par TwelveLabs · Whisper · Claude")

# ─── Page principale ──────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 3rem 0 2rem 0;">
    <h1 style="font-size:3rem; font-weight:900; color:#FF4444; margin:0;">🎬 Insolit Studio</h1>
    <p style="color:#888; font-size:1.1rem; margin-top:0.5rem;">
        Analyse vidéo · Recherche sémantique · Génération de briefs
    </p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    <div class="card card-red">
        <div style="font-size:2rem;">🎬</div>
        <div style="font-weight:700; margin-top:0.5rem;">Analyser</div>
        <div style="color:#888; font-size:0.85rem;">TwelveLabs + Whisper + Claude</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="card card-orange">
        <div style="font-size:2rem;">📚</div>
        <div style="font-weight:700; margin-top:0.5rem;">Bibliothèque</div>
        <div style="color:#888; font-size:0.85rem;">Recherche sémantique Marengo</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="card card-red">
        <div style="font-size:2rem;">📊</div>
        <div style="font-weight:700; margin-top:0.5rem;">Patterns</div>
        <div style="color:#888; font-size:0.85rem;">Insights & corrélations</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="card card-orange">
        <div style="font-size:2rem;">✨</div>
        <div style="font-weight:700; margin-top:0.5rem;">Brief</div>
        <div style="color:#888; font-size:0.85rem;">Génération data-driven</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div style="text-align:center; padding: 2rem 0; color:#444;">
    ← Utilise le menu de navigation pour commencer
</div>
""", unsafe_allow_html=True)
