import os
import json
import time
import logging
import numpy as np
from modules._env import _ROOT  # noqa — charge .env


logger = logging.getLogger(__name__)

TWELVELABS_API_KEY = os.getenv("TWELVELABS_API_KEY")
INDEX_NAME = "insolit-studio"

PEGASUS_PROMPT = """Analyse cette vidéo TikTok/Instagram et retourne UNIQUEMENT un JSON valide (sans markdown, sans explication) avec cette structure exacte.

RÈGLES CRITIQUES POUR LA DÉTECTION DES PLANS :
- Détecte CHAQUE changement de plan, même très court (minimum 0.3 seconde).
- Chaque changement de plan = un nouveau objet dans la liste plans.
- Si la vidéo dure 30s avec 10 coupes, tu retournes 10 plans minimum.
- Ne regroupe JAMAIS plusieurs plans en un seul. Chaque coupe = un objet séparé.
- Inspecte frame par frame pour ne manquer aucun cut, transition, fade ou zoom discret.

{
  "plans": [
    {
      "timestamp_debut": 0.0,
      "timestamp_fin": 3.0,
      "type_plan": "macro_plat|plan_moyen|plan_large|visage|texte_ecran|qr_code|action|transition",
      "scene_change_type": "cut|transition|fade|zoom|pan",
      "sujet_principal": "description courte",
      "luminosite": 7,
      "type_lumiere": "naturelle_chaude|naturelle_froide|artificielle|mixte",
      "mouvement_camera": "statique|travelling|zoom_in|zoom_out|shake",
      "presence_visage": false,
      "expression_visage": "neutre|sourire|surprise|reaction|serieux|na",
      "texte_visible_ecran": null,
      "couleurs_dominantes": ["couleur1", "couleur2"],
      "qualite_production": 8,
      "emotion_transmise": "description courte",
      "role_narratif": "hook|contexte|preuve|ambiance|cta|branding",
      "points_forts": ["point1"],
      "suggestion_amelioration": "suggestion courte"
    }
  ],
  "hook_analyse": {
    "duree_hook_secondes": 3,
    "texte_dit": "transcription exacte 0-3s",
    "texte_visible": "texte écran 0-3s ou null",
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
    "presence_visage_pourcentage": "40%",
    "proportion_texte_ecran": "20%",
    "type_tournage": "interieur|exterieur|mixte",
    "qualite_globale": 7
  }
}"""


def _get_client():
    try:
        from twelvelabs import TwelveLabs
        return TwelveLabs(api_key=TWELVELABS_API_KEY)
    except ImportError:
        raise ImportError("Package 'twelvelabs' non installé. Lance: pip install twelvelabs")


def _get_or_create_index(client):
    try:
        indexes = client.indexes.list()
        for idx in indexes:
            name = getattr(idx, "index_name", None) or getattr(idx, "name", None)
            if name == INDEX_NAME:
                logger.info(f"Index existant trouvé: {idx.id}")
                return idx.id

        logger.info("Création d'un nouvel index TwelveLabs...")
        try:
            from twelvelabs.indexes import IndexesCreateRequestModelsItem
            index = client.indexes.create(
                index_name=INDEX_NAME,
                models=[
                    IndexesCreateRequestModelsItem(
                        model_name="pegasus1.2",
                        model_options=["visual", "audio"]
                    ),
                    IndexesCreateRequestModelsItem(
                        model_name="marengo3.0",
                        model_options=["visual", "audio"]
                    ),
                ]
            )
        except (ImportError, AttributeError):
            # Fallback si la classe n'est pas dans ce chemin
            index = client.indexes.create(
                index_name=INDEX_NAME,
                models=[
                    {"model_name": "pegasus1.2", "model_options": ["visual", "audio"]},
                    {"model_name": "marengo3.0", "model_options": ["visual", "audio"]},
                ]
            )

        logger.info(f"Index créé: {index.id}")
        return index.id
    except Exception as e:
        logger.error(f"Erreur index TwelveLabs: {e}")
        raise


def _upload_video(client, index_id, video_path):
    try:
        logger.info(f"Upload vidéo vers TwelveLabs: {video_path}")
        with open(video_path, "rb") as video_file:
            task = client.tasks.create(index_id=index_id, video_file=video_file)

        task_id = task.id
        logger.info(f"Tâche créée: task_id={task_id} — attente indexation...")

        def on_task_update(t):
            logger.info(f"  Statut TwelveLabs: {t.status}")

        done = client.tasks.wait_for_done(task_id=task_id, sleep_interval=5, callback=on_task_update)

        if done.status != "ready":
            raise Exception(f"Indexation échouée: {done.status}")

        # video_id == task_id dans l'API TwelveLabs v1.2.3
        video_id = getattr(done, "video_id", None) or task_id
        logger.info(f"Vidéo indexée: video_id={video_id}")
        return video_id
    except Exception as e:
        logger.error(f"Erreur upload TwelveLabs: {e}")
        raise


def analyze_with_pegasus(video_path: str, progress_callback=None) -> dict:
    """Analyse complète via Pegasus 1.2 — retourne le JSON structuré."""
    client = _get_client()

    for attempt in range(3):
        try:
            if progress_callback:
                progress_callback("Connexion à TwelveLabs...")

            index_id = _get_or_create_index(client)

            if progress_callback:
                progress_callback("Upload et indexation de la vidéo...")

            video_id = _upload_video(client, index_id, video_path)

            if progress_callback:
                progress_callback("Analyse Pegasus en cours...")

            result = client.analyze(
                prompt=PEGASUS_PROMPT,
                video_id=video_id,
            )

            raw_text = result.data if hasattr(result, "data") else str(result)
            logger.info(f"Réponse Pegasus brute: {str(raw_text)[:200]}...")

            parsed = _parse_pegasus_response(str(raw_text))
            parsed["_video_id_twelvelabs"] = video_id
            parsed["_raw_response"] = str(raw_text)
            return parsed

        except Exception as e:
            logger.warning(f"Tentative {attempt + 1}/3 échouée: {type(e).__name__}: {e}")
            if attempt == 2:
                logger.error(f"Toutes les tentatives Pegasus ont échoué — fallback. Dernière erreur: {e}")
                return _pegasus_fallback(video_path)
            time.sleep(5)


def _parse_pegasus_response(raw_text: str) -> dict:
    """Extrait le JSON de la réponse Pegasus."""
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

    logger.warning("JSON Pegasus non parsable — structure minimale générée")
    return {
        "plans": [],
        "hook_analyse": {
            "duree_hook_secondes": 3,
            "texte_dit": "",
            "texte_visible": None,
            "type_hook": "inconnu",
            "score_accroche": 5,
            "premiere_impression": "Analyse non disponible",
            "ce_qui_accroche": "",
            "ce_qui_manque": None
        },
        "metriques_globales": {
            "nb_plans_total": 0,
            "rythme_coupes_par_seconde": 0,
            "luminosite_moyenne": 5,
            "presence_visage_pourcentage": "0%",
            "proportion_texte_ecran": "0%",
            "type_tournage": "inconnu",
            "qualite_globale": 5
        },
        "_raw_response": raw_text
    }


def _pegasus_fallback(video_path: str) -> dict:
    """Retourne une structure minimale en cas d'échec total."""
    return {
        "plans": [],
        "hook_analyse": {
            "duree_hook_secondes": 3,
            "texte_dit": "",
            "texte_visible": None,
            "type_hook": "inconnu",
            "score_accroche": 5,
            "premiere_impression": "Analyse TwelveLabs non disponible",
            "ce_qui_accroche": "N/A",
            "ce_qui_manque": None
        },
        "metriques_globales": {
            "nb_plans_total": 0,
            "rythme_coupes_par_seconde": 0,
            "luminosite_moyenne": 5,
            "presence_visage_pourcentage": "0%",
            "proportion_texte_ecran": "0%",
            "type_tournage": "inconnu",
            "qualite_globale": 5
        },
        "_error": "Fallback activé"
    }


def get_marengo_embedding(video_path: str) -> list | None:
    """Génère l'embedding Marengo pour une vidéo locale via embed.tasks."""
    client = _get_client()
    try:
        logger.info("Génération embedding Marengo (embed.tasks)...")
        with open(video_path, "rb") as vf:
            task = client.embed.tasks.create(
                model_name="marengo3.0",
                video_file=vf,
                video_embedding_scope=["clip", "video"],
            )

        def on_embed_update(t):
            logger.info(f"  Embed Marengo statut: {t.status}")

        done = client.embed.tasks.wait_for_done(
            task_id=task.id,
            sleep_interval=5,
            callback=on_embed_update,
        )

        # Récupère l'embedding complet
        result = client.embed.tasks.retrieve(task.id, embedding_option=["visual"])
        segments = []
        if hasattr(result, "video_embedding") and result.video_embedding:
            segments = result.video_embedding.segments or []
        elif hasattr(done, "video_embedding") and done.video_embedding:
            segments = done.video_embedding.segments or []

        if segments:
            vectors = [seg.embeddings_float for seg in segments if hasattr(seg, "embeddings_float") and seg.embeddings_float]
            if vectors:
                avg = np.mean(vectors, axis=0).tolist()
                logger.info(f"Embedding Marengo généré: dimension={len(avg)}")
                return avg

        logger.warning("Aucun segment d'embedding retourné par Marengo")
        return None
    except Exception as e:
        logger.error(f"Erreur embedding Marengo: {e}")
        return None


def search_similar_videos(target_embedding: list, all_videos_embeddings: list, top_k: int = 5) -> list:
    """
    Recherche les vidéos les plus similaires via similarité cosinus.
    all_videos_embeddings: liste de dicts {"video_id": int, "embedding": list, ...}
    """
    if not target_embedding or not all_videos_embeddings:
        return []

    target = np.array(target_embedding)
    target_norm = np.linalg.norm(target)
    if target_norm == 0:
        return []

    scores = []
    for item in all_videos_embeddings:
        emb = item.get("embedding")
        if not emb:
            continue
        vec = np.array(emb)
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        cosine_sim = float(np.dot(target, vec) / (target_norm * norm))
        scores.append({**item, "similarite": round(cosine_sim * 100, 1)})

    scores.sort(key=lambda x: x["similarite"], reverse=True)
    return scores[:top_k]


def search_by_text(query: str, index_id: str = None) -> list:
    """Recherche sémantique textuelle via Marengo."""
    client = _get_client()
    try:
        if not index_id:
            index_id = _get_or_create_index(client)

        results = client.search.query(
            index_id=index_id,
            query_text=query,
            options=["visual", "conversation", "text_in_video"],
            page_limit=10
        )
        items = []
        for clip in results.data:
            items.append({
                "video_id_twelvelabs": clip.video_id,
                "score": clip.score,
                "start": clip.start,
                "end": clip.end,
            })
        return items
    except Exception as e:
        logger.error(f"Erreur recherche sémantique TwelveLabs: {e}")
        return []
