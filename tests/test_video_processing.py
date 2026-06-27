#!/usr/bin/env python3
"""
Tests pour video_processing.py — VideoFrameExtractor.

Utilise des vidéos de test synthétiques ou des mocks.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ajouter le projet au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from video_processing import (
    VideoFrameExtractor,
    ExtractedFrame,
    extract_best_frames,
    get_video_metadata,
    batch_extract_frames,
    VIDEO_EXTENSIONS,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_video(tmp_path):
    """Crée un fichier vidéo factice (juste le fichier, pas une vraie vidéo)."""
    path = tmp_path / "test_video.mp4"
    path.write_bytes(b"\x00\x00\x00\x00mock video content")
    return str(path)


@pytest.fixture
def extractor():
    """Crée un extracteur avec paramètres réduits pour les tests."""
    return VideoFrameExtractor(
        top_n=5,
        min_sharpness=0.0,  # Pas de filtrage par netteté en test
        frame_interval=1.0,
        similarity_threshold=1.0,  # Pas de dédoublonnage
        use_face_detection=False,
    )


@pytest.fixture
def output_dir(tmp_path):
    return str(tmp_path / "frames")


# ── Tests VideoFrameExtractor ───────────────────────────────────────────────

class TestVideoFrameExtractor:
    def test_init_defaults(self):
        """Vérifie les valeurs par défaut."""
        e = VideoFrameExtractor()
        assert e.top_n == 30
        assert e.min_sharpness == 15.0
        assert e.frame_interval == 0.5
        assert e.similarity_threshold == 0.92

    def test_init_custom(self):
        """Vérifie les valeurs personnalisées."""
        e = VideoFrameExtractor(
            top_n=10, min_sharpness=5.0, frame_interval=2.0,
            similarity_threshold=0.8, use_face_detection=False,
        )
        assert e.top_n == 10
        assert e.min_sharpness == 5.0
        assert e.use_face_detection is False

    def test_compute_score_sharpness_only(self, extractor):
        """Score avec seulement la netteté."""
        score = extractor._compute_score(sharpness=50.0, face_count=0, has_face=False)
        assert 0.0 <= score <= 1.0
        assert score == pytest.approx(0.3, rel=0.01)  # 50/100 * 0.6

    def test_compute_score_with_face(self, extractor):
        """Score avec visage."""
        score = extractor._compute_score(sharpness=100.0, face_count=1, has_face=True)
        assert score == pytest.approx(1.0, rel=0.01)  # 100/100*0.6 + 0.4

    def test_compute_score_multi_faces(self, extractor):
        """Score avec plusieurs visages."""
        score = extractor._compute_score(sharpness=100.0, face_count=3, has_face=True)
        assert score > 0.9

    def test_compute_score_low_sharpness(self, extractor):
        """Score avec faible netteté."""
        score = extractor._compute_score(sharpness=1.0, face_count=0, has_face=False)
        assert score == pytest.approx(0.006, rel=0.01)

    @patch("cv2.VideoCapture")
    def test_get_video_metadata(self, mock_cap_class, sample_video):
        """Test des métadonnées vidéo."""
        # Mock du VideoCapture - la fonction get_video_metadata utilise
        # cap = cv2.VideoCapture(path) puis cap.get() directement
        mock_cap = MagicMock()
        mock_cap_class.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda x: {
            7: 300,    # CAP_PROP_FRAME_COUNT
            5: 30.0,   # CAP_PROP_FPS
            3: 1920,   # CAP_PROP_FRAME_WIDTH
            4: 1080,   # CAP_PROP_FRAME_HEIGHT
        }.get(x, 0)

        meta = get_video_metadata(sample_video)
        assert meta["filename"] == "test_video.mp4"
        assert meta["size_bytes"] > 0

    def test_video_metadata_invalid_path(self):
        """Chemin invalide."""
        with pytest.raises(FileNotFoundError):
            get_video_metadata("/nonexistent/video.mp4")

    def test_extractor_unknown_extension(self, tmp_path):
        """Extension non supportée."""
        path = tmp_path / "test.txt"
        path.write_text("not a video")
        with pytest.raises(ValueError, match="Extension non supportée"):
            e = VideoFrameExtractor()
            e.extract(str(path), str(tmp_path))

    @patch("cv2.VideoCapture")
    def test_extractor_file_not_found(self, mock_cap_class, tmp_path):
        """Fichier inexistant."""
        path = tmp_path / "nonexistent.mp4"
        with pytest.raises(FileNotFoundError):
            e = VideoFrameExtractor()
            e.extract(str(path), str(tmp_path))


# ── Tests ExtractedFrame ────────────────────────────────────────────────────

class TestExtractedFrame:
    def test_timecode(self):
        """Format du timecode."""
        f = ExtractedFrame(timestamp_sec=3661.5, path="/test.jpg", score=0.8)
        assert f.timecode == "01:01:01.500"

    def test_timecode_zero(self):
        f = ExtractedFrame(timestamp_sec=0.0, path="/test.jpg")
        assert f.timecode == "00:00:00.000"

    def test_timecode_short(self):
        f = ExtractedFrame(timestamp_sec=5.25, path="/test.jpg")
        assert "00:00:05.250" in f.timecode


# ── Tests batch ─────────────────────────────────────────────────────────────

class TestBatchExtract:
    def test_batch_invalid_dir(self):
        """Dossier invalide."""
        with pytest.raises(NotADirectoryError):
            batch_extract_frames("/nonexistent/dir")

    def test_batch_empty_dir(self, tmp_path):
        """Dossier vide."""
        empty = tmp_path / "empty_videos"
        empty.mkdir()
        result = batch_extract_frames(str(empty))
        assert result == {}


# ── Tests constants ─────────────────────────────────────────────────────────

class TestConstants:
    def test_video_extensions(self):
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mov" in VIDEO_EXTENSIONS
        assert ".avi" in VIDEO_EXTENSIONS
        assert ".txt" not in VIDEO_EXTENSIONS
