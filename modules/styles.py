"""CSS Insolit Studio — couleurs de marque partagées entre toutes les pages."""

INSOLIT_CSS = """
<style>
/* ── Couleurs Insolit ────────────────────────────────────── */
/* Magenta  : #ff00a4 */
/* Bleu     : #0000ff */
/* Cyan     : #01f0fc */
/* Fond     : #000000 */

/* ── Base ───────────────────────────────────────────────── */
.stApp { background-color: #000000 !important; color: #ffffff !important; }
body { background-color: #000000 !important; }

/* ── Sidebar ─────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #050505 !important;
    border-right: 1px solid #111 !important;
}
[data-testid="stSidebar"] * { color: #ffffff !important; }
[data-testid="stSidebarNav"] a { color: #888 !important; font-size: 0.9rem; }
[data-testid="stSidebarNav"] a:hover { color: #ff00a4 !important; }

/* ── Cards ───────────────────────────────────────────────── */
.card {
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 1rem;
}
.card-pink  { border-left: 4px solid #ff00a4; }
.card-blue  { border-left: 4px solid #0000ff; }
.card-cyan  { border-left: 4px solid #01f0fc; }

/* ── Boutons ─────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #ff00a4, #0000ff) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    opacity: 0.85 !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #1a1a1a !important;
    color: #555 !important;
}

/* ── Inputs ──────────────────────────────────────────────── */
.stTextInput input,
.stTextArea textarea,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: #0a0a0a !important;
    color: #ffffff !important;
    border-color: #222 !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus {
    border-color: #ff00a4 !important;
    box-shadow: 0 0 0 1px #ff00a4 !important;
}

/* ── Métriques ───────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #0a0a0a;
    border-radius: 8px;
    padding: 0.8rem;
    border: 1px solid #1a1a1a;
}
[data-testid="stMetricValue"] { color: #ff00a4 !important; }
[data-testid="stMetricLabel"] { color: #888 !important; }
[data-testid="stMetricDelta"] { color: #01f0fc !important; }

/* ── Tabs ────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: #0a0a0a;
    border-radius: 8px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] { color: #888 !important; }
.stTabs [aria-selected="true"] {
    color: #ff00a4 !important;
    border-bottom: 2px solid #ff00a4 !important;
    background: transparent !important;
}

/* ── Progress ────────────────────────────────────────────── */
.stProgress > div > div {
    background: linear-gradient(90deg, #0000ff, #01f0fc, #ff00a4) !important;
}

/* ── Alertes ─────────────────────────────────────────────── */
.stAlert { border-radius: 8px !important; }
.stSuccess { border-left: 4px solid #01f0fc !important; }
.stWarning { border-left: 4px solid #ff00a4 !important; }
.stError   { border-left: 4px solid #ff0044 !important; }
.stInfo    { border-left: 4px solid #0000ff !important; }

/* ── Expander ────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: #0a0a0a !important;
    border: 1px solid #1a1a1a !important;
    border-radius: 8px !important;
    color: #ffffff !important;
}
.streamlit-expanderContent {
    background: #050505 !important;
    border: 1px solid #1a1a1a !important;
}

/* ── Dataframe ───────────────────────────────────────────── */
[data-testid="stDataFrame"] { background: #0a0a0a !important; }
.dataframe { background: #0a0a0a !important; color: #fff !important; }

/* ── Scrollbar ───────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #000; }
::-webkit-scrollbar-thumb { background: #ff00a4; border-radius: 2px; }

/* ── Slider ──────────────────────────────────────────────── */
[data-testid="stSlider"] > div > div > div {
    background: linear-gradient(90deg, #0000ff, #ff00a4) !important;
}

/* ── Radio ───────────────────────────────────────────────── */
[data-testid="stRadio"] label { color: #fff !important; }

/* ── Divider ─────────────────────────────────────────────── */
hr { border-color: #111 !important; }

/* ── Badges ──────────────────────────────────────────────── */
.badge-viral { background:#ff00a4; color:#fff; padding:2px 10px; border-radius:12px; font-size:.75em; font-weight:700; }
.badge-bon   { background:#01f0fc; color:#000; padding:2px 10px; border-radius:12px; font-size:.75em; font-weight:700; }
.badge-moyen { background:#0000ff; color:#fff; padding:2px 10px; border-radius:12px; font-size:.75em; font-weight:700; }
.badge-mauvais { background:#333; color:#fff; padding:2px 10px; border-radius:12px; font-size:.75em; font-weight:700; }

/* ── Logo ────────────────────────────────────────────────── */
.logo-text { font-size:1.5rem; font-weight:900; color:#ff00a4; letter-spacing:-0.5px; }
.logo-sub  { font-size:0.65rem; color:#444; letter-spacing:3px; text-transform:uppercase; }

/* ── Titres ──────────────────────────────────────────────── */
h1 { color: #ff00a4 !important; }
h2 { color: #ffffff !important; }
h3 { color: #ffffff !important; }

/* ── Caption / small text ────────────────────────────────── */
.stCaption, small { color: #555 !important; }

/* ── Mobile ──────────────────────────────────────────────── */
@media(max-width:768px) {
    .block-container { padding-left:.5rem!important; padding-right:.5rem!important; }
}
</style>
"""


def apply_styles():
    """À appeler en haut de chaque page."""
    import streamlit as st
    st.markdown(INSOLIT_CSS, unsafe_allow_html=True)
