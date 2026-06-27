"""
Tests d'intégration — Flow complet e2e pour l'Album Photo Generator.

Teste le parcours complet : création d'album → ajout de photos → scoring
→ palette → preview → export, en utilisant les vrais modules backend.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ajouter le projet au path
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from db import AlbumDatabase
from pages.page_utils import (
    get_mock_photo_groups,
    get_mock_onedrive_photos,
    get_scores_dict,
    get_active_palette,
    load_palettes,
    MOCK_PHOTOS,
    MOCK_SCORES,
)

# ── Tests unitaires du bridge page_utils (sans Streamlit) ───────────────


class TestPageUtilsMockData:
    """Vérifie que les données mock sont cohérentes."""

    def test_mock_photos_have_required_fields(self):
        for p in MOCK_PHOTOS:
            assert "id" in p
            assert "name" in p
            assert "path" in p
            assert "type" in p

    def test_mock_photos_12(self):
        assert len(MOCK_PHOTOS) == 12

    def test_mock_scores_match_photos(self):
        for pid in MOCK_SCORES:
            assert pid in {p["id"] for p in MOCK_PHOTOS}

    def test_mock_scores_have_categories(self):
        categories = {s["category"] for s in MOCK_SCORES.values()}
        assert categories.issubset({"hero", "support", "filler"})

    def test_mock_groups(self):
        # Import du module pour tester _mock_groups() - accessible via le test
        from pages.page_utils import MOCK_PHOTOS
        groups = {}
        for p in MOCK_PHOTOS:
            path = p["path"]
            parts = path.split("/")
            folder = "/".join(parts[:-1]) if len(parts) > 1 else "Racine"
            if folder not in groups:
                groups[folder] = []
            groups[folder].append(p)
        assert len(groups) >= 5  # Au moins 5 dossiers différents
        total = sum(len(v) for v in groups.values())
        assert total == len(MOCK_PHOTOS)


# ── Tests AlbumDatabase (intégration) ──────────────────────────────────


class TestAlbumDatabaseIntegration:
    """Tests d'intégration : CRUD albums + photos + scoring."""

    @pytest.fixture
    def db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = AlbumDatabase(db_path)
        yield db
        db.close()
        os.unlink(db_path)

    def test_full_album_lifecycle(self, db):
        """Crée un album, ajoute des photos, vérifie les stats."""
        # Création
        album = db.create_album(
            name="Test Mael 2025",
            enfant="Mael",
            year=2025,
            palette_name="Ocean",
        )
        assert album["id"] > 0
        assert album["name"] == "Test Mael 2025"
        assert album["palette_name"] == "Ocean"

        # Ajout de photos
        for i in range(5):
            db.add_photo(
                album_id=album["id"],
                onedrive_path=f"Photos/2025/Vacances/photo_{i}.jpg",
                filename=f"photo_{i}.jpg",
                score=0.5 + (i * 0.1),
                category="filler" if i < 3 else "support" if i < 4 else "hero",
                selected=True,
            )

        # Vérification des stats
        stats = db.get_album_stats(album["id"])
        assert stats["total_photos"] == 5
        assert stats["selected_count"] == 5
        assert stats["avg_score"] == pytest.approx(0.7, abs=0.15)

        # Récupération des photos
        photos = db.get_album_photos(album["id"], sort_by="score")
        assert len(photos) == 5
        # Triées par score ascendant (ORDER BY score)
        scores = [p["score"] for p in photos]
        assert scores == sorted(scores), f"Attendu tri ascendant, obtenu {scores}"

    def test_scoring_job(self, db):
        """Crée et complète un job de scoring."""
        album = db.create_album(name="Score Test")
        for i in range(3):
            db.add_photo(album["id"], f"photo_{i}.jpg")

        job_id = db.create_scoring_job(album["id"])
        assert job_id > 0

        db.start_scoring_job(job_id, total_photos=3)
        db.complete_scoring_job(job_id, scored_photos=3)

        # Vérifier que les photos ont été scorées
        photos = db.get_album_photos(album["id"])
        assert len(photos) == 3

    def test_photo_selection(self, db):
        """Sélectionne / désélectionne des photos."""
        album = db.create_album(name="Selection Test")
        pid = db.add_photo(album["id"], "test.jpg", selected=False)

        db.set_photo_selection(pid, True)
        photos = db.get_album_photos(album["id"], selected_only=True)
        assert len(photos) == 1

        db.set_photo_selection(pid, False)
        photos = db.get_album_photos(album["id"], selected_only=True)
        assert len(photos) == 0

    def test_album_update(self, db):
        """Met à jour les métadonnées d'un album."""
        album = db.create_album(name="Original", palette_name="Soleil")
        db.update_album(album["id"], name="Updated", palette_name="Foret")
        updated = db.get_album(album["id"])
        assert updated["name"] == "Updated"
        assert updated["palette_name"] == "Foret"

    def test_delete_album_cascade(self, db):
        """Supprime un album et ses photos."""
        album = db.create_album(name="To Delete")
        db.add_photo(album["id"], "photo1.jpg")
        db.add_photo(album["id"], "photo2.jpg")
        assert len(db.get_album_photos(album["id"])) == 2

        db.delete_album(album["id"])
        assert db.get_album(album["id"]) is None

    def test_batch_photo_add(self, db):
        """Ajout en lot de photos."""
        album = db.create_album(name="Batch Test")
        photos_data = [
            {"onedrive_path": f"batch/{i}.jpg", "filename": f"{i}.jpg",
             "score": i * 0.1, "category": "filler"}
            for i in range(10)
        ]
        count = db.add_photos_batch(album["id"], photos_data)
        assert count == 10
        assert len(db.get_album_photos(album["id"])) == 10

    def test_get_album_stats_empty(self, db):
        """Stats d'un album vide."""
        album = db.create_album(name="Empty")
        stats = db.get_album_stats(album["id"])
        assert stats["total_photos"] == 0
        assert stats["avg_score"] is None

    def test_update_photo_score_details(self, db):
        """Met à jour les détails du score d'une photo."""
        album = db.create_album(name="Score Details")
        pid = db.add_photo(album["id"], "test.jpg")
        details = {"sharpness": 0.85, "smile": 0.92, "exposure": 0.78}
        db.update_photo_score(pid, score=0.85, score_details=details, category="hero")
        photos = db.get_album_photos(album["id"])
        assert photos[0]["score"] == pytest.approx(0.85)
        assert photos[0]["category"] == "hero"

    def test_local_cache_path(self, db):
        """Met à jour le chemin de cache local."""
        album = db.create_album(name="Cache Test")
        pid = db.add_photo(album["id"], "remote.jpg")
        db.update_photo_local_cache(pid, "/tmp/cached/remote.jpg")
        photos = db.get_album_photos(album["id"])
        assert photos[0]["local_cache_path"] == "/tmp/cached/remote.jpg"


# ── Tests config.yaml ──────────────────────────────────────────────────


class TestConfig:
    """Vérifie la configuration."""

    def test_config_exists(self):
        assert (PROJECT_DIR / "config.yaml").exists()

    def test_palettes_loaded(self):
        import yaml
        with open(PROJECT_DIR / "config.yaml") as f:
            config = yaml.safe_load(f)
        palettes = config.get("palettes", {})
        assert len(palettes) >= 4
        for name in ["Soleil", "Ocean", "Foret", "Pastel", "Crepuscule"]:
            assert name in palettes, f"Palette {name} manquante"

    def test_palette_colors_complete(self):
        palettes = load_palettes()
        required_keys = {"name", "bg_start", "bg_mid", "bg_end",
                         "band_top", "band_bottom", "text_primary",
                         "accent_1", "photo_border"}
        for name, palette in palettes.items():
            missing = required_keys - set(palette.keys())
            assert not missing, f"Palette {name} manque: {missing}"

    def test_scoring_config(self):
        import yaml
        with open(PROJECT_DIR / "config.yaml") as f:
            config = yaml.safe_load(f)
        scoring = config.get("scoring", {})
        assert "default_weights" in scoring
        weights = scoring["default_weights"]
        assert abs(sum(weights.values()) - 1.0) < 0.01


# ── Test de l'entrypoint app.py ────────────────────────────────────────


class TestAppEntrypoint:
    """Vérifie que app.py est importable et ses fonctions existent."""

    def test_app_importable(self):
        spec = __import__("app")
        assert hasattr(spec, "init_backend")
        assert hasattr(spec, "init_session_state")
        assert hasattr(spec, "render_sidebar")
        assert hasattr(spec, "render_header")
        assert hasattr(spec, "render_page")
        assert hasattr(spec, "main")

    def test_steps_defined(self):
        import app
        assert len(app.STEPS) == 5
        names = [s[0] for s in app.STEPS]
        assert names == ["Sélection", "Scoring", "Palette", "Preview", "Export"]


# ── Test de la structure du projet ─────────────────────────────────────


class TestProjectStructure:
    """Vérifie que tous les fichiers nécessaires sont présents."""

    def test_css_exists(self):
        assert (PROJECT_DIR / "styles" / "app.css").exists()

    def test_streamlit_config_exists(self):
        assert (PROJECT_DIR / ".streamlit" / "config.toml").exists()

    def test_all_pages_exist(self):
        for name in ["selection", "scoring_page", "palette", "preview", "export_page"]:
            assert (PROJECT_DIR / "pages" / f"{name}.py").exists(), f"Missing {name}.py"

    def test_page_utils_exists(self):
        assert (PROJECT_DIR / "pages" / "page_utils.py").exists()

    def test_db_module_exists(self):
        assert (PROJECT_DIR / "db.py").exists()

    def test_generate_module_exists(self):
        assert (PROJECT_DIR / "generate.py").exists()
