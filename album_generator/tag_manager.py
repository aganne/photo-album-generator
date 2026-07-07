"""
tag_manager.py — Lecture/écriture des tags d'album dans les métadonnées EXIF.

Stocke les tags (hero, favori, supprimer, redater, texte) dans le champ
EXIF UserComment (tag 0x9286) des fichiers JPEG, en utilisant piexif
pour éviter de réencoder l'image → aucune perte de qualité.

Format dans UserComment :
    album_tags: key1=value1, key2=value2

Exemple :
    album_tags: hero, favori, redater=2012-06-15, texte=Premier bain

Les autres contenus du UserComment (non-album_tags) sont préservés.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import piexif

logger = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────────────────

ALBUM_TAGS_PREFIX = "album_tags:"
"""Préfixe qui identifie la ligne de nos tags dans le champ UserComment."""

BOOLEAN_TAGS = frozenset({"supprimer", "hero", "favori"})
"""Tags de type booléen — stockés sans valeur si True, avec '=false' si False."""

STRING_TAGS = frozenset({"redater", "texte"})
"""Tags de type chaîne — toujours stockés avec '=valeur'."""

ALL_SUPPORTED_TAGS = BOOLEAN_TAGS | STRING_TAGS
"""Ensemble complet des clés supportées."""

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".JPG", ".JPEG"})
"""Extensions de fichiers prises en charge pour la lecture/écriture de tags."""

# ── Encodage / Décodage UserComment ──────────────────────────────────

_ENCODING_PREFIXES = {
    b"ASCII\x00\x00\x00": "ascii",
    b"UNICODE\x00":       "utf-16-le",
    b"\x00\x00\x00\x00\x00\x00\x00\x00": "ascii",
}


def _decode_user_comment(data: bytes) -> str:
    """Décode un champ UserComment EXIF depuis les bytes bruts.

    Gère les préfixes d'encodage standards (8 bytes) que certains outils
    (Digikam, ExifTool) peuvent préfixer. Si aucun préfixe reconnu, tente
    UTF-8 direct.
    """
    if not data:
        return ""

    rest = data
    for prefix, encoding in _ENCODING_PREFIXES.items():
        if data[:8] == prefix:
            rest = data[8:]
            break
    else:
        # Pas de préfixe reconnu — on suppose UTF-8
        pass

    # Tentative principale
    try:
        return rest.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Fallback : ascii en remplaçant les caractères hors répertoire
    try:
        return rest.decode("ascii", errors="replace")
    except Exception:
        return rest.decode("utf-8", errors="replace")


def _encode_user_comment(text: str) -> bytes:
    """Encode un texte en UserComment EXIF (UTF-8, sans préfixe)."""
    return text.encode("utf-8")


# ── Parsing / Formatage des tags ─────────────────────────────────────

def _parse_tags_from_comment(comment: str) -> dict[str, str | bool]:
    """Extrait le dictionnaire de tags depuis le texte complet UserComment.

    Cherche la ligne commençant par ``album_tags:`` et parse les
    paires clé=valeur ou clés nues (booléennes = True).
    """
    result: dict[str, str | bool] = {}
    for line in comment.split("\n"):
        stripped = line.strip()
        if not stripped.startswith(ALBUM_TAGS_PREFIX):
            continue

        tags_str = stripped[len(ALBUM_TAGS_PREFIX):].strip()
        if not tags_str:
            continue

        for part in tags_str.split(","):
            part = part.strip()
            if not part:
                continue

            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
            else:
                key = part.strip().lower()
                value = "True"

            if key in BOOLEAN_TAGS:
                result[key] = value.lower() in ("true", "1", "yes", "")
            else:
                result[key] = value

    return result


def _format_tags_to_line(tags: dict[str, str | bool]) -> str:
    """Formate le dictionnaire de tags en ligne ``album_tags: ...``.

    Les tags booléens True sont écrits sans valeur (juste la clé).
    Les tags booléens False sont écrits avec ``=false``.
    Les tags chaîne sont toujours écrits avec ``=valeur``.
    """
    parts: list[str] = []
    for key, value in sorted(tags.items()):
        if key in BOOLEAN_TAGS:
            if value is True or value == "True":
                parts.append(key)
            else:
                parts.append(f"{key}=false")
        else:
            parts.append(f"{key}={value}")

    if not parts:
        return ""
    return f"{ALBUM_TAGS_PREFIX} {', '.join(parts)}"


# ── Accès bas niveau EXIF ────────────────────────────────────────────

def _read_raw_comment(photo_path: Path) -> str:
    """Lit et décode le champ UserComment EXIF d'une photo.

    Retourne une chaîne vide si la photo n'a pas d'EXIF ou de UserComment.
    """
    try:
        exif_dict = piexif.load(str(photo_path))
    except Exception as exc:
        logger.warning("Impossible de lire les EXIF de %s : %s", photo_path, exc)
        return ""

    user_comment_bytes = exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment)
    if user_comment_bytes is None:
        return ""

    try:
        return _decode_user_comment(user_comment_bytes)
    except Exception as exc:
        logger.warning("Erreur de décodage UserComment pour %s : %s", photo_path, exc)
        return ""


def _write_raw_comment(photo_path: Path, full_comment: str) -> None:
    """Écrit le texte complet dans le champ UserComment des EXIF.

    Si la photo n'a pas de structure EXIF, en crée une minimale.
    Lève une exception en cas d'échec d'écriture.
    """
    try:
        exif_dict = piexif.load(str(photo_path))
    except Exception:
        # Pas d'EXIF ou corrompu → structure minimale
        exif_dict = {
            "0th": {},
            "Exif": {},
            "GPS": {},
            "1st": {},
            "thumbnail": None,
        }

    bytes_data = _encode_user_comment(full_comment) if full_comment else b""
    exif_dict["Exif"][piexif.ExifIFD.UserComment] = bytes_data

    try:
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(photo_path))
    except Exception as exc:
        logger.error("Erreur d'écriture EXIF pour %s : %s", photo_path, exc)
        raise


# ── API publique ─────────────────────────────────────────────────────

def read_tags(photo_path: Path) -> dict[str, str | bool]:
    """Lit les tags d'album depuis les métadonnées EXIF de la photo.

    Args:
        photo_path: Chemin vers le fichier photo (JPG/JPEG).

    Returns:
        Dictionnaire des tags {clé: valeur}. Vide si aucun tag trouvé.
    """
    comment = _read_raw_comment(photo_path)
    return _parse_tags_from_comment(comment)


def write_tags(photo_path: Path, tags: dict[str, str | bool]) -> None:
    """Écrit les tags d'album dans les EXIF de la photo.

    Remplace tous les tags d'album existants (mergés atomiquement).
    Les autres lignes du UserComment (non ``album_tags:``) sont préservées.

    Args:
        photo_path: Chemin vers le fichier photo.
        tags: Dictionnaire des tags à écrire (ex: ``{"hero": True, "texte": "Mon texte"}``).
    """
    comment = _read_raw_comment(photo_path)

    # Filtrer les anciennes lignes album_tags
    lines = comment.split("\n")
    kept_lines = [l for l in lines if not l.strip().startswith(ALBUM_TAGS_PREFIX)]

    # Ajouter la nouvelle ligne si on a des tags
    tags_line = _format_tags_to_line(tags)
    if tags_line:
        kept_lines.append(tags_line)

    # Reconstruire le commentaire complet
    new_comment = "\n".join(kept_lines).strip()
    _write_raw_comment(photo_path, new_comment)


def add_tag(photo_path: Path, key: str, value: str | bool = True) -> None:
    """Ajoute ou modifie un tag sans toucher aux autres.

    Args:
        photo_path: Chemin vers le fichier photo.
        key: Clé du tag (``hero``, ``favori``, ``supprimer``, ``redater``, ``texte``).
        value: Valeur. ``True`` par défaut pour les tags booléens.
    """
    tags = read_tags(photo_path)
    tags[key] = value
    write_tags(photo_path, tags)


def remove_tag(photo_path: Path, key: str) -> None:
    """Supprime un tag spécifique d'une photo.

    Si le tag n'existe pas, la fonction ne fait rien (pas d'erreur).

    Args:
        photo_path: Chemin vers le fichier photo.
        key: Clé du tag à supprimer.
    """
    tags = read_tags(photo_path)
    if key not in tags:
        return
    del tags[key]
    write_tags(photo_path, tags)


def clear_all_tags(photo_path: Path) -> None:
    """Supprime tous les tags d'album d'une photo.

    Les autres contenus du UserComment (non ``album_tags:``) sont préservés.

    Args:
        photo_path: Chemin vers le fichier photo.
    """
    comment = _read_raw_comment(photo_path)
    lines = comment.split("\n")
    kept_lines = [l for l in lines if not l.strip().startswith(ALBUM_TAGS_PREFIX)]
    new_comment = "\n".join(kept_lines).strip()
    if new_comment == comment and comment:
        # Rien à changer
        return
    _write_raw_comment(photo_path, new_comment)


def list_all_tags(photos_dir: Path) -> dict[str, dict[str, str | bool]]:
    """Scanne toutes les photos d'un dossier et retourne leurs tags.

    Args:
        photos_dir: Chemin du dossier contenant les photos.

    Returns:
        Dictionnaire ``{nom_de_fichier: {tags...}}`` pour les photos qui
        ont au moins un tag d'album. Trié par nom de fichier.
    """
    result: dict[str, dict[str, str | bool]] = {}

    if not photos_dir.is_dir():
        logger.warning("Dossier introuvable : %s", photos_dir)
        return result

    for fpath in sorted(photos_dir.iterdir()):
        if fpath.suffix not in IMAGE_EXTENSIONS or not fpath.is_file():
            continue
        try:
            tags = read_tags(fpath)
            if tags:
                result[fpath.name] = tags
        except Exception as exc:
            logger.warning("Erreur lecture %s : %s", fpath, exc)
            continue

    return result
