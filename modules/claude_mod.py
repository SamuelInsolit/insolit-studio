import os
import json
import logging
from modules._env import _ROOT  # noqa — charge .env


logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Modèles — Haiku pour l'analyse courante (10x moins cher), Sonnet pour le brief premium
MODEL_FAST   = "claude-haiku-4-5"   # rapide et économique — analyse vidéo
MODEL_SMART  = "claude-sonnet-4-5"  # qualité maximale — brief complet

# Tarifs approximatifs ($/M tokens)
PRICES = {
    MODEL_FAST:  {"in": 0.80,  "out": 4.0},
    MODEL_SMART: {"in": 3.0,   "out": 15.0},
}


def _get_client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _call_claude(prompt: str, system: str = None, max_tokens: int = 2048, model: str = MODEL_FAST) -> tuple[str, dict]:
    """Appelle Claude et retourne (texte, usage)."""
    client = _get_client()
    messages = [{"role": "user", "content": prompt}]
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    text = response.content[0].text
    p = PRICES.get(model, {"in": 3.0, "out": 15.0})
    cost = round(
        (response.usage.input_tokens * p["in"] + response.usage.output_tokens * p["out"]) / 1_000_000, 5
    )
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": model,
        "cout_estime": cost,
    }
    return text, usage


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

    prompt = f"""Expert TikTok/Instagram food & lifestyle IDF. Analyse cette vidéo.

HOOK: {hook.get('texte_dit','')} | type: {hook.get('type_hook','')} | score: {hook.get('score_accroche',5)}
MÉTRIQUES: {json.dumps(metriques, ensure_ascii=False)}
PLANS ({len(plans_summary)}): {json.dumps(plans_summary, ensure_ascii=False)}
TRANSCRIPTION: {texte}
Débit: {whisper_data.get('debit_parole',0)} mots/s | {whisper_data.get('nb_mots',0)} mots
SIMILAIRES: {similar_str or 'aucune'}

JSON strict (sans markdown):
{{"hook_texte":"texte exact","hook_visuel":"description","hook_type":"question|prix_choc|exclusivite|curiosite|social_proof|teasing|humour","hook_score":7.5,"hook_analyse":"analyse précise 1-2 phrases","structure_narrative":"construction narrative","points_forts":["p1","p2","p3"],"points_faibles":["f1","f2"],"score_potentiel":7.0,"score_justification":"justification courte","recommandations":["r1","r2","r3"],"comparaison_base":"comparaison courte","adaptable_insolit":true,"script_adapte":"script exact adapté Insolit","plans_a_reproduire":["plan1","plan2"],"ce_qui_change":["change1"],"note_adaptation":"note globale"}}"""

    try:
        text, usage = _call_claude(prompt, max_tokens=1200, model=MODEL_FAST)
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
    patterns: dict = None
) -> tuple[dict, dict]:
    """
    Génère un brief complet — utilise Sonnet (qualité maximale pour le livrable final).
    """
    best_str = json.dumps(best_videos[:4], ensure_ascii=False, indent=2) if best_videos else "[]"

    prompt = f"""Brief de tournage TikTok/Reels pour Insolit (bons plans restaurants IDF).

CONTEXTE:
- Partenaire: {partenaire} ({type_contenu}) — {ville}
- Offre: {offre}
- Objectif: {objectif} | Durée: {duree}s | Ton: {ton}

VIDÉOS QUI ONT MARCHÉ:
{best_str}

JSON strict (sans markdown):
{{"hook_suggere":"texte exact","hook_justification":"basé sur quelle vidéo","script_complet":[{{"timestamp":"0-3s","texte_a_dire":"...","texte_ecran":"..."}}],"plans":[{{"numero":1,"timestamp":"0-3s","description_precise":"...","conseil_lumiere":"...","conseil_camera":"...","conseil_pratique":"...","difficulte":2,"pourquoi_ce_plan":"..."}}],"duree_totale_estimee":{duree},"temps_tournage_minutes":30,"temps_montage_minutes":45,"niveau_global":"Débutant|Intermédiaire|Avancé","meilleur_moment_publication":"Mardi 18h-20h","mots_cles_a_utiliser":["mot1","mot2"],"mots_a_eviter":["mot1"],"suggestions_bonus":["s1","s2"],"son_tendance_conseil":"conseil musique"}}"""

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


def _parse_json_response(text: str) -> dict:
    t = text.strip()
    if "```json" in t:
        t = t.split("```json")[1].split("```")[0].strip()
    elif "```" in t:
        t = t.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start = t.find("{")
        end = t.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end])
            except json.JSONDecodeError:
                pass
    return {"_raw": text, "_error": "JSON non parsable"}
