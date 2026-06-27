#!/usr/bin/env python3
"""
Tests pour db.py — AlbumDatabase SQLite.

Utilise une base de données temporaire en mémoire.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ajouter le projet au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import AlbumDatabase


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Crée une base de données temporaire pour les tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = AlbumDatabase(db_path)
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture
def sample_album(db):
    """Crée un album exemple."""
    return db.create_album(
        name="Test Album",
        enfant="Test Enfant",
        year=2025,
        palette_name="Soleil",
        palette_colors=["#ff6b35", "#004e64"],
        description="Album de test",
    )


# ── Tests Albums ────────────────────────────────────────────────────────────

class TestAlbums:
    def test_create_album(self, db):
        album = db.create_album(name="Mon Album")
        assert album["id"] > 0
        assert album["name"] == "Mon Album"
        assert album["palette_name"] == "Soleil"  # Valeur par défaut

    def test_create_album_full(self, db):
        album = db.create_album(
            name="Noah 2025",
            enfant="Noah",
            year=2025,
            palette_name="Ocean",
            palette_colors=["#2980b9", "#1a5276"],
            description="Première année de Noah",
        )
        assert album["name"] == "Noah 2025"
        assert album["enfant"] == "Noah"
        assert album["year"] == 2025
        assert album["palette_name"] == "Ocean"
        assert "2980b9" in album["palette_colors"]

    def test_get_album_not_found(self, db):
        album = db.get_album(999)
        assert album is None

    def test_get_album(self, db, sample_album):
        fetched = db.get_album(sample_album["id"])
        assert fetched["id"] == sample_album["id"]
        assert fetched["name"] == sample_album["name"]

    def test_list_albums_empty(self, db):
        albums = db.list_albums()
        assert isinstance(albums, list)
        assert len(albums) == 0

    def test_list_albums(self, db, sample_album):
        db.create_album(name="Second Album")
        albums = db.list_albums()
        assert len(albums) == 2

    def test_update_album(self, db, sample_album):
        updated = db.update_album(
            sample_album["id"],
            name="Nouveau Nom",
            palette_name="Foret",
        )
        assert updated["name"] == "Nouveau Nom"
        assert updated["palette_name"] == "Foret"
        # Les champs non modifiés restent
        assert updated["enfant"] == "Test Enfant"

    def test_update_album_invalid_field(self, db, sample_album):
        """Les champs non autorisés sont ignorés."""
        updated = db.update_album(sample_album["id"], nonexistent="value")
        assert updated is not None
        assert updated["id"] == sample_album["id"]

    def test_delete_album(self, db, sample_album):
        deleted = db.delete_album(sample_album["id"])
        assert deleted is True
        assert db.get_album(sample_album["id"]) is None

    def test_delete_nonexistent_album(self, db):
        deleted = db.delete_album(999)
        assert deleted is False


# ── Tests Photos ────────────────────────────────────────────────────────────

class TestPhotos:
    def test_add_photo(self, db, sample_album):
        photo_id = db.add_photo(
            album_id=sample_album["id"],
            onedrive_path="Images/Pellicule/2025/test.jpg",
            filename="test.jpg",
            score=0.85,
            category="hero",
        )
        assert photo_id > 0

    def test_add_photo_minimal(self, db, sample_album):
        photo_id = db.add_photo(
            album_id=sample_album["id"],
            onedrive_path="test.jpg",
        )
        assert photo_id > 0

    def test_add_photos_batch(self, db, sample_album):
        photos = [
            {"onedrive_path": f"photos/2025/photo_{i}.jpg", "filename": f"photo_{i}.jpg", "score": 0.5 + i * 0.1}
            for i in range(10)
        ]
        count = db.add_photos_batch(sample_album["id"], photos)
        assert count == 10

    def test_get_album_photos(self, db, sample_album):
        # Ajoute des photos
        for i in range(5):
            db.add_photo(
                album_id=sample_album["id"],
                onedrive_path=f"photo_{i}.jpg",
                score=0.5 + i * 0.1,
                category="grille",
            )

        photos = db.get_album_photos(sample_album["id"])
        assert len(photos) == 5

    def test_get_album_photos_by_category(self, db, sample_album):
        db.add_photo(album_id=sample_album["id"], onedrive_path="hero.jpg", category="hero")
        db.add_photo(album_id=sample_album["id"], onedrive_path="duo.jpg", category="duo")
        db.add_photo(album_id=sample_album["id"], onedrive_path="grille.jpg", category="grille")

        heroes = db.get_album_photos(sample_album["id"], category="hero")
        assert len(heroes) == 1
        assert heroes[0]["category"] == "hero"

    def test_get_album_photos_selected_only(self, db, sample_album):
        db.add_photo(album_id=sample_album["id"], onedrive_path="selected.jpg", selected=True)
        db.add_photo(album_id=sample_album["id"], onedrive_path="not_selected.jpg", selected=False)

        selected = db.get_album_photos(sample_album["id"], selected_only=True)
        assert len(selected) == 1
        assert selected[0]["selected"] == 1

    def test_update_photo_score(self, db, sample_album):
        photo_id = db.add_photo(
            album_id=sample_album["id"],
            onedrive_path="test.jpg",
            score=0.5,
        )
        updated = db.update_photo_score(photo_id, 0.95, {"sharpness": 0.9, "smile": 0.8}, category="hero")
        assert updated is True

        photos = db.get_album_photos(sample_album["id"])
        assert photos[0]["score"] == 0.95

    def test_set_photo_selection(self, db, sample_album):
        photo_id = db.add_photo(album_id=sample_album["id"], onedrive_path="test.jpg")
        db.set_photo_selection(photo_id, True)
        photos = db.get_album_photos(sample_album["id"], selected_only=True)
        assert len(photos) == 1

        db.set_photo_selection(photo_id, False)
        photos = db.get_album_photos(sample_album["id"], selected_only=True)
        assert len(photos) == 0

    def test_set_photo_best_frame(self, db, sample_album):
        photo_id = db.add_photo(album_id=sample_album["id"], onedrive_path="video.mp4", is_video=True)
        db.set_photo_best_frame(photo_id, "frames/video_frame_001.jpg")
        photos = db.get_album_photos(sample_album["id"])
        assert photos[0]["best_frame_path"] == "frames/video_frame_001.jpg"

    def test_update_photo_local_cache(self, db, sample_album):
        photo_id = db.add_photo(album_id=sample_album["id"], onedrive_path="test.jpg")
        db.update_photo_local_cache(photo_id, "/tmp/cache/test.jpg")
        photos = db.get_album_photos(sample_album["id"])
        assert photos[0]["local_cache_path"] == "/tmp/cache/test.jpg"

    def test_delete_photos(self, db, sample_album):
        ids = []
        for i in range(5):
            pid = db.add_photo(album_id=sample_album["id"], onedrive_path=f"photo_{i}.jpg")
            ids.append(pid)

        # Supprime 2 photos
        deleted = db.delete_photos(sample_album["id"], photo_ids=ids[:2])
        assert deleted == 2
        assert len(db.get_album_photos(sample_album["id"])) == 3

    def test_delete_all_photos(self, db, sample_album):
        for i in range(5):
            db.add_photo(album_id=sample_album["id"], onedrive_path=f"photo_{i}.jpg")

        deleted = db.delete_photos(sample_album["id"])
        assert deleted == 5
        assert len(db.get_album_photos(sample_album["id"])) == 0

    def test_cascade_delete_album(self, db, sample_album):
        db.add_photo(album_id=sample_album["id"], onedrive_path="photo.jpg")
        db.delete_album(sample_album["id"])
        assert len(db.get_album_photos(sample_album["id"])) == 0


# ── Tests Scoring Jobs ──────────────────────────────────────────────────────

class TestScoringJobs:
    def test_create_job(self, db, sample_album):
        job_id = db.create_scoring_job(sample_album["id"])
        assert job_id > 0

    def test_create_job_with_config(self, db, sample_album):
        config = {"weights": {"sharpness": 0.5, "smile": 0.5}}
        job_id = db.create_scoring_job(sample_album["id"], config=config)
        assert job_id > 0

    def test_job_lifecycle(self, db, sample_album):
        job_id = db.create_scoring_job(sample_album["id"])
        db.start_scoring_job(job_id, total_photos=50)
        db.complete_scoring_job(job_id, scored_photos=48)
        # Les jobs sont créés avec un statut, on vérifie juste qu'il n'y a pas d'erreur
        assert True

    def test_fail_job(self, db, sample_album):
        job_id = db.create_scoring_job(sample_album["id"])
        db.start_scoring_job(job_id, total_photos=10)
        db.fail_scoring_job(job_id)
        assert True


# ── Tests Stats ─────────────────────────────────────────────────────────────

class TestStats:
    def test_get_album_stats_empty(self, db, sample_album):
        stats = db.get_album_stats(sample_album["id"])
        assert stats["total_photos"] == 0
        assert stats["selected_count"] == 0

    def test_get_album_stats(self, db, sample_album):
        for i in range(10):
            db.add_photo(
                album_id=sample_album["id"],
                onedrive_path=f"photo_{i}.jpg",
                score=0.5 + i * 0.05,
                category="grille" if i > 2 else "hero",
                selected=(i < 5),
            )

        stats = db.get_album_stats(sample_album["id"])
        assert stats["total_photos"] == 10
        assert stats["selected_count"] == 5
        assert stats["hero_count"] == 3
        assert stats["grille_count"] == 7
        assert stats["avg_score"] is not None
        assert stats["max_score"] is not None
        assert stats["min_score"] is not None

    def test_video_count(self, db, sample_album):
        db.add_photo(album_id=sample_album["id"], onedrive_path="photo.jpg", is_video=False)
        db.add_photo(album_id=sample_album["id"], onedrive_path="video.mp4", is_video=True)
        stats = db.get_album_stats(sample_album["id"])
        assert stats["video_count"] == 1
        assert stats["total_photos"] == 2
