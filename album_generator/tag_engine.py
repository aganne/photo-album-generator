"""
tag_engine.py — Application des tags EXIF dans le pipeline de génération d'album.

Lit les tags via tag_manager (depuis les EXIF UserComment), applique leurs
effets sur le pipeline de génération d'album, et retourne le contexte de
tags pour les étapes suivantes (tri, scoring, dispatch, légendes).

Règles d'application :
    supprimer → Retire la photo du pipeline
    redater   → Modifie la date de tri chronologique
    hero      → Force la photo en slot héro de sa fenêtre
    favori    → Boost le score de +20 %
    texte     → Stocke la légende pour usage futur dans les templates
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .tag_manager import read_tags

logger = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────────────────

HERO_TAG = "hero"
FAVORI_TAG = "favori"
SUPPRIMER_TAG = "supprimer"
REDATER_TAG = "redater"
TEXTE_TAG = "texte"

FAVORI_BOOST = 1.20
SCORE_CAP = 1.0

SUPPORTED_TAGS = frozenset({
    HERO_TAG, FAVORI_TAG, SUPPRIMER_TAG, REDATER_TAG, TEXTE_TAG,
})


# ── Helper silencieux ────────────────────────────────────────────────

def _read_tags_safe(photo_path: Path) -> dict[str, str | bool]:
    """Lit les tags d'une photo avec gestion d'erreur silencieuse.

    En cas d'erreur (fichier corrompu, pas d'EXIF, etc.), retourne un
    dict vide pour ne pas bloquer le pipeline.
    """
    try:
        return read_tags(photo_path)
    except Exception as exc:
        logger.debug("Erreur lecture tags %s : %s", photo_path, exc)
        return {}


# ── API publique ─────────────────────────────────────────────────────

def apply_tags(
    photo_paths: list[Path],
    photos_dir: Path | None = None,
) -> tuple[list[Path], dict[str, dict[str, Any]]]:
    """Applique les tags EXIF aux photos avant le pipeline de scoring.

    Pour chaque photo, lit les tags depuis l'EXIF et :
    - Supprime les photos taggées ``supprimer`` du pipeline
    - Conserve les autres tags dans ``tag_context`` pour les étapes
      suivantes (tri, scoring, dispatch, légendes)

    Args:
        photo_paths: Liste des chemins de photos (Path) à traiter.
        photos_dir: Dossier racine des photos (optionnel, inutilisé
                    pour l'instant — sert pour les résolutions futures).

    Returns:
        (filtered_paths, tag_context)
        - filtered_paths : photos restantes après suppression des
          photos taggées ``supprimer``
        - tag_context : dict {chemin_absolu: dict_des_tags} pour toutes
          les photos conservées qui ont au moins un tag
    """
    filtered: list[Path] = []
    tag_context: dict[str, dict[str, Any]] = {}

    for fp in photo_paths:
        abs_path = str(fp.resolve())
        tags = _read_tags_safe(fp)

        if not tags:
            # Pas de tags → photo normale, on garde
            filtered.append(fp)
            continue

        # ── Tag supprimer → retirer du pipeline ──
        if tags.get(SUPPRIMER_TAG) is True:
            logger.info("   🗑️  Photo supprimée par tag : %s", fp.name)
            continue

        # Conserver la photo et ses tags dans le contexte
        filtered.append(fp)
        tag_context[abs_path] = dict(tags)

    # Logging récap
    if tag_context:
        hero_count = sum(1 for t in tag_context.values() if t.get(HERO_TAG))
        favori_count = sum(1 for t in tag_context.values() if t.get(FAVORI_TAG))
        redater_count = sum(1 for t in tag_context.values() if t.get(REDATER_TAG))
        texte_count = sum(1 for t in tag_context.values() if t.get(TEXTE_TAG))
        parts = []
        if hero_count:
            parts.append(f"{hero_count} hero")
        if favori_count:
            parts.append(f"{favori_count} favori")
        if redater_count:
            parts.append(f"{redater_count} redater")
        if texte_count:
            parts.append(f"{texte_count} texte")
        if parts:
            logger.info("   🏷️  Tags actifs : %s", ", ".join(parts))

    return filtered, tag_context


def get_effective_date(
    photo_path: Path,
    tag_context: dict[str, dict[str, Any]] | None = None,
) -> datetime | None:
    """Retourne la date effective d'une photo pour le tri chronologique.

    Si la photo a le tag ``redater=YYYY-MM-DD``, utilise cette date.
    Sinon, utilise la date EXIF réelle via ``extract_exif_date``.

    Args:
        photo_path: Chemin de la photo.
        tag_context: Contexte de tags (optionnel). Si None ou absent,
                     ignore les tags.

    Returns:
        Datetime ou None si aucune date trouvée (ni tag, ni EXIF).
    """
    if tag_context:
        abs_path = str(photo_path.resolve())
        tags = tag_context.get(abs_path, {})
        redater_val = tags.get(REDATER_TAG)
        if redater_val:
            try:
                if isinstance(redater_val, str):
                    return datetime.strptime(redater_val, "%Y-%m-%d")
            except (ValueError, TypeError):
                logger.warning(
                    "Format redater invalide pour %s : %s",
                    photo_path.name, redater_val,
                )

    # Fallback : date EXIF réelle
    from .scoring import extract_exif_date  # évite import circulaire
    return extract_exif_date(photo_path)


def is_hero_tagged(
    photo_path: Path,
    tag_context: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Vérifie si la photo a le tag ``hero``.

    Args:
        photo_path: Chemin de la photo.
        tag_context: Contexte de tags (optionnel).

    Returns:
        True si le tag ``hero`` est présent et vaut True.
    """
    if not tag_context:
        return False
    abs_path = str(photo_path.resolve())
    tags = tag_context.get(abs_path, {})
    return bool(tags.get(HERO_TAG))


def get_score_boost(
    photo_path: Path | str,
    tag_context: dict[str, dict[str, Any]] | None = None,
) -> float:
    """Retourne le multiplicateur de score pour une photo.

    - ``favori`` → 1.20
    - Sinon → 1.00

    Args:
        photo_path: Chemin de la photo (Path ou str).
        tag_context: Contexte de tags (optionnel).

    Returns:
        Facteur multiplicateur à appliquer au score.
    """
    if not tag_context:
        return 1.0
    abs_path = str(Path(photo_path).resolve())
    tags = tag_context.get(abs_path, {})
    if tags.get(FAVORI_TAG) is True:
        return FAVORI_BOOST
    return 1.0


def get_legend(
    photo_path: Path | str,
    tag_context: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Retourne le texte de légende si la photo a le tag ``texte``.

    Args:
        photo_path: Chemin de la photo (Path ou str).
        tag_context: Contexte de tags (optionnel).

    Returns:
        Texte de légende, ou chaîne vide si absent.
    """
    if not tag_context:
        return ""
    abs_path = str(Path(photo_path).resolve())
    tags = tag_context.get(abs_path, {})
    value = tags.get(TEXTE_TAG)
    if value and isinstance(value, str):
        return value
    return ""


def count_tagged_photos(
    tag_context: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Compte les photos par type de tag pour le log récap.

    Args:
        tag_context: Contexte de tags.

    Returns:
        Dict {nom_tag: nombre_de_photos}.
    """
    counts: dict[str, int] = {}
    for tags in tag_context.values():
        for tag in SUPPORTED_TAGS:
            if tag in tags:
                counts[tag] = counts.get(tag, 0) + 1
    return counts
