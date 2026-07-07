"""Tests unitaires pour tag_manager.py — lecture/écriture EXIF UserComment."""

from __future__ import annotations

from pathlib import Path

import piexif
import pytest
from PIL import Image

from album_generator.tag_manager import (
    add_tag,
    clear_all_tags,
    list_all_tags,
    read_tags,
    remove_tag,
    write_tags,
)

# ── Helper : génération d'un JPEG minimal valide ─────────────────────


def _make_minimal_jpeg(dest: Path, existing_comment: str = "") -> None:
    """Crée un vrai fichier JPEG 2x2 pixels via Pillow.

    Optionnellement écrit un UserComment EXIF existant pour tester le merge.
    """
    img = Image.new("RGB", (2, 2), color=(128, 128, 128))
    img.save(str(dest), "JPEG", quality=85)

    # Si un commentaire existant est demandé, l'écrire via piexif
    if existing_comment:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = existing_comment.encode("utf-8")
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(dest))


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def tmp_photo(tmp_path: Path) -> Path:
    """Crée une photo JPEG minimal valide dans un dossier temporaire."""
    photo = tmp_path / "test_photo.JPG"
    _make_minimal_jpeg(photo)
    return photo


@pytest.fixture
def tmp_jpeg_dir(tmp_path: Path) -> Path:
    """Crée un dossier avec plusieurs photos pour tester list_all_tags."""
    for name in ["photo_a.JPG", "photo_b.JPG", "photo_c.JPG"]:
        p = tmp_path / name
        _make_minimal_jpeg(p)
    return tmp_path


# ── Tests d'écriture / lecture basique ───────────────────────────────


class TestWriteReadTags:
    """Cycle écriture → ré-lecture des tags."""

    def test_write_then_read(self, tmp_photo: Path):
        """Écrire des tags puis les relire."""
        tags = {"hero": True, "favori": True, "texte": "Premier bain"}
        write_tags(tmp_photo, tags)
        assert read_tags(tmp_photo) == tags

    def test_empty_tags_when_none(self, tmp_photo: Path):
        """Pas de tags → dict vide."""
        assert read_tags(tmp_photo) == {}

    def test_write_empty_dict(self, tmp_photo: Path):
        """Écrire un dict vide efface les tags."""
        write_tags(tmp_photo, {"hero": True})
        write_tags(tmp_photo, {})
        assert read_tags(tmp_photo) == {}

    def test_override_tags(self, tmp_photo: Path):
        """Ré-écrire écrase les anciens tags."""
        write_tags(tmp_photo, {"hero": True, "favori": True})
        write_tags(tmp_photo, {"redater": "2012-06-15"})
        tags = read_tags(tmp_photo)
        assert "hero" not in tags
        assert "favori" not in tags
        assert tags.get("redater") == "2012-06-15"

    def test_bool_false(self, tmp_photo: Path):
        """Tag booléen False."""
        write_tags(tmp_photo, {"favori": False})
        tags = read_tags(tmp_photo)
        assert tags.get("favori") is False

    def test_bool_false_string(self, tmp_photo: Path):
        """Tag booléen avec string 'false'."""
        write_tags(tmp_photo, {"favori": "False"})
        tags = read_tags(tmp_photo)
        assert tags.get("favori") is False

    def test_all_tags_types(self, tmp_photo: Path):
        """Tous les types de tags supportés."""
        tags = {
            "supprimer": True,
            "redater": "2012-06-15",
            "hero": True,
            "favori": False,
            "texte": "Premier bain à la mer",
        }
        write_tags(tmp_photo, tags)
        assert read_tags(tmp_photo) == tags


# ── Tests add_tag / remove_tag ───────────────────────────────────────


class TestAddRemoveTags:
    """Ajout et suppression de tags individuels."""

    def test_add_tag(self, tmp_photo: Path):
        """Ajouter un tag."""
        add_tag(tmp_photo, "hero")
        assert read_tags(tmp_photo) == {"hero": True}

    def test_add_second_tag(self, tmp_photo: Path):
        """Ajouter un deuxième tag sans perdre le premier."""
        add_tag(tmp_photo, "hero")
        add_tag(tmp_photo, "favori")
        tags = read_tags(tmp_photo)
        assert tags == {"hero": True, "favori": True}

    def test_add_tag_with_value(self, tmp_photo: Path):
        """Ajouter un tag avec valeur spécifique."""
        add_tag(tmp_photo, "redater", "2012-06-15")
        assert read_tags(tmp_photo) == {"redater": "2012-06-15"}

    def test_remove_tag(self, tmp_photo: Path):
        """Supprimer un tag existant."""
        write_tags(tmp_photo, {"hero": True, "favori": True})
        remove_tag(tmp_photo, "hero")
        assert read_tags(tmp_photo) == {"favori": True}

    def test_remove_missing_tag(self, tmp_photo: Path):
        """Supprimer un tag absent ne fait rien."""
        write_tags(tmp_photo, {"hero": True})
        remove_tag(tmp_photo, "inexistant")  # Ne doit pas lever
        assert read_tags(tmp_photo) == {"hero": True}

    def test_clear_all_tags(self, tmp_photo: Path):
        """Effacer tous les tags."""
        write_tags(tmp_photo, {"hero": True, "favori": True})
        clear_all_tags(tmp_photo)
        assert read_tags(tmp_photo) == {}

    def test_clear_no_tags(self, tmp_photo: Path):
        """clear_all_tags sur photo sans tags ne fait rien."""
        clear_all_tags(tmp_photo)
        assert read_tags(tmp_photo) == {}


# ── Tests de merge avec UserComment existant ─────────────────────────


class TestMergeExistingComment:
    """Préserver les contenus existants du UserComment."""

    def test_preserve_non_album_lines(self, tmp_path: Path):
        """Préserver les lignes non-album_tags dans UserComment."""
        existing = "Mon appareil: Canon EOS\nRéglages: f/2.8 1/250"
        photo = tmp_path / "merged.JPG"
        _make_minimal_jpeg(photo, existing_comment=existing)

        write_tags(photo, {"hero": True})
        tags = read_tags(photo)
        assert tags == {"hero": True}

        # Vérifier que les lignes existantes sont encore là dans le UserComment brut
        exif_dict = piexif.load(str(photo))
        raw_bytes = exif_dict["Exif"][piexif.ExifIFD.UserComment]
        raw_str = raw_bytes.decode("utf-8")
        assert "Mon appareil" in raw_str
        assert "Réglages" in raw_str
        assert "album_tags:" in raw_str

    def test_merge_with_existing_album_tags(self, tmp_path: Path):
        """Ajouter un tag quand un UserComment a déjà album_tags."""
        existing = "Un commentaire\nalbum_tags: favori"
        photo = tmp_path / "existing_tags.JPG"
        _make_minimal_jpeg(photo, existing_comment=existing)

        add_tag(photo, "hero")
        tags = read_tags(photo)
        assert tags == {"favori": True, "hero": True}

    def test_multiple_album_tags_lines(self, tmp_path: Path):
        """Gérer plusieurs lignes album_tags (dédoublonnage)."""
        existing = "album_tags: hero\nalbum_tags: favori"
        photo = tmp_path / "dup.JPG"
        _make_minimal_jpeg(photo, existing_comment=existing)

        write_tags(photo, {"hero": True})
        tags = read_tags(photo)
        assert tags == {"hero": True}
        # Vérifier qu'il n'y a qu'une seule ligne album_tags
        exif_dict = piexif.load(str(photo))
        raw_str = exif_dict["Exif"][piexif.ExifIFD.UserComment].decode("utf-8")
        assert raw_str.count("album_tags:") == 1

    def test_clear_preserves_other_lines(self, tmp_path: Path):
        """clear_all_tags préserve les autres lignes."""
        existing = "Info: prise le 15 juin 2012"
        photo = tmp_path / "preserve.JPG"
        _make_minimal_jpeg(photo, existing_comment=existing)

        write_tags(photo, {"hero": True})
        clear_all_tags(photo)
        assert read_tags(photo) == {}

        # Les autres lignes préservées
        exif_dict = piexif.load(str(photo))
        raw_str = exif_dict["Exif"][piexif.ExifIFD.UserComment].decode("utf-8")
        assert "Info:" in raw_str
        assert "album_tags:" not in raw_str


# ── Test list_all_tags ───────────────────────────────────────────────


class TestListAllTags:
    """list_all_tags — scanne un dossier et retourne les photos taggées."""

    def test_list_multiple_photos(self, tmp_jpeg_dir: Path):
        """Photos avec/sans tags."""
        # Tagger 2 photos sur 3
        write_tags(tmp_jpeg_dir / "photo_a.JPG", {"hero": True})
        write_tags(tmp_jpeg_dir / "photo_c.JPG", {"favori": True})

        result = list_all_tags(tmp_jpeg_dir)
        assert "photo_a.JPG" in result
        assert "photo_c.JPG" in result
        assert "photo_b.JPG" not in result  # pas de tags
        assert result["photo_a.JPG"] == {"hero": True}
        assert result["photo_c.JPG"] == {"favori": True}

    def test_list_empty_dir(self, tmp_path: Path):
        """Dossier vide → dict vide."""
        result = list_all_tags(tmp_path)
        assert result == {}

    def test_list_missing_dir(self):
        """Dossier inexistant → dict vide."""
        result = list_all_tags(Path("/tmp/does_not_exist_xyz"))
        assert result == {}


# ── Tests de robustesse ──────────────────────────────────────────────


class TestRobustness:
    """Gestion d'erreurs et cas limites."""

    def test_non_existent_file(self, tmp_photo: Path):
        """Fichier inexistant → dict vide."""
        result = read_tags(tmp_photo.parent / "inexistant.JPG")
        assert result == {}

    def test_write_non_existent_file(self):
        """Écrire sur fichier inexistant → erreur."""
        with pytest.raises(Exception):
            write_tags(Path("/tmp/inexistant_xyz.JPG"), {"hero": True})

    def test_no_exif_on_photo(self, tmp_photo: Path):
        """Photo vierge sans EXIF → lire OK (dict vide)."""
        assert read_tags(tmp_photo) == {}

    def test_write_adds_exif(self, tmp_photo: Path):
        """Écrire des tags sur photo sans EXIF crée la structure EXIF."""
        write_tags(tmp_photo, {"hero": True})
        # Doit pouvoir se relire
        assert read_tags(tmp_photo) == {"hero": True}
        # La photo a maintenant des EXIF valides
        exif_dict = piexif.load(str(tmp_photo))
        assert "Exif" in exif_dict

    def test_case_insensitivity(self, tmp_photo: Path):
        """Les clés sont insensibles à la casse."""
        raw_comment = "album_tags: HERO, FAVORI, REDATER=2012-06-15"
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = raw_comment.encode("utf-8")
        piexif.insert(piexif.dump(exif_dict), str(tmp_photo))

        tags = read_tags(tmp_photo)
        assert tags.get("hero") is True
        assert tags.get("favori") is True
        assert tags.get("redater") == "2012-06-15"

    def test_unicode_texte(self, tmp_photo: Path):
        """Texte avec accents et caractères Unicode."""
        texte = "Premier bain à la mer — été 2012 ♥"
        write_tags(tmp_photo, {"texte": texte})
        tags = read_tags(tmp_photo)
        assert tags.get("texte") == texte

    def test_ongoing_write_read_roundtrip(self, tmp_photo: Path):
        """10 cycles d'écriture/lecture successifs sans perte."""
        for i in range(10):
            tags = read_tags(tmp_photo)
            tags[f"tag_{i}"] = f"value_{i}"
            write_tags(tmp_photo, tags)
        tags = read_tags(tmp_photo)
        assert len(tags) == 10
        assert tags.get("tag_9") == "value_9"
