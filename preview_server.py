#!/usr/bin/env python3
"""
preview_server.py — Serveur de prévisualisation de l'album photo.

Lance un serveur Flask (port 8888 par défaut) qui expose une API REST
pour prévisualiser le dispatch de l'album, tagger les photos via EXIF,
et régénérer l'album.

Usage:
    python3 preview_server.py --photos /root/mael_onedrive --port 8888
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, ImageOps

# Ajouter le projet au path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from album_generator.tag_manager import (
    add_tag,
    read_tags,
    remove_tag,
    clear_all_tags,
    list_all_tags,
)
from album_generator.templates import load_templates, dispatch_album
from album_generator.scoring import extract_exif_date
from album_generator.tag_engine import get_effective_date

# Extensions vidéo reconnues
VIDEO_EXTENSIONS = frozenset({".mts", ".MTS", ".mp4", ".MP4", ".mov", ".MOV", ".avi", ".AVI"})

# ── Configuration ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("preview_server")

app = Flask(__name__, static_folder=None)

# État global
PHOTOS_DIR: Path = Path("/root/mael_2012_photos")
OUTPUT_DIR: Path = PROJECT_DIR / "output"
SCORING_REPORT_PATH: Path = OUTPUT_DIR / "scoring_report.json"
PROJECT_DIR_OBJ: Path = PROJECT_DIR
PREVIEW_STATIC_DIR: Path = PROJECT_DIR / "preview_static"

# Cache des scores chargé une fois
_scores_cache: Optional[Dict[str, Dict]] = None
_scores_lock = threading.Lock()

# État de la régénération
_regenerating = False
_regenerate_progress = ""
_regenerate_lock = threading.Lock()


# ── Utilitaires ───────────────────────────────────────────────────────

def _safe_photo_path(filename: str) -> Path:
    """Resolve a photo path and validate it is under PHOTOS_DIR.

    Prevents path traversal attacks (e.g. ``../../etc/passwd``).
    """
    candidate = (PHOTOS_DIR / filename).resolve()
    # resolve() normalises and removes ../ components, but we still
    # need to confirm the final path is inside the photos directory.
    try:
        candidate.relative_to(PHOTOS_DIR.resolve())
    except ValueError:
        raise ValueError("Photo path escapes PHOTOS_DIR")
    return candidate


def load_scores() -> Dict[str, Dict]:
    """Charge et met en cache le scoring_report.json."""
    global _scores_cache
    with _scores_lock:
        if _scores_cache is not None:
            return _scores_cache

        if not SCORING_REPORT_PATH.exists():
            logger.warning("scoring_report.json introuvable — scoring nécessaire")
            _scores_cache = {"scores": {}, "config": {}, "dispatch": {}}
            return _scores_cache

        with open(SCORING_REPORT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _scores_cache = data
        return data


def invalidate_scores_cache() -> None:
    """Invalide le cache pour recharger au prochain appel."""
    global _scores_cache
    with _scores_lock:
        _scores_cache = None


def get_photo_score(photo_path: Path) -> Optional[Dict]:
    """Cherche le score d'une photo dans le rapport en faisant correspondre le nom de fichier."""
    data = load_scores()
    scores_dict = data.get("scores", {})

    # Essai de matching direct + par nom de fichier
    photo_name = photo_path.name
    best = None

    for crop_path_str, score_data in scores_dict.items():
        if photo_name in crop_path_str:
            best = score_data
            break

    # Fallback: essai sans le préfixe "rot_" 
    if best is None and photo_name.startswith("rot_"):
        stripped = photo_name[4:]  # enlève "rot_"
        for crop_path_str, score_data in scores_dict.items():
            if stripped in crop_path_str:
                best = score_data
                break

    return best


def scan_photos() -> List[Path]:
    """Liste les fichiers JPG dans le répertoire des photos."""
    photos = []
    for f in sorted(PHOTOS_DIR.iterdir()):
        ext = f.suffix.upper()
        if ext in (".JPG", ".JPEG") and f.is_file():
            photos.append(f)
    return photos


def scan_videos() -> List[Path]:
    """Liste les fichiers vidéo dans le répertoire des photos."""
    videos = []
    for f in sorted(PHOTOS_DIR.iterdir()):
        if f.suffix in VIDEO_EXTENSIONS and f.is_file():
            videos.append(f)
    return videos


def get_photo_info(photo_path: Path) -> Dict[str, Any]:
    """Retourne les infos complètes d'une photo : tags, score, date EXIF."""
    tags = read_tags(photo_path)
    score_data = get_photo_score(photo_path)
    exif_date = extract_exif_date(photo_path)

    info = {
        "filename": photo_path.name,
        "path": str(photo_path),
        "tags": _serialize_tags(tags),
    }

    if score_data:
        info["score"] = score_data.get("total", 0)
        info["score_details"] = score_data.get("details", {})

    if exif_date:
        info["exif_date"] = exif_date.isoformat()

    return info


def _serialize_tags(tags: Dict[str, Any]) -> Dict[str, Any]:
    """Sérialise les tags (booléens en bool Python)."""
    result = {}
    for k, v in tags.items():
        if isinstance(v, bool):
            result[k] = v
        elif isinstance(v, str) and v.lower() == "true":
            result[k] = True
        elif isinstance(v, str) and v.lower() == "false":
            result[k] = False
        else:
            result[k] = v
    return result


def _build_tag_context() -> Dict[str, Dict]:
    """Construit le dict tag_context {chemin_absolu: {tag: valeur}} pour le dispatch V6.

    Lit les tags EXIF de toutes les photos et les transforme au format
    attendu par dispatch_album() et tag_engine.
    """
    photos = scan_photos()
    tag_context: Dict[str, Dict] = {}
    for photo_path in photos:
        try:
            raw_tags = read_tags(photo_path)
            # Filtrer les tags valides et booléens (ignorer redater/texte qui sont des str)
            tags = {}
            for k, v in raw_tags.items():
                if k in ("hero", "favori", "supprimer", "pas_hero"):
                    if isinstance(v, bool):
                        tags[k] = v
                    elif isinstance(v, str) and v.lower() == "true":
                        tags[k] = True
                    elif isinstance(v, str) and v.lower() == "false":
                        tags[k] = False
                elif k in ("redater", "texte", "zoom", "recadrage"):
                    tags[k] = str(v) if v else ""
            if any(tags.values()):  # Ne garder que les photos qui ont au moins un tag actif
                tag_context[str(photo_path.resolve())] = tags
        except Exception as e:
            logger.debug("Erreur lecture tags %s: %s", photo_path.name, e)
    if tag_context:
        logger.info("🏷️  Tag context chargé: %d photos taggées", len(tag_context))
    return tag_context


def build_photo_scores_for_dispatch() -> Optional[List[Tuple[str, float, Dict]]]:
    """Construit la liste `photo_scores` attendue par dispatch_album().

    Returns:
        List de (path, score, details) triée par date EXIF (avec support redater),
        ou None si pas de scores disponibles.
    """
    photos = scan_photos()
    if not photos:
        return None

    # Construire le tag_context pour le support du tag redater
    tag_context = _build_tag_context()

    scored_list = []
    for photo_path in photos:
        score_data = get_photo_score(photo_path)
        if score_data:
            total = score_data.get("total", 0.0)
            details = score_data.get("details", {})
            scored_list.append((str(photo_path), total, details))

    if not scored_list:
        return None

    # Tri par date effective (EXIF ou redater si tag présent)
    def exif_sort_key(item):
        path = item[0]
        dt = get_effective_date(Path(path), tag_context) if tag_context else extract_exif_date(Path(path))
        return dt.isoformat() if dt else ""

    scored_list.sort(key=exif_sort_key)
    return scored_list


# ── Endpoints API ─────────────────────────────────────────────────────

@app.route("/api/photos")
def api_photos():
    """Liste toutes les photos avec leurs tags."""
    photos = scan_photos()
    result = []
    for photo_path in photos:
        info = get_photo_info(photo_path)
        result.append({
            "filename": info["filename"],
            "path": info["path"],
            "tags": info["tags"],
            "score": info.get("score"),
            "exif_date": info.get("exif_date"),
        })
    return jsonify(result)


@app.route("/api/preview")
def api_preview():
    """Retourne la structure de l'album prévue par dispatch_album().

    Construit un aperçu complet page par page sans régénérer le PDF.
    """
    # Charger les templates
    try:
        tpl_by_id = load_templates()
    except Exception as e:
        return jsonify({"error": f"Erreur chargement templates: {e}"}), 500

    # Construire les scores pour le dispatch
    photo_scores = build_photo_scores_for_dispatch()
    if not photo_scores:
        return jsonify({
            "error": "Aucun score disponible. Lancez d'abord le scoring.",
            "need_scoring": True,
            "pages": [],
        })

    # Construire le tag_context à partir des tags EXIF
    try:
        tag_context = _build_tag_context()
    except Exception as e:
        logger.warning("Erreur tag_context: %s", e)
        tag_context = None

    # Lancer le dispatch V6 avec les tags
    try:
        pages = dispatch_album(photo_scores, tpl_by_id, window_size=40, tag_context=tag_context)
    except Exception as e:
        logger.error("Erreur dispatch_album: %s", e)
        return jsonify({"error": f"Erreur dispatch: {e}"}), 500

    # Formater la réponse
    result_pages = []
    for i, (template_id, photo_paths, is_hero) in enumerate(pages, start=1):
        page_photos = []
        for p in photo_paths:
            path_obj = Path(p)
            filename = path_obj.name

            # Déterminer la zone_id depuis le template
            tpl = tpl_by_id.get(template_id, {})
            zones = tpl.get("zones", [])
            photo_zones = [z for z in zones if z["type"] == "photo"]

            page_photos.append({
                "filename": filename,
                "path": p,
                "zone_id": photo_zones[len(page_photos)]["id"]
                if len(page_photos) < len(photo_zones)
                else f"p{len(page_photos)+1}",
            })

        result_pages.append({
            "page_num": i,
            "template_id": template_id,
            "is_hero": is_hero,
            "photos": page_photos,
        })

    # ── Pages vidéo T9 ──
    # Ajouter une page T9 pour chaque vidéo trouvée dans le dossier photos
    videos = scan_videos()
    if videos:
        logger.info("🎬 %d vidéos détectées — ajout pages T9", len(videos))
        for vid in videos:
            result_pages.append({
                "page_num": len(result_pages) + 1,
                "template_id": "T9",
                "is_hero": False,
                "photos": [{
                    "filename": vid.name,
                    "path": str(vid),
                    "zone_id": "video",
                }],
                "is_video": True,
            })

    return jsonify(result_pages)


@app.route("/api/photo/<path:filename>/info")
def api_photo_info(filename: str):
    """Retourne les infos détaillées d'une photo."""
    try:
        photo_path = _safe_photo_path(filename)
    except ValueError:
        return jsonify({"error": "Chemin de photo invalide"}), 400
    if not photo_path.exists():
        return jsonify({"error": f"Photo introuvable: {filename}"}), 404
    info = get_photo_info(photo_path)
    return jsonify(info)


@app.route("/api/photo/<path:filename>/thumbnail")
def api_photo_thumbnail(filename: str):
    """Retourne une vignette JPEG de la photo (600px pour preview)."""
    try:
        photo_path = _safe_photo_path(filename)
    except ValueError:
        return jsonify({"error": "Chemin de photo invalide"}), 400
    if not photo_path.exists():
        return jsonify({"error": f"Photo introuvable: {filename}"}), 404

    try:
        img = Image.open(photo_path)
        img = ImageOps.exif_transpose(img) or img
        img.thumbnail((600, 600), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")
    except Exception as e:
        logger.error("Erreur thumbnail %s: %s", filename, e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/photo/<path:filename>/tag", methods=["POST"])
def api_photo_add_tag(filename: str):
    """Ajoute ou modifie un tag sur une photo (écriture EXIF immédiate)."""
    try:
        photo_path = _safe_photo_path(filename)
    except ValueError:
        return jsonify({"error": "Chemin de photo invalide"}), 400
    if not photo_path.exists():
        return jsonify({"error": f"Photo introuvable: {filename}"}), 404

    data = request.get_json(silent=True) or {}
    tag = data.get("tag", "").strip().lower()
    value = data.get("value", True)

    if not tag:
        return jsonify({"error": "Paramètre 'tag' requis"}), 400

    # Validation du tag
    valid_tags = {"hero", "favori", "supprimer", "redater", "texte", "pas_hero", "zoom", "recadrage"}
    if tag not in valid_tags:
        return jsonify({"error": f"Tag invalide: {tag}. Tags supportés: {', '.join(valid_tags)}"}), 400

    try:
        if tag in ("redater", "texte", "zoom", "recadrage"):
            if not isinstance(value, str) or not value.strip():
                return jsonify({"error": f"Le tag '{tag}' requiert une valeur texte"}), 400
            if tag == "redater":
                from datetime import datetime
                try:
                    datetime.strptime(value.strip(), "%Y-%m-%d")
                except ValueError:
                    return jsonify({"error": "Format redater invalide (attendu: YYYY-MM-DD)"}), 400
            add_tag(photo_path, tag, value.strip())
        else:
            add_tag(photo_path, tag, bool(value))
        tags = read_tags(photo_path)
        return jsonify({"success": True, "filename": filename, "tag": tag, "tags": _serialize_tags(tags)})
    except Exception as e:
        logger.error("Erreur ajout tag %s: %s", filename, e)
        return jsonify({"error": f"Impossible d'écrire le tag: {e}"}), 500


@app.route("/api/photo/<path:filename>/tag/<tag_name>", methods=["DELETE"])
def api_photo_remove_tag(filename: str, tag_name: str):
    """Supprime un tag d'une photo."""
    try:
        photo_path = _safe_photo_path(filename)
    except ValueError:
        return jsonify({"error": "Chemin de photo invalide"}), 400
    if not photo_path.exists():
        return jsonify({"error": f"Photo introuvable: {filename}"}), 404

    tag_name = tag_name.strip().lower()
    try:
        remove_tag(photo_path, tag_name)
        tags = read_tags(photo_path)
        return jsonify({"success": True, "filename": filename, "tag": tag_name, "tags": _serialize_tags(tags)})
    except Exception as e:
        logger.error("Erreur suppression tag %s: %s", filename, e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/photo/<path:filename>/tags", methods=["DELETE"])
def api_photo_clear_tags(filename: str):
    """Supprime tous les tags d'une photo."""
    try:
        photo_path = _safe_photo_path(filename)
    except ValueError:
        return jsonify({"error": "Chemin de photo invalide"}), 400
    if not photo_path.exists():
        return jsonify({"error": f"Photo introuvable: {filename}"}), 404

    try:
        clear_all_tags(photo_path)
        return jsonify({"success": True, "filename": filename, "tags": {}})
    except Exception as e:
        logger.error("Erreur clear tags %s: %s", filename, e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tagged-photos")
def api_tagged_photos():
    """Liste toutes les photos qui ont des tags."""
    try:
        tagged = list_all_tags(PHOTOS_DIR)
        return jsonify(tagged)
    except Exception as e:
        logger.error("Erreur list_all_tags: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/regenerate", methods=["POST"])
def api_regenerate():
    """Lance la régénération de l'album en arrière-plan."""
    global _regenerating, _regenerate_progress
    with _regenerate_lock:
        if _regenerating:
            return jsonify({"error": "Régénération déjà en cours"}), 409
        _regenerating = True
        _regenerate_progress = "Démarrage..."

    def run_generate():
        global _regenerating, _regenerate_progress
        try:
            _set_progress("Scoring en cours...")
            cmd = [
                sys.executable,
                str(PROJECT_DIR_OBJ / "generate.py"),
                "--photos", str(PHOTOS_DIR),
                "--scoring",
            ]
            # On pourrait ajouter --html-only pour aller plus vite
            logger.info("Lancement: %s", " ".join(cmd))
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_DIR_OBJ),
            )
            output_lines = []
            for line in proc.stdout or []:
                output_lines.append(line)
                if "Scoring" in line or "dispatch" in line or "généré" in line.lower():
                    _set_progress(line.strip())
                elif len(" ".join(output_lines[-3:])) > 200:
                    _set_progress(output_lines[-1].strip())

            proc.wait()
            if proc.returncode == 0:
                _set_progress("Album régénéré avec succès !")
                # Invalider le cache des scores
                invalidate_scores_cache()
            else:
                _set_progress(f"Erreur (code {proc.returncode})")
                logger.error("Erreur generate: %s", "\n".join(output_lines[-20:]))
        except Exception as e:
            _set_progress(f"Erreur: {e}")
            logger.error("Exception dans run_generate: %s", e)
        finally:
            with _regenerate_lock:
                _regenerating = False

    def _set_progress(msg: str) -> None:
        global _regenerate_progress
        with _regenerate_lock:
            _regenerate_progress = msg

    thread = threading.Thread(target=run_generate, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Régénération lancée"})


@app.route("/api/regenerate/status")
def api_regenerate_status():
    """Retourne le statut de la régénération."""
    with _regenerate_lock:
        return jsonify({
            "running": _regenerating,
            "progress": _regenerate_progress,
        })


# ── Pages statiques (SPA) ────────────────────────────────────────────

@app.route("/")
def index():
    """Sert l'interface principale."""
    return send_from_directory(PREVIEW_STATIC_DIR, "index.html")


@app.route("/pages")
def album_pages():
    """Vue des pages maquettées avec templates."""
    return send_from_directory(PREVIEW_STATIC_DIR, "album_pages.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    """Sert les fichiers statiques (JS, CSS)."""
    return send_from_directory(PREVIEW_STATIC_DIR, filename)


# ── Point d'entrée ───────────────────────────────────────────────────

def main():
    global PHOTOS_DIR
    parser = argparse.ArgumentParser(description="Serveur de prévisualisation d'album photo")
    parser.add_argument("--photos", type=str, default="/root/mael_onedrive",
                        help="Répertoire des photos (défaut: /root/mael_onedrive)")
    parser.add_argument("--port", type=int, default=8888,
                        help="Port du serveur (défaut: 8888)")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Adresse d'écoute (défaut: 0.0.0.0)")
    parser.add_argument("--debug", action="store_true",
                        help="Mode debug Flask")
    args = parser.parse_args()

    PHOTOS_DIR = Path(args.photos).resolve()

    if not PHOTOS_DIR.is_dir():
        logger.error("Répertoire des photos introuvable: %s", PHOTOS_DIR)
        sys.exit(1)

    logger.info("📸 Serveur de prévisualisation")
    logger.info("   Photos : %s", PHOTOS_DIR)
    logger.info("   Port   : %d", args.port)
    logger.info("   URL    : http://%s:%d", args.host if args.host != "0.0.0.0" else "localhost", args.port)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
