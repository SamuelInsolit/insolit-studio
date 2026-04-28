"""
Constantes partagées entre toutes les pages Insolit Studio.
Centralise les couleurs/labels de performance pour éviter la duplication.
"""

# ── Couleurs par tag de performance ──────────────────────────────────────────
PERF_BORDER = {
    "viral":   "#00C853",
    "bon":     "#2196F3",
    "moyen":   "#FF9800",
    "mauvais": "#F44336",
}

PERF_LABEL_MAP = {
    "viral":   "🔥 Viral",
    "bon":     "✅ Bon",
    "moyen":   "😐 Moyen",
    "mauvais": "❌ Mauvais",
}

PERF_TEXT_COLOR = {
    "viral":   "#000",
    "bon":     "#fff",
    "moyen":   "#000",
    "mauvais": "#fff",
}

# ── Couleurs placeholder par catégorie ────────────────────────────────────────
CAT_COLORS = {
    "Restaurant":    "#E65100",
    "Bar":           "#7B1FA2",
    "Café":          "#5D4037",
    "Expérience":    "#1565C0",
    "Bon plan":      "#2E7D32",
    "Tendance food": "#AD1457",
    "Lifestyle":     "#4527A0",
    "Voyage IDF":    "#00695C",
    "Autre":         "#37474F",
}

# ── Seuils de déverrouillage ──────────────────────────────────────────────────
UNLOCK_BRIEFS    = 5    # vidéos annotées pour générer des briefs
UNLOCK_PATTERNS  = 10   # vidéos pour patterns & graphiques complets
UNLOCK_RAPPORT   = 20   # vidéos pour rapport IA complet
UNLOCK_PREDICT   = 30   # vidéos pour prédictions & recommandations
