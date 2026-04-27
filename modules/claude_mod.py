import os
import json
import logging
from pathlib import Path
from modules._env import _ROOT  # noqa — charge .env


logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Modèles — Haiku pour l'analyse courante (10x moins cher), Sonnet pour le brief premium
MODEL_FAST   = "claude-haiku-4-5"   # rapide et économique — analyse vidéo
MODEL_SMART  = "claude-sonnet-4-5"  # qualité maximale — brief complet

# Tarifs approximatifs ($/M tokens)
PRICES = {
    MODEL_FAST:  {"in": 0.80,  "out": 4.0,  "cache_write": 0.80,  "cache_read": 0.08},
    MODEL_SMART: {"in": 3.0,   "out": 15.0, "cache_write": 3.0,   "cache_read": 0.30},
}

# ── Contexte statique Insolit (mis en cache → -90% coût après 1er appel) ─────
_CONTEXT_PATH = _ROOT / "context_insolit.md"
_INSOLIT_CONTEXT: str | None = None


def _get_insolit_context() -> str:
    """Charge context_insolit.md une seule fois (lazy loading + mise en cache mémoire)."""
    global _INSOLIT_CONTEXT
    if _INSOLIT_CONTEXT is None:
        try:
            _INSOLIT_CONTEXT = _CONTEXT_PATH.read_text(encoding="utf-8")
            logger.info(f"Contexte Insolit chargé: {len(_INSOLIT_CONTEXT)} caractères")
        except FileNotFoundError:
            _INSOLIT_CONTEXT = ""
            logger.warning("context_insolit.md introuvable — fonctionnement sans contexte enrichi")
    return _INSOLIT_CONTEXT


def _get_client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _call_claude(
    prompt: str,
    system: str = None,
    max_tokens: int = 2048,
    model: str = MODEL_FAST,
    use_context: bool = True,        # Injecte context_insolit.md avec cache
) -> tuple[str, dict]:
    """
    Appelle Claude et retourne (texte, usage).
    use_context=True : injecte le contexte Insolit avec prompt caching (économise -90% après 1er appel).
    """
    import anthropic
    client = _get_client()

    # Construction du système avec cache
    system_blocks = []
    if use_context:
        ctx = _get_insolit_context()
        if ctx:
            # Le bloc contexte est marqué cache_control → Anthropic le met en cache
            system_blocks.append({
                "type": "text",
                "text": ctx,
                "cache_control": {"type": "ephemeral"},  # Cache 5 minutes (renouvelé à chaque appel)
            })
    if system:
        system_blocks.append({"type": "text", "text": system})

    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "betas": ["prompt-caching-2024-07-31"],  # Active le prompt caching
    }
    if system_blocks:
        kwargs["system"] = system_blocks

    try:
        response = client.beta.messages.create(**kwargs)
    except Exception:
        # Fallback sans caching si le beta n'est pas disponible
        kwargs.pop("betas", None)
        if system_blocks:
            kwargs["system"] = "\n\n".join(b["text"] for b in system_blocks)
        response = client.messages.create(**kwargs)

    text = response.content[0].text
    p = PRICES.get(model, {"in": 3.0, "out": 15.0, "cache_write": 3.0, "cache_read": 0.30})

    # Calcul du coût avec cache
    in_tokens = getattr(response.usage, "input_tokens", 0)
    out_tokens = getattr(response.usage, "output_tokens", 0)
    cache_write = getattr(response.usage, "cache_creation_input_tokens", 0)
    cache_read  = getattr(response.usage, "cache_read_input_tokens", 0)

    cost = round(
        (in_tokens * p["in"] + out_tokens * p["out"] +
         cache_write * p.get("cache_write", p["in"]) +
         cache_read  * p.get("cache_read", p["in"] * 0.1)) / 1_000_000,
        6
    )

    usage = {
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cache_write_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "model": model,
        "cout_estime": cost,
    }
    if cache_read:
        logger.info(f"Cache hit! {cache_read} tokens lus du cache (-90% coût)")

    return text, usage


_VISION_JSON_STRUCTURE = """{
  "plans": [
    {
      "timestamp_debut": 0.0,
      "timestamp_fin": 3.0,
      "type_plan": "macro_plat|plan_moyen|plan_large|visage|texte_ecran|action|transition",
      "sujet_principal": "ce qu'on voit",
      "luminosite": 7,
      "type_lumiere": "naturelle_chaude|naturelle_froide|artificielle|mixte",
      "mouvement_camera": "statique|travelling|zoom_in|zoom_out|shake",
      "presence_visage": false,
      "expression_visage": "neutre|sourire|surprise|reaction|serieux|na",
      "texte_visible_ecran": null,
      "couleurs_dominantes": ["couleur1"],
      "qualite_production": 7,
      "emotion_transmise": "appétissant|excitant|neutre|drôle",
      "role_narratif": "hook|contexte|preuve|ambiance|cta|branding",
      "points_forts": ["point"],
      "suggestion_amelioration": "suggestion",
      "scene_change_type": "cut|transition|fade|zoom|pan"
    }
  ],
  "hook_analyse": {
    "duree_hook_secondes": 3,
    "texte_dit": "mots exacts du hook",
    "texte_visible": "texte à l'écran au début ou null",
    "type_hook": "question|prix_choc|exclusivite|curiosite|social_proof|teasing|humour",
    "score_accroche": 7,
    "premiere_impression": "1 phrase",
    "ce_qui_accroche": "explication",
    "ce_qui_manque": null
  },
  "metriques_globales": {
    "nb_plans_total": 5,
    "rythme_coupes_par_seconde": 0.3,
    "luminosite_moyenne": 7,
    "presence_visage_pourcentage": "30%",
    "proportion_texte_ecran": "10%",
    "type_tournage": "interieur|exterieur|mixte",
    "qualite_globale": 7
  }
}"""


def analyze_frames_with_vision(
    frames: list,
    video_duration: float,
) -> tuple[dict, dict]:
    """
    Analyse visuelle via Claude Haiku Vision (frames extraites par ffmpeg).
    Beaucoup plus rapide que TwelveLabs (~10-15s vs 2-3min).
    frames: [{"data": base64_jpeg, "timestamp_debut": float, "timestamp_fin": float, "timestamp_mid": float}]
    """
    if not frames:
        return {}, {}

    import anthropic as _anthropic

    client = _get_client()

    # Construction du message multimodal
    content = []
    content.append({
        "type": "text",
        "text": (
            f"Vidéo TikTok/Instagram de {video_duration:.0f} secondes. "
            f"Voici {len(frames)} frames extraites à intervalles réguliers.\n"
            "OBJECTIF : Détecter TOUS les plans et analyser la structure créative complète.\n\n"
            "RÈGLES ABSOLUES :\n"
            f"1. PLANS : Chaque frame = UN plan distinct dans le JSON. NE JAMAIS fusionner deux frames.\n"
            f"   → Tu dois retourner exactement {len(frames)} objets dans 'plans'.\n"
            "2. TEXTE : Copie MOT POUR MOT tout texte visible (overlay, sous-titres, prix, adresses, emojis hashtags).\n"
            "   → Si prix visible (ex: 6,99€ / 12€ / -50%) → note dans texte_visible_ecran OBLIGATOIREMENT.\n"
            "   → Si aucun texte → null (pas une string vide).\n"
            "3. HOOK : Les 3 premières secondes sont critiques — analyse finement le texte ET l'image du plan 1.\n"
            "4. TIMESTAMPS : Utilise exactement les timestamps fournis (ne les invente pas).\n"
            "5. structure_narrative dans metriques doit être UNE STRING (pas un objet JSON)."
        )
    })

    for i, frame in enumerate(frames):
        content.append({
            "type": "text",
            "text": f"\nPlan {i+1} — [{frame['timestamp_debut']:.1f}s → {frame['timestamp_fin']:.1f}s] (frame prise à {frame['timestamp_mid']:.1f}s) :"
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": frame["data"],
            }
        })

    content.append({
        "type": "text",
        "text": (
            f"\nRetourne UNIQUEMENT ce JSON valide (sans markdown, sans explication) "
            f"en utilisant exactement les timestamps fournis :\n{_VISION_JSON_STRUCTURE}"
        )
    })

    try:
        # ~500 tokens output par frame + 1000 overhead (plans verbeux + hook + metriques)
        # 12 frames → 7000 tokens → largement au-dessus du plafond de troncature
        # claude-haiku-4-5 supporte jusqu'à 8192 output tokens
        max_tok = min(8192, max(3000, len(frames) * 500 + 1000))
        response = client.messages.create(
            model=MODEL_FAST,
            max_tokens=max_tok,
            messages=[{"role": "user", "content": content}],
        )

        raw_text = response.content[0].text
        p = PRICES[MODEL_FAST]
        in_tok  = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost    = round((in_tok * p["in"] + out_tok * p["out"]) / 1_000_000, 5)

        usage = {"input_tokens": in_tok, "output_tokens": out_tok, "model": MODEL_FAST, "cout_estime": cost}
        logger.info(f"Vision (Haiku): {in_tok}in/{out_tok}out = ${cost:.5f}")

        parsed = _parse_pegasus_response(raw_text)
        return parsed, usage

    except Exception as e:
        logger.error(f"Erreur Vision: {e}")
        return {}, {}


def analyze_creative(pegasus_data: dict, whisper_data: dict, similar_videos: list) -> tuple[dict, dict]:
    """
    Analyse créative — utilise Haiku (10x moins cher que Sonnet).
    Retourne (analyse_dict, usage_dict).
    """
    # Pegasus : on envoie seulement les champs essentiels pour réduire les tokens
    hook = pegasus_data.get("hook_analyse", {})
    metriques = pegasus_data.get("metriques_globales", {})
    plans_summary = [
        {
            "type": p.get("type_plan"),
            "duree": round(float(p.get("timestamp_fin", 0)) - float(p.get("timestamp_debut", 0)), 1),
            "role": p.get("role_narratif"),
            "visage": p.get("presence_visage"),
            "qualite": p.get("qualite_production"),
        }
        for p in pegasus_data.get("plans", [])[:10]  # max 10 plans
    ]

    # Whisper : tronquer si trop long
    texte = whisper_data.get("texte_complet", "Non disponible")
    if len(texte) > 600:
        texte = texte[:600] + "..."

    similar_str = ""
    if similar_videos:
        similar_str = "\n".join(
            f"- {s.get('titre','?')} | similarité {s.get('similarite','?')}%"
            for s in similar_videos[:3]
        )

    prompt = f"""Expert TikTok food IDF. Réponds UNIQUEMENT avec ce JSON valide (sans markdown, sans texte avant/après).

HOOK: {hook.get('texte_dit','')} | {hook.get('type_hook','')} | score:{hook.get('score_accroche',5)}
PLANS ({len(plans_summary)} plans): {json.dumps(plans_summary, ensure_ascii=False)}
TRANSCRIPT: {texte}
MOTS: {whisper_data.get('nb_mots',0)} | DÉBIT: {whisper_data.get('debit_parole',0)} mots/s

TYPES OBLIGATOIRES (respecte exactement) :
- hook_texte, hook_visuel, hook_type, hook_analyse, structure_narrative, comparaison_base, note_adaptation → STRING (jamais un objet)
- points_forts, points_faibles, recommandations, plans_a_reproduire → ARRAY de strings
- hook_score, score_potentiel → NUMBER
- adaptable_insolit → BOOLEAN

{{"hook_texte":"texte exact dit","hook_visuel":"description visuelle du hook","hook_type":"question|prix_choc|exclusivite|curiosite|social_proof|teasing|humour","hook_score":7.5,"hook_analyse":"analyse en 1-2 phrases","structure_narrative":"description de la structure en string","points_forts":["point1","point2","point3"],"points_faibles":["faiblesse1","faiblesse2"],"score_potentiel":7.0,"score_justification":"justification courte","recommandations":["reco1","reco2","reco3"],"comparaison_base":"comparaison courte","adaptable_insolit":true,"script_adapte":"script adapté Insolit","plans_a_reproduire":["plan1"],"note_adaptation":"note"}}"""

    try:
        text, usage = _call_claude(prompt, max_tokens=2000, model=MODEL_FAST)
        parsed = _parse_json_response(text)
        logger.info(f"Analyse créative (Haiku): coût={usage['cout_estime']}$ | {usage['input_tokens']}in/{usage['output_tokens']}out")
        return parsed, usage
    except Exception as e:
        logger.error(f"Erreur analyse Claude: {e}")
        return {"_error": str(e)}, {}


def generate_brief(
    type_contenu: str,
    partenaire: str,
    ville: str,
    offre: str,
    objectif: str,
    duree: int,
    ton: str,
    best_videos: list,
    patterns: dict = None,
    knowledge_base: list = None,
) -> tuple[dict, dict]:
    """
    Génère un brief complet — utilise Sonnet (qualité maximale pour le livrable final).
    knowledge_base: liste de ressources de la Base de Connaissances (scripts, patterns, guidelines).
    """
    best_str = json.dumps(best_videos[:4], ensure_ascii=False, indent=2) if best_videos else "[]"

    # Enrichissement base de connaissances
    kb_section = ""
    if knowledge_base:
        # Prioriser: guidelines > scripts viraux > patterns
        guidelines = [r for r in knowledge_base if r.get("type_ressource") == "guideline"]
        scripts = [r for r in knowledge_base if r.get("type_ressource") == "script" and r.get("performance_tag") == "viral"]
        patterns_kb = [r for r in knowledge_base if r.get("type_ressource") == "pattern"]
        top_kb = (guidelines + scripts + patterns_kb)[:6]  # max 6 ressources

        if top_kb:
            kb_lines = []
            for r in top_kb:
                type_lbl = {"script": "Script", "pattern": "Pattern", "guideline": "Guideline",
                            "inspiration": "Inspiration", "competitor": "Concurrent"}.get(r.get("type_ressource", ""), "Ressource")
                perf = f" [{r['performance_tag'].upper()}]" if r.get("performance_tag") else ""

                # Stats complètes si disponibles
                stats_parts = []
                if r.get("vues_approx"): stats_parts.append(f"{r['vues_approx']:,} vues")
                if r.get("nb_likes"):    stats_parts.append(f"{r['nb_likes']:,} likes")
                if r.get("nb_enregistrements"): stats_parts.append(f"{r['nb_enregistrements']:,} saves")
                if r.get("taux_completion"): stats_parts.append(f"{r['taux_completion']:.0f}% complétion")
                # Calcul engagement rate
                vues_n = r.get("vues_approx") or 0
                if vues_n > 0:
                    total_eng = (r.get("nb_likes") or 0) + (r.get("nb_commentaires") or 0) + \
                                (r.get("nb_partages") or 0) + (r.get("nb_enregistrements") or 0)
                    eng_rate = round(total_eng / vues_n * 100, 1)
                    if eng_rate > 0: stats_parts.append(f"{eng_rate}% engagement")
                stats_str = f" | {' · '.join(stats_parts)}" if stats_parts else ""

                # Ligne de base
                line = f"[{type_lbl}{perf}{stats_str}] {r['titre']}:"

                # Hook exact
                if r.get("hook_texte"):
                    line += f"\nHOOK: «{r['hook_texte']}»"

                # Ce qui marche + à reproduire (gold mine pour Claude)
                if r.get("ce_qui_marche"):
                    line += f"\nPOURQUOI ÇA MARCHE: {r['ce_qui_marche']}"
                if r.get("a_reproduire"):
                    line += f"\nÀ REPRODUIRE: {r['a_reproduire']}"

                # Script
                line += f"\nSCRIPT:\n{r['contenu']}"

                kb_lines.append(line)

            kb_section = f"\n\nBASE DE CONNAISSANCES INSOLIT (scripts validés avec stats réelles):\n" + "\n---\n".join(kb_lines)

    prompt = f"""Brief de tournage TikTok/Reels pour Insolit (bons plans restaurants IDF).

CONTEXTE:
- Partenaire: {partenaire} ({type_contenu}) — {ville}
- Offre: {offre}
- Objectif: {objectif} | Durée: {duree}s | Ton: {ton}

VIDÉOS QUI ONT MARCHÉ:
{best_str}{kb_section}

JSON strict (sans markdown):
{{"hook_suggere":"texte exact","hook_justification":"basé sur quelle vidéo ou ressource","script_complet":[{{"timestamp":"0-3s","texte_a_dire":"...","texte_ecran":"..."}}],"plans":[{{"numero":1,"timestamp":"0-3s","description_precise":"...","conseil_lumiere":"...","conseil_camera":"...","conseil_pratique":"...","difficulte":2,"pourquoi_ce_plan":"..."}}],"duree_totale_estimee":{duree},"temps_tournage_minutes":30,"temps_montage_minutes":45,"niveau_global":"Débutant|Intermédiaire|Avancé","meilleur_moment_publication":"Mardi 18h-20h","mots_cles_a_utiliser":["mot1","mot2"],"mots_a_eviter":["mot1"],"suggestions_bonus":["s1","s2"],"son_tendance_conseil":"conseil musique"}}"""

    try:
        text, usage = _call_claude(prompt, max_tokens=4096, model=MODEL_SMART)
        parsed = _parse_json_response(text)
        logger.info(f"Brief (Sonnet): coût={usage['cout_estime']}$")
        return parsed, usage
    except Exception as e:
        logger.error(f"Erreur génération brief: {e}")
        return {"_error": str(e)}, {}


def generate_patterns_report(videos_data: list) -> tuple[str, dict]:
    """Rapport de patterns — Haiku suffit pour du markdown."""
    # Résume les données pour réduire les tokens
    summary = [
        {k: v for k, v in vid.items() if k in
         ["titre", "duree_secondes", "nb_plans", "hook_score", "score_potentiel", "vues", "performance_tag", "rythme"]}
        for vid in videos_data[:30]  # max 30 vidéos
    ]

    prompt = f"""Expert analyse TikTok/Instagram Insolit (bons plans IDF).
{len(summary)} vidéos analysées:
{json.dumps(summary, ensure_ascii=False)}

Rapport de patterns actionnable en français, format markdown:

## 📊 Patterns principaux
[3-5 patterns fiables avec % vidéos concernées]

## 🚫 Ce qui tue la performance
[Corrélations négatives]

## 💡 Opportunités non exploitées
[Contenu sous-représenté mais à potentiel]

## 🎯 3 prochaines vidéos à tester
[Recommandations concrètes data-driven]

## ⚡ Action immédiate
[1 seule chose à changer maintenant]"""

    try:
        text, usage = _call_claude(prompt, max_tokens=1500, model=MODEL_FAST)
        return text, usage
    except Exception as e:
        logger.error(f"Erreur rapport patterns: {e}")
        return f"Erreur : {e}", {}


def compare_video_to_kb_resource(
    video_hook_type: str,
    video_hook_text: str,
    video_score: float,
    video_categorie: str,
    resource: dict,
) -> dict:
    """
    Compare une vidéo analysée à une ressource de la KB.
    Retourne {"points_communs": [...], "differences": [...], "conseil_cle": "..."}
    Utilise Haiku (rapide, ~$0.001).
    """
    perf_label = {"viral": "VIRAL (+500k vues)", "bon": "BON (50-500k vues)",
                  "moyen": "MOYEN (<50k vues)"}.get(resource.get("performance_tag", ""), "performance inconnue")
    vues_str = f"{resource.get('vues_approx', 0):,} vues" if resource.get("vues_approx") else "vues inconnues"

    prompt = f"""Compare ces deux contenus vidéo en 1 phrase max par point. JSON strict uniquement.

VIDÉO ANALYSÉE:
- Catégorie: {video_categorie}
- Hook type: {video_hook_type}
- Hook texte: «{video_hook_text or "non disponible"}»
- Score potentiel: {video_score}/10

RESSOURCE BASE DE CONNAISSANCES [{perf_label} | {vues_str}]:
- Titre: {resource.get("titre")}
- Hook: «{resource.get("hook_texte") or "non renseigné"}»
- Ce qui marche: {resource.get("ce_qui_marche") or "non renseigné"}
- Script (extrait): {str(resource.get("contenu", ""))[:200]}

{{"points_communs": ["similarité 1 (1 phrase max)", "similarité 2"], "differences": ["différence 1 (1 phrase max)", "différence 2"], "conseil_cle": "1 action concrète pour s'aligner sur la ressource performante"}}"""

    try:
        text, usage = _call_claude(prompt, max_tokens=300, model=MODEL_FAST, use_context=False)
        result = _parse_json_response(text)
        return result
    except Exception as e:
        logger.warning(f"Comparaison KB échouée: {e}")
        return {"points_communs": [], "differences": [], "conseil_cle": ""}


def _parse_pegasus_response(raw_text: str) -> dict:
    """Parse la réponse JSON Vision (même logique que l'ancien module twelvelabs)."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    logger.warning("JSON Vision non parsable — structure minimale générée")
    return {
        "plans": [], "hook_analyse": {
            "duree_hook_secondes": 3, "texte_dit": "", "texte_visible": None,
            "type_hook": "inconnu", "score_accroche": 5,
            "premiere_impression": "Analyse non disponible", "ce_qui_accroche": "", "ce_qui_manque": None,
        }, "metriques_globales": {
            "nb_plans_total": 0, "rythme_coupes_par_seconde": 0,
            "luminosite_moyenne": 5, "presence_visage_pourcentage": "0%",
            "proportion_texte_ecran": "0%", "type_tournage": "inconnu", "qualite_globale": 5,
        },
    }


def _parse_json_response(text: str) -> dict:
    t = text.strip()
    if "```json" in t:
        t = t.split("```json")[1].split("```")[0].strip()
    elif "```" in t:
        t = t.split("```")[1].split("```")[0].strip()
    parsed = None
    try:
        parsed = json.loads(t)
    except json.JSONDecodeError:
        start = t.find("{")
        end = t.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(t[start:end])
            except json.JSONDecodeError:
                pass
    if parsed is None:
        return {"_raw": text, "_error": "JSON non parsable"}

    # Normalisation des types pour éviter les erreurs SQLite "type dict/list not supported"
    STRING_FIELDS = ["hook_texte", "hook_visuel", "hook_type", "hook_analyse",
                     "structure_narrative", "comparaison_base", "note_adaptation",
                     "script_adapte", "score_justification"]
    LIST_FIELDS   = ["points_forts", "points_faibles", "recommandations", "plans_a_reproduire"]
    for f in STRING_FIELDS:
        if f in parsed and not isinstance(parsed[f], str):
            # dict {"analyse": "..."} → extrait la string ou json.dumps
            val = parsed[f]
            if isinstance(val, dict):
                parsed[f] = val.get("analyse") or val.get("description") or val.get("texte") or json.dumps(val, ensure_ascii=False)
            else:
                parsed[f] = str(val) if val is not None else ""
    for f in LIST_FIELDS:
        if f in parsed and not isinstance(parsed[f], list):
            val = parsed[f]
            if isinstance(val, str):
                try:
                    parsed[f] = json.loads(val)
                except Exception:
                    parsed[f] = [val] if val else []
            else:
                parsed[f] = []

    return parsed
