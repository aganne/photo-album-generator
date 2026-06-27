"""
page_utils.py — Bridge entre les pages Streamlit (Dionysos) et le backend (Hephaistos).

Fournit aux pages les mêmes fonctions que l'ancien db.py mock, mais basées
sur AlbumDatabase réelle + config.yaml. Les pages importent ce module
au lieu de from db import get_mock_onedrive_photos, MOCK_SCORES, etc.
"""

import json
import streamlit as st
from pathlib import Path


def _get_backend():
    """Retourne le backend depuis session_state (initialisé par app.py)."""
    return st.session_state.get("backend")


def _get_db():
    """Retourne l'instance AlbumDatabase."""
    backend = _get_backend()
    if backend:
        return backend["db"]
    return None


def _get_config():
    """Retourne la config YAML."""
    backend = _get_backend()
    if backend:
        return backend.get("config", {})
    return {}


def get_mock_photo_groups() -> dict:
    """Retourne les groupes de photos mock pour la sélection OneDrive.
    Lit les photos de l'album courant dans la DB avec mock si pas d'album.
    """
    backend = _get_backend()
    db = _get_db()
    if not db:
        return {}

    album_id = st.session_state.get("album_id")
    if album_id:
        photos = db.get_album_photos(album_id, sort_by="sort_order")
    else:
        photos = []

    # Si pas d'album ou pas de photos, retourne les mock data intégrées
    if not photos:
        return _mock_groups()

    # Grouper par dossier OneDrive
    groups = {}
    for p in photos:
        path = p.get("onedrive_path", "")
        parts = path.split("/")
        folder = "/".join(parts[:-1]) if len(parts) > 1 else "Racine"
        if folder not in groups:
            groups[folder] = []
        groups[folder].append({
            "id": str(p["id"]),
            "name": p.get("filename", path.split("/")[-1]),
            "path": path,
            "date": p.get("exif_date", ""),
            "size_kb": p.get("filesize", 0) // 1024,
            "type": "video" if p.get("is_video") else "photo",
            "score": p.get("score", 0.0),
            "category": p.get("category", "filler"),
            "selected": p.get("selected", False),
        })
    return groups


def get_mock_onedrive_photos() -> list:
    """Retourne toutes les photos mock / DB de l'album courant."""
    db = _get_db()
    if not db:
        return _mock_photos_list()

    album_id = st.session_state.get("album_id")
    if album_id:
        photos = db.get_album_photos(album_id, sort_by="sort_order")
        if photos:
            return [_photo_to_dict(p) for p in photos]

    return _mock_photos_list()


def _photo_to_dict(p: dict) -> dict:
    """Convertit une ligne AlbumDatabase en dict compatible pages."""
    return {
        "id": str(p["id"]),
        "name": p.get("filename", p.get("onedrive_path", "").split("/")[-1]),
        "path": p.get("onedrive_path", ""),
        "date": p.get("exif_date", ""),
        "size_kb": p.get("filesize", 0) // 1024,
        "type": "video" if p.get("is_video") else "photo",
        "score": p.get("score", 0.0),
        "category": p.get("category", "filler"),
    }


def get_scores_dict() -> dict:
    """Retourne un dict {photo_id: score_info} compatible MOCK_SCORES."""
    db = _get_db()
    result = {}
    if not db:
        return result

    album_id = st.session_state.get("album_id")
    if album_id:
        photos = db.get_album_photos(album_id)
        for p in photos:
            details = {}
            if p.get("score_details"):
                try:
                    details = json.loads(p["score_details"])
                except (json.JSONDecodeError, TypeError):
                    details = {}
            result[str(p["id"])] = {
                "score": p.get("score", 0.0),
                "category": p.get("category", "filler"),
                "sharpness": details.get("sharpness", 0.0),
                "exposure": details.get("exposure", 0.0),
                "contrast": details.get("contrast", 0.0),
                "smile": details.get("smile", 0.0),
                "faces": details.get("faces_count", 0),
                "noise": details.get("noise", 0.0),
            }
    return result


# ── Palettes ────────────────────────────────────────────────────────────

def load_palettes() -> dict:
    """Charge toutes les palettes depuis la config."""
    config = _get_config()
    palettes = config.get("palettes", {})
    if not palettes:
        # Fallback: les palettes hardcodées
        from pages.palette import PALETTES as FALLBACK
        return FALLBACK
    return palettes


def get_active_palette() -> dict:
    """Retourne la palette active depuis la session/DB."""
    palette_name = st.session_state.get("current_palette", "Soleil")
    palettes = load_palettes()
    return palettes.get(palette_name, next(iter(palettes.values())))


def save_palette(palette_name: str, colors: dict) -> bool:
    """Sauvegarde les couleurs de palette dans la DB de l'album courant."""
    db = _get_db()
    album_id = st.session_state.get("album_id")
    if db and album_id:
        palette_colors = list(colors.values()) if isinstance(colors, dict) else colors
        db.update_album(album_id, palette_name=palette_name,
                        palette_colors=palette_colors)
        return True
    return False


# ── Mock data (fallback si pas de DB) ──────────────────────────────────

MOCK_PHOTOS = [
    {"id": "mock_001", "name": "Vacances à la plage.jpg", "path": "OneDrive/Photos/2024/Ete/plage.jpg", "date": "2024-07-15", "size_kb": 4200, "type": "photo", "score": 0.87, "category": "hero"},
    {"id": "mock_002", "name": "Anniversaire Mael.jpg", "path": "OneDrive/Photos/2024/Anniversaire/mael.jpg", "date": "2024-09-22", "size_kb": 3800, "type": "photo", "score": 0.92, "category": "hero"},
    {"id": "mock_003", "name": "Randonnée montagne.jpg", "path": "OneDrive/Photos/2024/Ete/montagne.jpg", "date": "2024-08-10", "size_kb": 5100, "type": "photo", "score": 0.76, "category": "support"},
    {"id": "mock_004", "name": "Premiers pas.jpg", "path": "OneDrive/Photos/2024/Printemps/premiers_pas.jpg", "date": "2024-03-18", "size_kb": 3400, "type": "photo", "score": 0.88, "category": "hero"},
    {"id": "mock_005", "name": "Noël en famille.jpg", "path": "OneDrive/Photos/2024/Noel/noel.jpg", "date": "2024-12-25", "size_kb": 4600, "type": "photo", "score": 0.74, "category": "support"},
    {"id": "mock_006", "name": "Jardin au printemps.jpg", "path": "OneDrive/Photos/2024/Printemps/jardin.jpg", "date": "2024-04-05", "size_kb": 2900, "type": "photo", "score": 0.65, "category": "filler"},
    {"id": "mock_007", "name": "Sortie à la ferme.jpg", "path": "OneDrive/Photos/2024/Ete/ferme.jpg", "date": "2024-07-28", "size_kb": 4100, "type": "photo", "score": 0.80, "category": "support"},
    {"id": "mock_008", "name": "Cours de dessin.jpg", "path": "OneDrive/Photos/2024/Automne/dessin.jpg", "date": "2024-10-12", "size_kb": 3200, "type": "photo", "score": 0.62, "category": "filler"},
    {"id": "mock_009", "name": "Match de foot.jpg", "path": "OneDrive/Photos/2024/Automne/foot.jpg", "date": "2024-11-02", "size_kb": 5500, "type": "photo", "score": 0.55, "category": "filler"},
    {"id": "mock_010", "name": "Sous la neige.jpg", "path": "OneDrive/Photos/2025/Hiver/neige.jpg", "date": "2025-01-15", "size_kb": 3900, "type": "photo", "score": 0.83, "category": "hero"},
    {"id": "mock_011", "name": "Vidéo anniversaire.mp4", "path": "OneDrive/Videos/2024/anniversaire.mp4", "date": "2024-09-22", "size_kb": 45000, "type": "video", "score": 0.70, "category": "support"},
    {"id": "mock_012", "name": "Vidéo premiers pas.mp4", "path": "OneDrive/Videos/2024/premiers_pas.mp4", "date": "2024-03-18", "size_kb": 32000, "type": "video", "score": 0.85, "category": "hero"},
]

MOCK_SCORES = {
    p["id"]: {"score": p["score"], "category": p["category"],
              "sharpness": 0.75, "exposure": 0.80, "contrast": 0.72,
              "smile": 0.85, "faces": 3, "noise": 0.12}
    for p in MOCK_PHOTOS
}


def _mock_groups() -> dict:
    """Génère les groupes mock."""
    groups = {}
    for p in MOCK_PHOTOS:
        path = p["path"]
        parts = path.split("/")
        folder = "/".join(parts[:-1]) if len(parts) > 1 else "Racine"
        if folder not in groups:
            groups[folder] = []
        groups[folder].append(p)
    return groups


def _mock_photos_list() -> list:
    return MOCK_PHOTOS
