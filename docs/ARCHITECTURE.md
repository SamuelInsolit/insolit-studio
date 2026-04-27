# Architecture — Insolit Studio

## Vue d'ensemble

Insolit Studio est une application Streamlit multi-pages qui analyse des vidéos TikTok/Instagram pour Insolit Paris (média food & bons plans IDF). Elle extrait des plans, transcrit l'audio, analyse la créativité, et génère des briefs de tournage.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Streamlit (UI)                              │
│  app.py  │  1_Analyser  │  4_Generer  │  7_Enrichir  │  ...        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
  modules/analyzer.py   modules/claude_mod.py  modules/whisper_mod.py
  (pipeline ffmpeg)      (Claude API)          (Whisper local)
         │                     │
         ▼                     ▼
  modules/database.py    Claude Haiku 4.5
  (SQLAlchemy / SQLite)  + Sonnet 4.5
```

---

## Pipeline d'analyse vidéo (analyzer.py)

```
Source (URL ou fichier)
    │
    ▼ copy_uploaded_video() / download_video()
    │
    ▼ get_video_duration()  [ffprobe]
    │
    ▼ compress_video()      [ffmpeg — 720p CRF28 900kbps → 5-10x plus petit]
    │
    ▼ detect_scene_changes()  [ffmpeg select=gt(scene,0.15) — seuil sensible]
    │                         [retourne liste de timestamps]
    │
    ▼ extract_frames_for_vision()  [1 frame par intervalle, base64 JPEG 480px]
    │
    ├──── ThreadPoolExecutor ─────────────────────────────────┐
    │                                                         │
    ▼                                                         ▼
analyze_frames_with_vision()                            transcribe()
(Claude Haiku Vision)                                   (Whisper small/medium)
~10-15s                                                 ~15-25s
    │                                                         │
    └─────────────────────── Parallèle ───────────────────────┘
                                │
                                ▼ Sauvegarde DB (plans, transcription)
                                │
                                ▼ analyze_creative()  [Claude Haiku]
                                │
                                ▼ extract_screenshots()  [ffmpeg]
                                │
                                ▼ Résultat final (~30-45s total)
```

---

## Modèles de données (database.py)

```
Video               → métadonnées, source, durée, chemin fichier
AnalysePegasus      → résultats Vision (nb_plans, rythme, luminosité...)
Plan                → chaque plan individuel (timestamp, type, texte, screenshot)
Transcription       → mots Whisper avec timestamps
AnalyseCreative     → hook_score, points_forts, recommandations, script_adapté
Stats               → vues, likes, completion_rate, performance_tag, note_humaine
Brief               → briefs générés (hook, script, plans, timing)
Ressource           → base de connaissances (scripts, patterns, guidelines)
```

---

## Modules

| Module | Rôle | Coût |
|--------|------|------|
| `analyzer.py` | Pipeline principal (ffmpeg + orchestration) | Gratuit (local) |
| `claude_mod.py` | Appels Claude (Vision + analyse + brief) | ~$0.01-0.02/vidéo |
| `whisper_mod.py` | Transcription audio locale | Gratuit (CPU) |
| `database.py` | ORM SQLAlchemy, modèles, helpers | — |
| `enrichment.py` | Sauvegarde stats et notes humaines | — |
| `styles.py` | Styles CSS partagés | — |
| `_env.py` | Chargement .env, résolution ROOT | — |

---

## Pages Streamlit

| Page | Fichier | Fonction |
|------|---------|----------|
| Accueil | `app.py` | Navigation + présentation |
| 1 Analyser | `1_Analyser.py` | Upload/URL → pipeline complet |
| 2 Bibliothèque | `2_Bibliotheque.py` | Toutes les vidéos analysées |
| 3 Patterns | `3_Patterns.py` | Rapport IA sur corrélations |
| 4 Générer | `4_Generer.py` | Génération de brief de tournage |
| 5 Compte | `5_Compte.py` | Analyse de compte TikTok/IG |
| 6 Base Connaissances | `6_Base_Connaissances.py` | Scripts, patterns, guidelines |
| 7 Enrichir | `7_Enrichir.py` | Import rapide + stats + notes humaines |

---

## Prompt Caching (réduction coûts Claude)

Le fichier `context_insolit.md` est injecté dans CHAQUE appel Claude avec `cache_control: {"type": "ephemeral"}`. Après le 1er appel :
- Tokens mis en cache : ~1000 tokens (contexte Insolit)
- Économie : -90% sur ces tokens (0.08$ vs 0.80$ / M tokens pour Haiku)
- Durée cache : 5 minutes (renouvelé à chaque appel actif)

---

## Threading / UI temps réel

Pour éviter que Streamlit freeze pendant l'analyse :
```python
# Thread background — lance l'analyse
t = threading.Thread(target=_run_analysis, daemon=True)
t.start()

# Main thread — polling loop chaque seconde
while t.is_alive():
    progress_bar.progress(pct)
    status_ph.markdown(step_label)
    time.sleep(1)   # ← libère le websocket Streamlit → UI se met à jour
```

---

## Détection de plans (ffmpeg scene filter)

```bash
ffmpeg -i video.mp4 \
  -filter:v "select='gt(scene,0.15)',showinfo" \
  -frames:v 80 -f null /dev/null
```

- Seuil `0.15` = sensible (détecte coupes nettes + transitions douces)
- Parse `pts_time:` depuis stderr pour récupérer les timestamps
- Filtre min 0.3s entre deux coupes (évite faux positifs)
- Fallback : découpage uniforme si < 3 scènes détectées

---

## Compression vidéo

```bash
ffmpeg -y -i input.mp4 \
  -vf "scale='if(gt(iw,ih),min(720,iw),-2)':'if(gt(iw,ih),-2,min(720,ih))'" \
  -c:v libx264 -crf 28 -b:v 900k -maxrate 1200k \
  -c:a aac -b:a 96k \
  -movflags +faststart -threads 2 \
  output_c.mp4
```

Résultat : 5-10x réduction de taille, maintient lisibilité pour Vision.
