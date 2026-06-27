#!/usr/bin/env python3
"""
db.py — Couche SQLite pour l'album photo.

Stocke les métadonnées des albums, photos, scores, palettes et
enregistrements vocaux. Base locale, zéro configuration.

Usage:
    from db import AlbumDatabase

    db = AlbumDatabase("data/albums.db")
    album = db.create_album("Noah 2025", palette=["#FF6B35", "#004E64"])
    db.add_photo(album["id"], onedrive_path="Images/Pellicule/2025/photo.jpg",
                 score=0.85, category="hero")
    photos = db.get_album_photos(album["id"])
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Schéma ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS albums (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    enfant          TEXT DEFAULT '',
    year            INTEGER,
    palette_colors  TEXT DEFAULT '[]',       -- JSON array of hex colors
    palette_name    TEXT DEFAULT 'Soleil',
    voice_narrative_path TEXT DEFAULT '',
    pdf_path        TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS album_photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id        INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    onedrive_path   TEXT NOT NULL,           -- Chemin OneDrive (ex: "Images/Pellicule/2025/photo.jpg")
    local_cache_path TEXT DEFAULT '',         -- Chemin local après téléchargement
    filename        TEXT DEFAULT '',
    filesize        INTEGER DEFAULT 0,
    width           INTEGER DEFAULT 0,
    height          INTEGER DEFAULT 0,
    score           REAL DEFAULT 0.0,        -- Score IA composite (0.0 à 1.0)
    score_details   TEXT DEFAULT '{}',       -- JSON: {"sharpness": 0.8, "smile": 0.9, ...}
    category        TEXT DEFAULT 'filler',   -- 'hero', 'duo', 'grille', 'filler'
    selected        BOOLEAN DEFAULT FALSE,
    is_video        BOOLEAN DEFAULT FALSE,
    video_duration  REAL DEFAULT 0.0,
    best_frame_path TEXT DEFAULT '',
    exif_date       TEXT DEFAULT '',
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scoring_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id        INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    status          TEXT DEFAULT 'pending',  -- 'pending', 'running', 'complete', 'failed'
    total_photos    INTEGER DEFAULT 0,
    scored_photos   INTEGER DEFAULT 0,
    config_json     TEXT DEFAULT '{}',       -- JSON: weights, thresholds
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_album_photos_album ON album_photos(album_id);
CREATE INDEX IF NOT EXISTS idx_album_photos_score ON album_photos(score DESC);
CREATE INDEX IF NOT EXISTS idx_scoring_jobs_album ON scoring_jobs(album_id);
"""


# ── AlbumDatabase ────────────────────────────────────────────────────────────

class AlbumDatabase:
    """Base de données SQLite thread-safe pour les albums photo."""

    def __init__(self, db_path: str = "data/albums.db"):
        self.db_path = str(Path(db_path).resolve())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Connexion thread-safe (une par thread)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self) -> None:
        """Crée les tables si elles n'existent pas."""
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # ── Albums ───────────────────────────────────────────────────────────────

    def create_album(
        self,
        name: str,
        enfant: str = "",
        year: Optional[int] = None,
        palette_name: str = "Soleil",
        palette_colors: Optional[List[str]] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """Crée un nouvel album et retourne ses données."""
        cur = self._conn.execute(
            """INSERT INTO albums (name, description, enfant, year, palette_name, palette_colors)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, description, enfant, year, palette_name,
             json.dumps(palette_colors or [])),
        )
        self._conn.commit()
        return self.get_album(cur.lastrowid)

    def get_album(self, album_id: int) -> Optional[Dict[str, Any]]:
        """Récupère un album par son ID."""
        row = self._conn.execute(
            "SELECT * FROM albums WHERE id = ?", (album_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_albums(self) -> List[Dict[str, Any]]:
        """Liste tous les albums, du plus récent au plus ancien."""
        rows = self._conn.execute(
            "SELECT * FROM albums ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_album(
        self,
        album_id: int,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Met à jour les champs d'un album."""
        allowed = {"name", "description", "enfant", "year",
                   "palette_name", "palette_colors", "voice_narrative_path",
                   "pdf_path"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_album(album_id)

        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [album_id]
        self._conn.execute(
            f"UPDATE albums SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()
        return self.get_album(album_id)

    def delete_album(self, album_id: int) -> bool:
        """Supprime un album et ses photos (cascade)."""
        cur = self._conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # ── Photos ───────────────────────────────────────────────────────────────

    def add_photo(
        self,
        album_id: int,
        onedrive_path: str,
        filename: str = "",
        score: float = 0.0,
        score_details: Optional[Dict[str, float]] = None,
        category: str = "filler",
        selected: bool = False,
        is_video: bool = False,
        best_frame_path: str = "",
        exif_date: str = "",
        sort_order: int = 0,
    ) -> int:
        """Ajoute une photo à un album. Retourne son ID."""
        cur = self._conn.execute(
            """INSERT INTO album_photos
               (album_id, onedrive_path, filename, score, score_details,
                category, selected, is_video, best_frame_path, exif_date, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (album_id, onedrive_path, filename, score,
             json.dumps(score_details or {}),
             category, selected, is_video, best_frame_path, exif_date, sort_order),
        )
        self._conn.commit()
        return cur.lastrowid

    def add_photos_batch(self, album_id: int, photos: List[Dict]) -> int:
        """Ajoute plusieurs photos en une transaction. Retourne le nombre ajouté."""
        data = []
        for p in photos:
            data.append((
                album_id,
                p.get("onedrive_path", ""),
                p.get("filename", ""),
                p.get("score", 0.0),
                json.dumps(p.get("score_details", {})),
                p.get("category", "filler"),
                p.get("selected", False),
                p.get("is_video", False),
                p.get("best_frame_path", ""),
                p.get("exif_date", ""),
                p.get("sort_order", 0),
            ))
        self._conn.executemany(
            """INSERT INTO album_photos
               (album_id, onedrive_path, filename, score, score_details,
                category, selected, is_video, best_frame_path, exif_date, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            data,
        )
        self._conn.commit()
        return len(data)

    def get_album_photos(
        self,
        album_id: int,
        category: Optional[str] = None,
        selected_only: bool = False,
        sort_by: str = "sort_order",
    ) -> List[Dict[str, Any]]:
        """Récupère les photos d'un album, triées."""
        valid_sort = {"sort_order", "score", "exif_date", "filename"}
        if sort_by not in valid_sort:
            sort_by = "sort_order"

        where = ["album_id = ?"]
        params: List = [album_id]

        if category:
            where.append("category = ?")
            params.append(category)
        if selected_only:
            where.append("selected = 1")

        sql = f"SELECT * FROM album_photos WHERE {' AND '.join(where)} ORDER BY {sort_by}"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_photo_score(
        self,
        photo_id: int,
        score: float,
        score_details: Optional[Dict[str, float]] = None,
        category: Optional[str] = None,
    ) -> bool:
        """Met à jour le score d'une photo."""
        updates = {"score": score}
        if score_details is not None:
            updates["score_details"] = json.dumps(score_details)
        if category is not None:
            updates["category"] = category
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [photo_id]
        cur = self._conn.execute(
            f"UPDATE album_photos SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_photo_local_cache(self, photo_id: int, local_path: str) -> bool:
        """Enregistre le chemin local après téléchargement."""
        cur = self._conn.execute(
            "UPDATE album_photos SET local_cache_path = ? WHERE id = ?",
            (local_path, photo_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_photo_selection(self, photo_id: int, selected: bool) -> bool:
        """Sélectionne ou désélectionne une photo."""
        cur = self._conn.execute(
            "UPDATE album_photos SET selected = ? WHERE id = ?",
            (selected, photo_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_photo_best_frame(self, photo_id: int, best_frame_path: str) -> bool:
        """Enregistre la meilleure frame extraite d'une vidéo."""
        cur = self._conn.execute(
            "UPDATE album_photos SET best_frame_path = ? WHERE id = ?",
            (best_frame_path, photo_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_photos(self, album_id: int, photo_ids: Optional[List[int]] = None) -> int:
        """Supprime des photos. Si photo_ids est None, supprime toutes les photos de l'album."""
        if photo_ids is not None:
            placeholders = ",".join("?" for _ in photo_ids)
            cur = self._conn.execute(
                f"DELETE FROM album_photos WHERE album_id = ? AND id IN ({placeholders})",
                [album_id] + photo_ids,
            )
        else:
            cur = self._conn.execute(
                "DELETE FROM album_photos WHERE album_id = ?", (album_id,)
            )
        self._conn.commit()
        return cur.rowcount

    # ── Scoring jobs ─────────────────────────────────────────────────────────

    def create_scoring_job(self, album_id: int, config: Optional[Dict] = None) -> int:
        """Crée un job de scoring. Retourne son ID."""
        cur = self._conn.execute(
            """INSERT INTO scoring_jobs (album_id, status, config_json)
               VALUES (?, 'pending', ?)""",
            (album_id, json.dumps(config or {})),
        )
        self._conn.commit()
        return cur.lastrowid

    def start_scoring_job(self, job_id: int, total_photos: int) -> bool:
        """Marque un job comme en cours d'exécution."""
        cur = self._conn.execute(
            """UPDATE scoring_jobs
               SET status = 'running', total_photos = ?, started_at = ?
               WHERE id = ?""",
            (total_photos, datetime.utcnow().isoformat(), job_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def complete_scoring_job(self, job_id: int, scored_photos: int) -> bool:
        """Marque un job comme terminé."""
        cur = self._conn.execute(
            """UPDATE scoring_jobs
               SET status = 'complete', scored_photos = ?, completed_at = ?
               WHERE id = ?""",
            (scored_photos, datetime.utcnow().isoformat(), job_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def fail_scoring_job(self, job_id: int) -> bool:
        """Marque un job comme échoué."""
        cur = self._conn.execute(
            "UPDATE scoring_jobs SET status = 'failed', completed_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), job_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ── Stats ────────────────────────────────────────────────────────────────

    def get_album_stats(self, album_id: int) -> Dict[str, Any]:
        """Retourne des statistiques sur un album."""
        row = self._conn.execute(
            """SELECT
                   COUNT(*) as total_photos,
                   COALESCE(SUM(CASE WHEN selected THEN 1 ELSE 0 END), 0) as selected_count,
                   AVG(score) as avg_score,
                   MAX(score) as max_score,
                   MIN(score) as min_score,
                   COALESCE(SUM(CASE WHEN is_video THEN 1 ELSE 0 END), 0) as video_count,
                   COALESCE(SUM(CASE WHEN category = 'hero' THEN 1 ELSE 0 END), 0) as hero_count,
                   COALESCE(SUM(CASE WHEN category = 'duo' THEN 1 ELSE 0 END), 0) as duo_count,
                   COALESCE(SUM(CASE WHEN category = 'grille' THEN 1 ELSE 0 END), 0) as grille_count
               FROM album_photos WHERE album_id = ?""",
            (album_id,),
        ).fetchone()
        result = dict(row) if row else {}
        # Arrondir les flottants
        for k in ("avg_score", "max_score", "min_score"):
            if k in result and result[k] is not None:
                result[k] = round(result[k], 4)
        return result

    def close(self) -> None:
        """Ferme la connexion."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
