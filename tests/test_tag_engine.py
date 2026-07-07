"""
Tests unitaires pour tag_engine.py — application des tags EXIF dans le pipeline.

Utilise tag_manager.write_tags() pour préparer des photos taggées,
puis vérifie que tag_engine les interprète correctement.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from album_generator.tag_engine import (
    apply_tags,
    count_tagged_photos,
    get_effective_date,
    get_legend,
    get_score_boost,
    is_hero_tagged,
)
from album_generator.tag_manager import (
    add_tag,
    read_tags,
    write_tags,
)


# ── Helper : JPEG minimal ────────────────────────────────────────────


@pytest.fixture
def tmp_photos(tmp_path: Path) -> list[Path]:
    """Crée 4 photos JPEG vierges pour les tests."""
    photos = []
    for i in range(4):
        fp = tmp_path / f"photo_{i:02d}.jpg"
        img = Image.new("RGB", (2, 2), color=(128, 128, 128))
        img.save(str(fp), "JPEG", quality=85)
        photos.append(fp)
    return photos


# ── apply_tags ───────────────────────────────────────────────────────


class TestApplyTags:
    def test_no_tags_passthrough(self, tmp_photos: list[Path]) -> None:
        """Photos sans tags → inchangées, tag_context vide."""
        filtered, ctx = apply_tags(tmp_photos)
        assert filtered == tmp_photos
        assert ctx == {}

    def test_supprimer_removes_photo(self, tmp_photos: list[Path]) -> None:
        """Tag supprimer → photo retirée du pipeline."""
        add_tag(tmp_photos[0], "supprimer", True)
        filtered, ctx = apply_tags(tmp_photos)
        assert tmp_photos[0] not in filtered
        assert len(filtered) == 3

    def test_supprimer_does_not_appear_in_context(self, tmp_photos: list[Path]) -> None:
        """Photo supprimée → pas dans tag_context."""
        add_tag(tmp_photos[0], "supprimer", True)
        _, ctx = apply_tags(tmp_photos)
        abs_path = str(tmp_photos[0].resolve())
        assert abs_path not in ctx

    def test_hero_in_context(self, tmp_photos: list[Path]) -> None:
        """Tag hero → stocké dans tag_context."""
        add_tag(tmp_photos[1], "hero", True)
        filtered, ctx = apply_tags(tmp_photos)
        abs_path = str(tmp_photos[1].resolve())
        assert abs_path in ctx
        assert ctx[abs_path]["hero"] is True
        assert tmp_photos[1] in filtered

    def test_favori_in_context(self, tmp_photos: list[Path]) -> None:
        """Tag favori → stocké dans tag_context."""
        add_tag(tmp_photos[2], "favori", True)
        filtered, ctx = apply_tags(tmp_photos)
        abs_path = str(tmp_photos[2].resolve())
        assert abs_path in ctx
        assert ctx[abs_path]["favori"] is True

    def test_redater_in_context(self, tmp_photos: list[Path]) -> None:
        """Tag redater → stocké dans tag_context."""
        add_tag(tmp_photos[0], "redater", "2012-06-15")
        filtered, ctx = apply_tags(tmp_photos)
        abs_path = str(tmp_photos[0].resolve())
        assert abs_path in ctx
        assert ctx[abs_path]["redater"] == "2012-06-15"

    def test_texte_in_context(self, tmp_photos: list[Path]) -> None:
        """Tag texte → stocké dans tag_context."""
        add_tag(tmp_photos[0], "texte", "Premier bain")
        filtered, ctx = apply_tags(tmp_photos)
        abs_path = str(tmp_photos[0].resolve())
        assert abs_path in ctx
        assert ctx[abs_path]["texte"] == "Premier bain"

    def test_multiple_tags(self, tmp_photos: list[Path]) -> None:
        """Plusieurs tags sur une même photo."""
        add_tag(tmp_photos[0], "hero", True)
        add_tag(tmp_photos[0], "favori", True)
        add_tag(tmp_photos[0], "texte", "Anniversaire")
        add_tag(tmp_photos[0], "redater", "2012-07-14")

        filtered, ctx = apply_tags(tmp_photos)
        abs_path = str(tmp_photos[0].resolve())
        tags = ctx[abs_path]
        assert tags["hero"] is True
        assert tags["favori"] is True
        assert tags["texte"] == "Anniversaire"
        assert tags["redater"] == "2012-07-14"
        assert tmp_photos[0] in filtered

    def test_mixed_tags(self, tmp_photos: list[Path]) -> None:
        """Mélange de photos taggées et non taggées."""
        add_tag(tmp_photos[0], "supprimer", True)
        add_tag(tmp_photos[1], "hero", True)
        add_tag(tmp_photos[2], "favori", True)
        # photo_03 sans tag

        filtered, ctx = apply_tags(tmp_photos)
        assert len(filtered) == 3  # 1 supprimée
        assert tmp_photos[0] not in filtered

        abs_1 = str(tmp_photos[1].resolve())
        abs_2 = str(tmp_photos[2].resolve())
        assert ctx[abs_1]["hero"] is True
        assert ctx[abs_2]["favori"] is True


# ── get_effective_date ──────────────────────────────────────────────


class TestGetEffectiveDate:
    def test_redater_overrides_exif(self, tmp_photos: list[Path]) -> None:
        """Tag redater → utilise la date taggée, pas l'EXIF."""
        add_tag(tmp_photos[0], "redater", "2015-08-20")
        _, ctx = apply_tags(tmp_photos)
        dt = get_effective_date(tmp_photos[0], ctx)
        assert dt is not None
        assert dt.year == 2015
        assert dt.month == 8
        assert dt.day == 20

    def test_no_redater_falls_to_exif(self, tmp_photos: list[Path]) -> None:
        """Sans redater → retourne date EXIF (None si pas d'EXIF)."""
        dt = get_effective_date(tmp_photos[0])
        assert dt is None  # JPEG minimal sans EXIF

    def test_no_tag_context(self, tmp_photos: list[Path]) -> None:
        """Sans tag_context → pas d'erreur, retourne EXIF."""
        dt = get_effective_date(tmp_photos[0], None)
        # Pas de crash, retourne ce que extract_exif_date donne
        assert dt is None or isinstance(dt, datetime)

    def test_invalid_redater_format(self, tmp_photos: list[Path]) -> None:
        """Redater mal formatté → ignore et retourne EXIF."""
        add_tag(tmp_photos[0], "redater", "pas-une-date")
        _, ctx = apply_tags(tmp_photos)
        dt = get_effective_date(tmp_photos[0], ctx)
        # Doit tomber sur le fallback EXIF (None ici)
        assert dt is None


# ── is_hero_tagged ──────────────────────────────────────────────────


class TestIsHeroTagged:
    def test_hero_tagged_true(self, tmp_photos: list[Path]) -> None:
        """Photo avec tag hero → True."""
        add_tag(tmp_photos[0], "hero", True)
        _, ctx = apply_tags(tmp_photos)
        assert is_hero_tagged(tmp_photos[0], ctx) is True

    def test_not_hero_tagged(self, tmp_photos: list[Path]) -> None:
        """Photo sans tag hero → False."""
        add_tag(tmp_photos[0], "favori", True)
        _, ctx = apply_tags(tmp_photos)
        assert is_hero_tagged(tmp_photos[0], ctx) is False

    def test_no_context(self, tmp_photos: list[Path]) -> None:
        """Sans tag_context → False."""
        assert is_hero_tagged(tmp_photos[0], None) is False

    def test_hero_with_supprimer(self, tmp_photos: list[Path]) -> None:
        """Hero + supprimer → supprimer gagne (photo retirée)."""
        add_tag(tmp_photos[0], "hero", True)
        add_tag(tmp_photos[0], "supprimer", True)
        filtered, ctx = apply_tags(tmp_photos)
        assert tmp_photos[0] not in filtered
        assert str(tmp_photos[0].resolve()) not in ctx


# ── get_score_boost ─────────────────────────────────────────────────


class TestGetScoreBoost:
    def test_favori_boost(self, tmp_photos: list[Path]) -> None:
        """Favori → 1.20."""
        add_tag(tmp_photos[0], "favori", True)
        _, ctx = apply_tags(tmp_photos)
        assert get_score_boost(tmp_photos[0], ctx) == 1.20

    def test_no_favori(self, tmp_photos: list[Path]) -> None:
        """Pas favori → 1.0."""
        add_tag(tmp_photos[0], "hero", True)
        _, ctx = apply_tags(tmp_photos)
        assert get_score_boost(tmp_photos[0], ctx) == 1.0

    def test_no_context(self, tmp_photos: list[Path]) -> None:
        """Sans contexte → 1.0."""
        assert get_score_boost(tmp_photos[0], None) == 1.0

    def test_string_path(self, tmp_photos: list[Path]) -> None:
        """Accepte un str aussi bien qu'un Path."""
        add_tag(tmp_photos[0], "favori", True)
        _, ctx = apply_tags(tmp_photos)
        assert get_score_boost(str(tmp_photos[0]), ctx) == 1.20


# ── get_legend ──────────────────────────────────────────────────────


class TestGetLegend:
    def test_with_texte(self, tmp_photos: list[Path]) -> None:
        """Tag texte → retourne le texte."""
        add_tag(tmp_photos[0], "texte", "Premier bain de Mael")
        _, ctx = apply_tags(tmp_photos)
        assert get_legend(tmp_photos[0], ctx) == "Premier bain de Mael"

    def test_no_texte(self, tmp_photos: list[Path]) -> None:
        """Sans texte → chaîne vide."""
        add_tag(tmp_photos[0], "hero", True)
        _, ctx = apply_tags(tmp_photos)
        assert get_legend(tmp_photos[0], ctx) == ""

    def test_texte_empty_string(self, tmp_photos: list[Path]) -> None:
        """Texte vide → chaîne vide."""
        add_tag(tmp_photos[0], "texte", "")
        _, ctx = apply_tags(tmp_photos)
        assert get_legend(tmp_photos[0], ctx) == ""

    def test_no_context(self, tmp_photos: list[Path]) -> None:
        """Sans contexte → chaîne vide."""
        assert get_legend(tmp_photos[0], None) == ""

    def test_texte_with_unicode(self, tmp_photos: list[Path]) -> None:
        """Texte avec caractères Unicode."""
        add_tag(tmp_photos[0], "texte", "🎉 Anniversaire de Mael 🎂")
        _, ctx = apply_tags(tmp_photos)
        assert get_legend(tmp_photos[0], ctx) == "🎉 Anniversaire de Mael 🎂"


# ── count_tagged_photos ─────────────────────────────────────────────


class TestCountTaggedPhotos:
    def test_counts_single(self, tmp_photos: list[Path]) -> None:
        """Compte les photos par tag."""
        add_tag(tmp_photos[0], "hero", True)
        add_tag(tmp_photos[1], "favori", True)
        add_tag(tmp_photos[2], "texte", "Hello")
        _, ctx = apply_tags(tmp_photos)
        counts = count_tagged_photos(ctx)
        assert counts.get("hero") == 1
        assert counts.get("favori") == 1
        assert counts.get("texte") == 1

    def test_counts_multiple_same_tag(self, tmp_photos: list[Path]) -> None:
        """Plusieurs photos avec le même tag."""
        add_tag(tmp_photos[0], "hero", True)
        add_tag(tmp_photos[2], "hero", True)
        _, ctx = apply_tags(tmp_photos)
        counts = count_tagged_photos(ctx)
        assert counts.get("hero") == 2

    def test_empty_context(self) -> None:
        """Contexte vide → dict vide."""
        assert count_tagged_photos({}) == {}
