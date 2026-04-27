# Coûts API — Insolit Studio

## Modèles utilisés

| Modèle | Usage | Coût input | Coût output | Cache read |
|--------|-------|-----------|------------|------------|
| claude-haiku-4-5 | Analyse vidéo, patterns | 0.80$/M | 4.00$/M | 0.08$/M |
| claude-sonnet-4-5 | Génération brief | 3.00$/M | 15.00$/M | 0.30$/M |

## Coût par opération

### Analyse vidéo complète (pipeline Vision)
| Étape | Modèle | Tokens input | Tokens output | Coût estimé |
|-------|--------|-------------|--------------|-------------|
| Vision (frames) | Haiku | ~2000-4000 | ~1500 | ~$0.008-0.012 |
| Analyse créative | Haiku | ~1500 (dont 1000 cachés) | ~800 | ~$0.002-0.004 |
| **Total analyse** | | | | **~$0.010-0.016** |

### Génération de brief
| Étape | Modèle | Tokens | Coût estimé |
|-------|--------|--------|-------------|
| Brief complet | Sonnet | 3000in / 2000out | ~$0.039 |

### Rapport de patterns
| Modèle | Tokens | Coût estimé |
|--------|--------|-------------|
| Haiku | 2000in / 1000out | ~$0.006 |

## Économies prompt caching

Le `context_insolit.md` (~1000 tokens) est mis en cache avec `cache_control: {"type": "ephemeral"}`.

**Sans cache** : 1000 tokens × $0.80/M = $0.0008 par appel
**Avec cache** (après 1er appel) : 1000 tokens × $0.08/M = $0.00008 par appel
**Économie** : -90% sur le contexte statique

## Coût mensuel estimé

Usage modéré (50 analyses + 20 briefs / mois) :
- 50 analyses × $0.013 = $0.65
- 20 briefs × $0.039 = $0.78
- 10 rapports × $0.006 = $0.06
- **Total : ~$1.50/mois**

Usage intensif (200 analyses + 50 briefs) :
- **Total : ~$5-8/mois**

## Whisper — coût = $0

Whisper tourne localement sur le serveur Railway (CPU).
- Modèle `small` sur Railway (500MB RAM)
- Modèle `medium` en local (1.5GB RAM, meilleure précision)
- Téléchargé au premier appel (~75MB pour small, ~461MB pour medium)

## Optimisations appliquées

1. **Haiku au lieu de Sonnet** pour Vision + analyse créative → 10x moins cher
2. **Prompt caching** sur context_insolit.md → -90% sur le contexte
3. **Max frames = 20** envoyées à Vision → limite les tokens image
4. **Truncate transcription à 600 chars** avant envoi à Claude → réduit tokens
5. **Plans summary** limité à 10 plans avant envoi à analyze_creative → réduit tokens
6. **Whisper local** (pas d'API) → $0 pour la transcription
