import os
import json
import logging
from datetime import datetime
from modules._env import _ROOT  # noqa — charge .env

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text,
    DateTime, Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.pool import StaticPool


logger = logging.getLogger(__name__)

Base = declarative_base()
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///insolit_studio.db")
        # Railway fournit postgres:// mais SQLAlchemy requiert postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        if db_url.startswith("sqlite"):
            _engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            _engine = create_engine(db_url, pool_pre_ping=True)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    Base.metadata.create_all(bind=get_engine())
    _migrate_db(get_engine())
    logger.info("Base de données initialisée.")


def _migrate_db(engine):
    """Ajoute les nouvelles colonnes aux tables existantes (forward-only migrations)."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    if "ressources" not in inspector.get_table_names():
        return  # Sera créée par create_all

    existing_ressources = {col["name"] for col in inspector.get_columns("ressources")}
    new_cols_ressources = [
        ("url_source",          "TEXT"),
        ("nb_likes",            "INTEGER"),
        ("nb_commentaires",     "INTEGER"),
        ("nb_partages",         "INTEGER"),
        ("nb_enregistrements",  "INTEGER"),
        ("taux_completion",     "REAL"),
        ("hook_texte",          "TEXT"),
        ("ce_qui_marche",       "TEXT"),
        ("a_reproduire",        "TEXT"),
        ("contexte",            "TEXT"),
    ]
    with engine.begin() as conn:
        for col_name, col_type in new_cols_ressources:
            if col_name not in existing_ressources:
                try:
                    conn.execute(text("ALTER TABLE ressources ADD COLUMN " + col_name + " " + col_type))
                    logger.info("Migration: colonne ressources." + col_name + " ajoutée")
                except Exception as e:
                    logger.warning("Migration " + col_name + ": " + str(e))

    # Migrations table videos
    if "videos" in inspector.get_table_names():
        existing_videos = {col["name"] for col in inspector.get_columns("videos")}
        new_cols_videos = [
            ("type_offre",       "TEXT"),
            ("jour_publication", "TEXT"),
            ("nom_son",          "TEXT"),
            ("auteur_son",       "TEXT"),
            ("son_original",     "BOOLEAN"),
        ]
        with engine.begin() as conn:
            for col_name, col_type in new_cols_videos:
                if col_name not in existing_videos:
                    try:
                        conn.execute(text("ALTER TABLE videos ADD COLUMN " + col_name + " " + col_type))
                        logger.info("Migration: colonne videos." + col_name + " ajoutée")
                    except Exception as e:
                        logger.warning("Migration videos." + col_name + ": " + str(e))

    # Migrations table plans
    if "plans" in inspector.get_table_names():
        existing_plans = {col["name"] for col in inspector.get_columns("plans")}
        new_cols_plans = [
            ("changement_scene", "BOOLEAN"),
            ("personnes",        "TEXT"),
        ]
        with engine.begin() as conn:
            for col_name, col_type in new_cols_plans:
                if col_name not in existing_plans:
                    try:
                        conn.execute(text("ALTER TABLE plans ADD COLUMN " + col_name + " " + col_type))
                        logger.info("Migration: colonne plans." + col_name + " ajoutée")
                    except Exception as e:
                        logger.warning("Migration plans." + col_name + ": " + str(e))

    # Migrations table stats
    if "stats" in inspector.get_table_names():
        existing_stats = {col["name"] for col in inspector.get_columns("stats")}
        new_cols_stats = [
            ("taux_engagement", "REAL"),
            ("ratio_saves",     "REAL"),
            ("ratio_shares",    "REAL"),
        ]
        with engine.begin() as conn:
            for col_name, col_type in new_cols_stats:
                if col_name not in existing_stats:
                    try:
                        conn.execute(text("ALTER TABLE stats ADD COLUMN " + col_name + " " + col_type))
                        logger.info("Migration: colonne stats." + col_name + " ajoutée")
                    except Exception as e:
                        logger.warning("Migration stats." + col_name + ": " + str(e))


# ─── Modèles ────────────────────────────────────────────────────────────────

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)
    titre = Column(String(500))
    url_source = Column(Text)
    type_source = Column(String(50))  # mon_compte|concurrent|inspiration|secteur
    nom_compte = Column(String(200))
    date_publication = Column(String(50))
    categorie = Column(String(100))
    partenaire = Column(String(200))
    ville = Column(String(100))
    fichier_path = Column(Text)
    duree_secondes = Column(Float)
    statut_analyse = Column(String(50), default="en_attente")
    created_at = Column(DateTime, default=datetime.utcnow)
    # Amélioration 2 — type d'offre
    type_offre = Column(String(100))
    # Amélioration 3 — jour de publication
    jour_publication = Column(String(20))
    # Amélioration 6 — son/musique
    nom_son = Column(String(500))
    auteur_son = Column(String(200))
    son_original = Column(Boolean)

    analyse_pegasus = relationship("AnalysePegasus", back_populates="video", uselist=False)
    plans = relationship("Plan", back_populates="video")
    transcription = relationship("Transcription", back_populates="video")
    analyse_creative = relationship("AnalyseCreative", back_populates="video", uselist=False)
    stats = relationship("Stats", back_populates="video", uselist=False)


class AnalysePegasus(Base):
    __tablename__ = "analyse_pegasus"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True)
    raw_json = Column(Text)
    nb_plans = Column(Integer)
    duree_moyenne_plan = Column(Float)
    rythme_coupes_par_seconde = Column(Float)
    luminosite_moyenne = Column(Float)
    presence_visage = Column(Boolean)
    presence_texte_ecran = Column(Boolean)
    qualite_production = Column(Float)
    type_tournage = Column(String(50))
    mouvement_dominant = Column(String(50))
    marengo_embedding = Column(Text)  # JSON serialized list

    video = relationship("Video", back_populates="analyse_pegasus")

    def get_embedding(self):
        if self.marengo_embedding:
            return json.loads(self.marengo_embedding)
        return None

    def set_embedding(self, vector):
        self.marengo_embedding = json.dumps(vector)


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    numero_plan = Column(Integer)
    timestamp_debut = Column(Float)
    timestamp_fin = Column(Float)
    duree = Column(Float)
    screenshot_path = Column(Text)
    type_plan = Column(String(100))
    description = Column(Text)
    luminosite = Column(Float)
    mouvement = Column(String(100))
    presence_visage = Column(Boolean)
    expression = Column(String(100))
    texte_visible = Column(Text)
    couleur_dominante = Column(String(200))
    qualite = Column(Float)
    role_narratif = Column(String(100))
    points_forts = Column(Text)
    suggestion_amelioration = Column(Text)
    changement_scene = Column(Boolean, default=False)  # nouveau lieu OU nouvelle personne vs plan précédent
    personnes = Column(String(200))                    # description des personnes à l'écran

    video = relationship("Video", back_populates="plans")


class Transcription(Base):
    __tablename__ = "transcription"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    timestamp = Column(Float)
    mot = Column(String(200))
    confiance = Column(Float)

    video = relationship("Video", back_populates="transcription")


class AnalyseCreative(Base):
    __tablename__ = "analyse_creative"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True)
    hook_texte = Column(Text)
    hook_visuel = Column(Text)
    hook_type = Column(String(100))
    hook_score = Column(Float)
    hook_analyse = Column(Text)
    structure_narrative = Column(Text)
    points_forts = Column(Text)
    points_faibles = Column(Text)
    score_potentiel = Column(Float)
    recommandations = Column(Text)
    comparaison_base = Column(Text)
    adaptable_insolit = Column(Boolean)
    note_adaptation = Column(Text)

    video = relationship("Video", back_populates="analyse_creative")


class Stats(Base):
    __tablename__ = "stats"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True)
    vues = Column(Integer)
    likes = Column(Integer)
    comments = Column(Integer)
    shares = Column(Integer)
    saves = Column(Integer)
    completion_rate = Column(Float)
    clics_lien = Column(Integer)
    performance_tag = Column(String(50))  # viral|bon|moyen|mauvais
    note_humaine = Column(Text)
    annotee_par = Column(String(100))
    annotee_le = Column(DateTime)
    # Amélioration 5 — ratios engagement
    taux_engagement = Column(Float)
    ratio_saves = Column(Float)
    ratio_shares = Column(Float)

    video = relationship("Video", back_populates="stats")


class TopCommentaire(Base):
    """Amélioration 4 — Top commentaires des vidéos virales."""
    __tablename__ = "top_commentaires"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    texte = Column(Text)
    nb_likes = Column(Integer, default=0)
    position = Column(Integer)
    insight_claude = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Brief(Base):
    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True)
    type_contenu = Column(String(100))
    partenaire = Column(String(200))
    ville = Column(String(100))
    offre = Column(Text)
    objectif = Column(Text)
    duree_cible = Column(Integer)
    ton = Column(String(100))
    hook_suggere = Column(Text)
    script_complet = Column(Text)
    plans_json = Column(Text)
    niveau_difficulte = Column(String(50))
    temps_tournage_estime = Column(Integer)
    temps_montage_estime = Column(Integer)
    suggestions = Column(Text)
    base_sur_videos_ids = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Ressource(Base):
    """
    Base de connaissances : scripts, patterns, guidelines qui marchent.
    Utilisée par Claude pour enrichir la génération de briefs.
    Stats complètes + analyse qualitative pour améliorer l'IA avec le temps.
    """
    __tablename__ = "ressources"

    id = Column(Integer, primary_key=True)
    type_ressource = Column(String(50))   # script|pattern|guideline|inspiration|competitor
    titre = Column(String(500))
    contenu = Column(Text)                # Script/texte/pattern complet
    tags = Column(Text)                   # JSON array de tags

    # ── Source ────────────────────────────────────────────────────────────────
    url_source = Column(Text)             # URL TikTok/IG de la vidéo source
    compte_source = Column(String(200))   # @compte source

    # ── Stats engagement (données réelles) ───────────────────────────────────
    vues_approx = Column(Integer)         # Vues
    nb_likes = Column(Integer)            # Likes
    nb_commentaires = Column(Integer)     # Commentaires
    nb_partages = Column(Integer)         # Partages
    nb_enregistrements = Column(Integer)  # Enregistrements / Saves
    taux_completion = Column(Float)       # % de complétion (watch time)

    # ── Analyse qualitative ───────────────────────────────────────────────────
    hook_texte = Column(Text)             # Texte exact du hook (0-3s)
    ce_qui_marche = Column(Text)          # Pourquoi ça marche (analyse humaine)
    a_reproduire = Column(Text)           # Ce qu'on doit copier exactement
    contexte = Column(Text)              # Contexte spécifique (saison, actu, lieu...)

    # ── Meta ──────────────────────────────────────────────────────────────────
    performance_tag = Column(String(50))  # viral|bon|moyen
    notes = Column(Text)                  # Notes libres
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_precision_level():
    session = get_session()
    try:
        count = session.query(Stats).filter(Stats.performance_tag.isnot(None)).count()
        if count < 10:
            return count, "FAIBLE"
        elif count < 30:
            return count, "BONNE"
        else:
            return count, "EXCELLENTE"
    finally:
        session.close()


def get_all_videos_with_stats():
    session = get_session()
    try:
        videos = (
            session.query(Video)
            .filter(Video.statut_analyse == "complete")
            .order_by(Video.created_at.desc())
            .all()
        )
        result = []
        for v in videos:
            d = {
                "id": v.id,
                "titre": v.titre,
                "url_source": v.url_source,
                "type_source": v.type_source,
                "nom_compte": v.nom_compte,
                "categorie": v.categorie,
                "partenaire": v.partenaire,
                "ville": v.ville,
                "fichier_path": v.fichier_path,
                "duree_secondes": v.duree_secondes,
                "created_at": v.created_at,
            }
            if v.analyse_pegasus:
                d.update({
                    "nb_plans": v.analyse_pegasus.nb_plans,
                    "rythme_coupes_par_seconde": v.analyse_pegasus.rythme_coupes_par_seconde,
                    "qualite_production": v.analyse_pegasus.qualite_production,
                })
            if v.analyse_creative:
                d.update({
                    "hook_score": v.analyse_creative.hook_score,
                    "score_potentiel": v.analyse_creative.score_potentiel,
                    "hook_texte": v.analyse_creative.hook_texte,
                })
            if v.stats:
                d.update({
                    "vues": v.stats.vues,
                    "performance_tag": v.stats.performance_tag,
                    "completion_rate": v.stats.completion_rate,
                })
            result.append(d)
        return result
    finally:
        session.close()


def find_matching_kb_resources(hook_type: str = "", categorie: str = "",
                               hook_texte: str = "", limit: int = 3) -> list:
    """
    Trouve les ressources de la base de connaissances dont les tags correspondent
    au hook_type et à la catégorie de la vidéo analysée.
    Retourne une liste de dicts enrichis avec overlap_tags et match_score.
    """
    import json as _json
    session = get_session()
    try:
        resources = session.query(Ressource).all()
        if not resources:
            return []

        # Termes de recherche extraits de la vidéo
        search_terms = set()
        if hook_type:
            for part in hook_type.lower().replace("-", "_").split("_"):
                if len(part) > 2:
                    search_terms.add(part)
        if categorie:
            search_terms.add(categorie.lower())
            # Synonymes courants
            syns = {"restaurant": ["food", "resto", "restau"],
                    "bar": ["cocktail", "drinks"],
                    "café": ["coffee", "brunch"],
                    "bon plan": ["deal", "promo", "prix"]}
            for k, v in syns.items():
                if k in categorie.lower():
                    search_terms.update(v)
        # Mots-clés du hook texte (5 premiers mots significatifs)
        if hook_texte:
            stop = {"le", "la", "les", "de", "du", "des", "un", "une", "et", "à", "en", "on"}
            for word in hook_texte.lower().split():
                w = word.strip("«».,!?")
                if len(w) > 3 and w not in stop:
                    search_terms.add(w)
                if len(search_terms) >= 8:
                    break

        if not search_terms:
            return []

        scored = []
        for r in resources:
            r_tags = set()
            if r.tags:
                try:
                    for t in _json.loads(r.tags):
                        r_tags.add(t.lower().strip())
                except Exception:
                    pass
            if r.type_ressource:
                r_tags.add(r.type_ressource.lower())
            if r.hook_texte:
                # Les mots du hook de la ressource comptent aussi
                stop = {"le", "la", "les", "de", "du", "un", "une", "et", "à", "en"}
                for word in (r.hook_texte or "").lower().split():
                    w = word.strip("«».,!?")
                    if len(w) > 3 and w not in stop:
                        r_tags.add(w)

            overlap = search_terms & r_tags
            if overlap:
                scored.append({
                    "id":                  r.id,
                    "titre":               r.titre,
                    "contenu":             r.contenu,
                    "performance_tag":     r.performance_tag,
                    "vues_approx":         r.vues_approx,
                    "nb_likes":            getattr(r, "nb_likes", None),
                    "nb_enregistrements":  getattr(r, "nb_enregistrements", None),
                    "taux_completion":     getattr(r, "taux_completion", None),
                    "hook_texte":          getattr(r, "hook_texte", None),
                    "ce_qui_marche":       getattr(r, "ce_qui_marche", None),
                    "a_reproduire":        getattr(r, "a_reproduire", None),
                    "compte_source":       r.compte_source,
                    "tags":                r.tags,
                    "overlap_tags":        list(overlap),
                    "match_score":         len(overlap),
                })

        return sorted(scored, key=lambda x: -x["match_score"])[:limit]
    finally:
        session.close()


def get_scoring_referentiel() -> dict:
    """
    Calcule le référentiel de scores basé sur les vidéos annotées.
    Retourne {'viral': avg, 'bon': avg, 'moyen': avg, 'nb_annotees': n}
    """
    session = get_session()
    try:
        from sqlalchemy.orm import joinedload
        videos = (
            session.query(Video)
            .join(Stats, isouter=True)
            .join(AnalyseCreative, isouter=True)
            .filter(Video.statut_analyse == "complete")
            .all()
        )
        buckets = {"viral": [], "bon": [], "moyen": [], "mauvais": []}
        for v in videos:
            if v.stats and v.stats.performance_tag and v.analyse_creative:
                tag   = v.stats.performance_tag
                score = v.analyse_creative.score_potentiel
                if tag in buckets and score:
                    buckets[tag].append(float(score))

        result = {"nb_annotees": sum(len(v) for v in buckets.values())}
        for tag, scores in buckets.items():
            result[tag] = round(sum(scores) / len(scores), 1) if scores else None
        return result
    finally:
        session.close()


def delete_video(video_id: int) -> dict:
    """
    Supprime une vidéo et toutes ses données (DB + fichiers disque).
    Retourne {"success": True/False, "message": "..."}
    """
    import shutil
    session = get_session()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if not video:
            return {"success": False, "message": f"Vidéo #{video_id} introuvable"}

        fichier_path = video.fichier_path

        # Suppression en cascade (tables liées)
        session.query(Stats).filter_by(video_id=video_id).delete()
        session.query(AnalyseCreative).filter_by(video_id=video_id).delete()
        session.query(Transcription).filter_by(video_id=video_id).delete()
        session.query(Plan).filter_by(video_id=video_id).delete()
        session.query(AnalysePegasus).filter_by(video_id=video_id).delete()
        session.delete(video)
        session.commit()

        # Fichier vidéo
        if fichier_path and os.path.exists(fichier_path):
            os.remove(fichier_path)

        # Screenshots
        screenshots_dir = os.path.join("./screenshots", str(video_id))
        if os.path.exists(screenshots_dir):
            shutil.rmtree(screenshots_dir)

        logger.info(f"Vidéo #{video_id} supprimée")
        return {"success": True, "message": f"Vidéo #{video_id} supprimée"}
    except Exception as e:
        session.rollback()
        logger.error(f"Erreur suppression vidéo #{video_id}: {e}")
        return {"success": False, "message": str(e)}
    finally:
        session.close()


def compute_engagement_ratios(stats_obj):
    """Amélioration 5 — Calcule et stocke les ratios d'engagement en place."""
    vues = stats_obj.vues or 0
    if vues > 0:
        likes    = stats_obj.likes    or 0
        comments = stats_obj.comments or 0
        shares   = stats_obj.shares   or 0
        saves    = stats_obj.saves    or 0
        total_eng = likes + comments + shares + saves
        stats_obj.taux_engagement = round(total_eng / vues * 100, 2)
        stats_obj.ratio_saves     = round(saves / vues * 100, 2)
        stats_obj.ratio_shares    = round(shares / vues * 100, 2)


def get_best_videos(source_filter="all", limit=10):
    session = get_session()
    try:
        q = (
            session.query(Video)
            .join(Stats, isouter=True)
            .filter(Video.statut_analyse == "complete")
        )
        if source_filter == "mon_compte":
            q = q.filter(Video.type_source == "mon_compte")
        elif source_filter == "concurrent":
            q = q.filter(Video.type_source == "concurrent")
        q = q.order_by(Stats.vues.desc().nullslast()).limit(limit)
        return q.all()
    finally:
        session.close()


def get_full_knowledge_context() -> dict:
    """
    Retourne le contexte complet de la KB pour enrichir generate_brief().
    Inclut : scripts_viraux, hooks_performants, patterns_gagnants,
             videos_references annotées, stats_agregees.
    """
    session = get_session()
    try:
        ressources = session.query(Ressource).order_by(Ressource.created_at.desc()).all()

        scripts_viraux = []
        hooks_performants = []
        patterns_gagnants = []
        tous_les_contenus = []

        for r in ressources:
            item = {
                "id":                r.id,
                "type":              r.type_ressource,
                "titre":             r.titre,
                "contenu":           r.contenu,
                "performance":       r.performance_tag,
                "vues":              r.vues_approx,
                "nb_likes":          r.nb_likes,
                "nb_enregistrements": r.nb_enregistrements,
                "taux_completion":   r.taux_completion,
                "hook_texte":        r.hook_texte,
                "ce_qui_marche":     r.ce_qui_marche,
                "a_reproduire":      r.a_reproduire,
                "contexte":          r.contexte,
            }
            tous_les_contenus.append(item)

            if r.performance_tag == "viral":
                scripts_viraux.append(item)
            if r.hook_texte:
                hooks_performants.append({
                    "hook":          r.hook_texte,
                    "performance":   r.performance_tag,
                    "vues":          r.vues_approx,
                    "ce_qui_marche": r.ce_qui_marche,
                    "titre_source":  r.titre,
                })
            if r.type_ressource == "pattern":
                patterns_gagnants.append(item)

        # Vidéos annotées (références)
        videos_annotees = (
            session.query(Video)
            .join(Stats)
            .filter(Stats.performance_tag.isnot(None))
            .filter(Video.statut_analyse == "complete")
            .order_by(Stats.vues.desc().nullslast())
            .limit(20)
            .all()
        )

        videos_references = []
        for v in videos_annotees:
            ref = {
                "titre":           v.titre,
                "performance":     v.stats.performance_tag if v.stats else None,
                "vues":            v.stats.vues if v.stats else None,
                "completion_rate": v.stats.completion_rate if v.stats else None,
                "duree":           v.duree_secondes,
            }
            if v.analyse_creative:
                ref["hook_texte"] = v.analyse_creative.hook_texte
                ref["hook_type"]  = v.analyse_creative.hook_type
                ref["hook_score"] = v.analyse_creative.hook_score
                ref["points_forts"] = v.analyse_creative.points_forts
            videos_references.append(ref)

        nb_total_annot = len(videos_annotees)
        nb_viral = sum(1 for v in videos_annotees if v.stats and v.stats.performance_tag == "viral")
        nb_bon   = sum(1 for v in videos_annotees if v.stats and v.stats.performance_tag == "bon")

        # ── Amélioration 1 — Agrégation visuelles virales ─────────────────────
        caracteristiques_visuelles_virales = {}
        try:
            from collections import Counter
            videos_virales = (
                session.query(Video)
                .join(Stats)
                .filter(Stats.performance_tag == "viral")
                .filter(Video.statut_analyse == "complete")
                .all()
            )
            virales_avec_plans = [v for v in videos_virales if v.plans]
            if len(virales_avec_plans) >= 3:
                plans_1 = []
                for v in virales_avec_plans:
                    plan1 = next((p for p in v.plans if p.numero_plan == 1), None)
                    if plan1:
                        plans_1.append(plan1)
                if plans_1:
                    types_count = Counter(p.type_plan for p in plans_1 if p.type_plan)
                    roles_count = Counter(p.role_narratif for p in plans_1 if p.role_narratif)
                    durees = [p.duree for p in plans_1 if p.duree]
                    visages = [p for p in plans_1 if p.presence_visage and p.timestamp_debut is not None and p.timestamp_debut < 5]
                    lumin_all = []
                    for v in virales_avec_plans:
                        if v.analyse_pegasus and v.analyse_pegasus.luminosite_moyenne:
                            lumin_all.append(v.analyse_pegasus.luminosite_moyenne)
                    caracteristiques_visuelles_virales = {
                        "nb_videos_virales_analysees": len(virales_avec_plans),
                        "plan_1_type_dominant": types_count.most_common(1)[0][0] if types_count else "",
                        "plan_1_duree_moyenne": round(sum(durees) / len(durees), 2) if durees else 0,
                        "presence_visage_5s": round(len(visages) / len(plans_1), 2) if plans_1 else 0,
                        "role_hook_dominant": roles_count.most_common(1)[0][0] if roles_count else "",
                        "luminosite_moyenne_virales": round(sum(lumin_all) / len(lumin_all), 2) if lumin_all else 0,
                    }
        except Exception as _e:
            logger.warning("caracteristiques_visuelles_virales: " + str(_e))

        # ── Amélioration 2 — Performance par type d'offre ─────────────────────
        performance_par_offre = {}
        try:
            videos_avec_offre = (
                session.query(Video)
                .join(Stats)
                .filter(Video.type_offre.isnot(None))
                .filter(Video.type_offre != "")
                .filter(Video.statut_analyse == "complete")
                .all()
            )
            offre_buckets = {}
            for v in videos_avec_offre:
                offre = v.type_offre or "Non spécifié"
                if offre not in offre_buckets:
                    offre_buckets[offre] = []
                offre_buckets[offre].append(v)
            for offre, vids in offre_buckets.items():
                vues_list = [v.stats.vues for v in vids if v.stats and v.stats.vues]
                comp_list = [v.stats.completion_rate for v in vids if v.stats and v.stats.completion_rate]
                nb_viral_offre = sum(1 for v in vids if v.stats and v.stats.performance_tag == "viral")
                performance_par_offre[offre] = {
                    "nb_videos": len(vids),
                    "vues_moyennes": round(sum(vues_list) / len(vues_list)) if vues_list else 0,
                    "completion_moyen": round(sum(comp_list) / len(comp_list), 1) if comp_list else 0,
                    "taux_viral": round(nb_viral_offre / len(vids), 2) if vids else 0,
                }
        except Exception as _e:
            logger.warning("performance_par_offre: " + str(_e))

        # ── Amélioration 3 — Timing optimal ───────────────────────────────────
        timing_optimal = {}
        try:
            videos_avec_jour = (
                session.query(Video)
                .join(Stats)
                .filter(Video.jour_publication.isnot(None))
                .filter(Video.jour_publication != "")
                .filter(Video.statut_analyse == "complete")
                .all()
            )
            jour_buckets = {}
            for v in videos_avec_jour:
                jour = v.jour_publication
                if jour not in jour_buckets:
                    jour_buckets[jour] = []
                if v.stats and v.stats.vues:
                    jour_buckets[jour].append(v.stats.vues)
            jour_moyennes = {}
            for jour, vues_list in jour_buckets.items():
                if vues_list:
                    jour_moyennes[jour] = round(sum(vues_list) / len(vues_list))
            if jour_moyennes:
                meilleur_jour = max(jour_moyennes, key=jour_moyennes.get)
                timing_optimal = {
                    "vues_par_jour": jour_moyennes,
                    "meilleur_jour": meilleur_jour,
                    "vues_moyennes_meilleur_jour": jour_moyennes[meilleur_jour],
                }
        except Exception as _e:
            logger.warning("timing_optimal: " + str(_e))

        # ── Amélioration 4 — Insights commentaires viraux ─────────────────────
        insights_commentaires_viraux = []
        try:
            commentaires_viraux = (
                session.query(TopCommentaire)
                .join(Video, TopCommentaire.video_id == Video.id)
                .join(Stats, Stats.video_id == Video.id)
                .filter(Stats.performance_tag == "viral")
                .filter(TopCommentaire.insight_claude.isnot(None))
                .order_by(TopCommentaire.created_at.desc())
                .limit(5)
                .all()
            )
            insights_commentaires_viraux = [c.insight_claude for c in commentaires_viraux if c.insight_claude]
        except Exception as _e:
            logger.warning("insights_commentaires_viraux: " + str(_e))

        # ── Amélioration 6 — Analyse sons ─────────────────────────────────────
        analyse_sons = {}
        try:
            from collections import Counter as _Counter
            videos_avec_son = (
                session.query(Video)
                .join(Stats)
                .filter(Stats.performance_tag == "viral")
                .filter(Video.nom_son.isnot(None))
                .filter(Video.nom_son != "")
                .filter(Video.statut_analyse == "complete")
                .all()
            )
            if videos_avec_son:
                nb_original = sum(1 for v in videos_avec_son if v.son_original)
                sons_counter = _Counter(v.nom_son for v in videos_avec_son if v.nom_son)
                analyse_sons = {
                    "nb_videos_avec_son": len(videos_avec_son),
                    "ratio_son_original": round(nb_original / len(videos_avec_son), 2),
                    "sons_frequents": [{"son": s, "count": c} for s, c in sons_counter.most_common(5)],
                }
        except Exception as _e:
            logger.warning("analyse_sons: " + str(_e))

        return {
            "scripts_viraux":    scripts_viraux,
            "hooks_performants": hooks_performants,
            "patterns_gagnants": patterns_gagnants,
            "tous_les_contenus": tous_les_contenus,
            "videos_references": videos_references,
            "stats_agregees": {
                "nb_ressources_kb":    len(ressources),
                "nb_scripts_viraux":   len(scripts_viraux),
                "nb_hooks_kb":         len(hooks_performants),
                "nb_videos_annotees":  nb_total_annot,
                "nb_viral":            nb_viral,
                "nb_bon":              nb_bon,
            },
            "caracteristiques_visuelles_virales": caracteristiques_visuelles_virales,
            "performance_par_offre":              performance_par_offre,
            "timing_optimal":                     timing_optimal,
            "insights_commentaires_viraux":       insights_commentaires_viraux,
            "analyse_sons":                       analyse_sons,
        }
    finally:
        session.close()
