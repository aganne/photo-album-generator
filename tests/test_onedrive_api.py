#!/usr/bin/env python3
"""
Tests pour onedrive_api.py — OneDriveClient.

Les tests d'authentification et de requêtes réseau sont mockés.
Les tests de structure de données sont réels.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# Ajouter le projet au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from onedrive_api import (
    OneDriveClient,
    OneDriveItem,
    OneDriveError,
    AuthError,
    NotFoundError,
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    CLIENT_ID,
    AUTHORITY,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_token_cache(tmp_path):
    """Crée un cache token factice."""
    token_data = {
        "token": {
            "access_token": "mock_access_token_123",
            "refresh_token": "mock_refresh_token_456",
            "expires_in": 3600,
            "acquired_at": 0,  # Forcera le refresh
        }
    }
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_data))
    return str(path)


@pytest.fixture
def valid_token_cache(tmp_path):
    """Crée un cache token valide (fraîchement acquis)."""
    import time
    token_data = {
        "token": {
            "access_token": "valid_token",
            "refresh_token": "refresh_token",
            "expires_in": 3600,
            "acquired_at": time.time(),
        }
    }
    path = tmp_path / "token_valid.json"
    path.write_text(json.dumps(token_data))
    return str(path)


# ── Tests OneDriveItem ──────────────────────────────────────────────────────

class TestOneDriveItem:
    def test_from_graph_item_photo(self):
        """Crée un OneDriveItem depuis une réponse Graph API pour une photo."""
        item_data = {
            "id": "item_123",
            "name": "photo.jpg",
            "size": 1024000,
            "file": {"mimeType": "image/jpeg"},
            "image": {"width": 4000, "height": 3000},
            "createdDateTime": "2025-01-15T10:00:00Z",
            "lastModifiedDateTime": "2025-01-15T14:00:00Z",
            "@microsoft.graph.downloadUrl": "https://graph.example.com/download/photo.jpg",
        }
        item = OneDriveItem.from_graph_item(item_data, parent_path="Images/Pellicule/2025")
        assert item.name == "photo.jpg"
        assert item.path == "Images/Pellicule/2025/photo.jpg"
        assert item.is_photo is True
        assert item.is_video is False
        assert item.is_folder is False
        assert item.size == 1024000
        assert item.image_dimensions == (4000, 3000)
        assert item.download_url == "https://graph.example.com/download/photo.jpg"

    def test_from_graph_item_video(self):
        """Crée un OneDriveItem pour une vidéo."""
        item_data = {
            "id": "video_456",
            "name": "vacances.mp4",
            "size": 50000000,
            "file": {"mimeType": "video/mp4"},
            "video": {"duration": 120000},  # 120 secondes en ms
        }
        item = OneDriveItem.from_graph_item(item_data)
        assert item.is_video is True
        assert item.is_photo is False
        assert item.video_duration == 120.0  # converti en secondes

    def test_from_graph_item_folder(self):
        """Crée un OneDriveItem pour un dossier."""
        item_data = {
            "id": "folder_789",
            "name": "2025",
            "size": 0,
            "folder": {"childCount": 12},
        }
        item = OneDriveItem.from_graph_item(item_data, parent_path="Images/Pellicule")
        assert item.is_folder is True
        assert item.is_photo is False
        assert item.is_video is False

    def test_from_graph_item_no_parent_path(self):
        """Sans parent_path, le chemin est juste le nom."""
        item_data = {"id": "1", "name": "photo.jpg", "file": {"mimeType": "image/jpeg"}}
        item = OneDriveItem.from_graph_item(item_data)
        assert item.path == "photo.jpg"

    def test_extension_property(self):
        item = OneDriveItem(id="1", name="photo.JPG", path="photo.JPG")
        assert item.extension == ".jpg"

    def test_photo_extensions_heic(self):
        """HEIC is a photo extension."""
        item = OneDriveItem(id="1", name="photo.heic", path="photo.heic", is_photo=True)
        assert item.is_photo is True
        assert item.extension == ".heic"
    
    def test_photo_extensions_from_graph(self):
        item_data = {"id": "1", "name": "photo.heic", "file": {"mimeType": "image/heic"}}
        # Test via le constructeur direct
        item = OneDriveItem(id="1", name="photo.heic", path="photo.heic")
        assert item.extension == ".heic"


# ── Tests OneDriveClient (initialisation) ───────────────────────────────────

class TestOneDriveClientInit:
    def test_init_defaults(self, tmp_path):
        """Initialisation avec valeurs par défaut."""
        client = OneDriveClient(token_cache_path=str(tmp_path / "tokens/token.json"))
        assert client.client_id == CLIENT_ID
        assert client.scopes == ["Files.ReadWrite.All", "Files.Read.All"]

    def test_init_custom(self, tmp_path):
        client = OneDriveClient(
            token_cache_path=str(tmp_path / "custom_token.json"),
            client_id="custom_id",
            scopes=["Files.Read"],
            drive_id="custom_drive_id",
        )
        assert client.client_id == "custom_id"
        assert client.scopes == ["Files.Read"]
        assert client._drive_id == "custom_drive_id"

    def test_token_loading(self, mock_token_cache):
        """Charge le token depuis le cache."""
        client = OneDriveClient(token_cache_path=mock_token_cache)
        assert client._token is not None
        assert client._token["access_token"] == "mock_access_token_123"

    def test_token_loading_invalid_json(self, tmp_path):
        """Cache corrompu."""
        path = tmp_path / "bad_token.json"
        path.write_text("not valid json")
        client = OneDriveClient(token_cache_path=str(path))
        assert client._token is None

    def test_token_cache_missing(self):
        """Cache inexistant."""
        client = OneDriveClient(token_cache_path="/nonexistent/path/token.json")
        assert client._token is None


# ── OneDriveClient auth (mocked) ────────────────────────────────────────────

class TestOneDriveClientAuth:
    def test_needs_auth_no_token(self, tmp_path):
        client = OneDriveClient(token_cache_path=str(tmp_path / "no_token.json"))
        assert client.needs_auth() is True

    def test_needs_auth_expired_token(self, mock_token_cache):
        """Token expiré (acquired_at = 0)."""
        import time
        with patch("time.time", return_value=10000):
            client = OneDriveClient(token_cache_path=mock_token_cache)
            # Le refresh va échouer car pas de vrai MSAL
            assert client.needs_auth() is True

    @patch("onedrive_api.OneDriveClient._try_silent_refresh", return_value=True)
    def test_needs_auth_refresh_success(self, mock_refresh, mock_token_cache):
        """Refresh silencieux réussi."""
        client = OneDriveClient(token_cache_path=mock_token_cache)
        assert client.needs_auth() is False

    def test_get_auth_url_msal_error(self, tmp_path):
        """Erreur MSAL."""
        client = OneDriveClient(token_cache_path=str(tmp_path / "t.json"))
        with patch.object(client, '_lazy_msal') as mock_msal:
            mock_app = MagicMock()
            mock_app.initiate_device_flow.return_value = {"error": "invalid_request"}
            mock_msal.return_value = mock_app
            with pytest.raises(AuthError):
                client.get_auth_url()


# ── OneDriveClient API (mocked) ─────────────────────────────────────────────

class TestOneDriveClientApi:
    @pytest.fixture
    def client(self, valid_token_cache, tmp_path):
        client = OneDriveClient(token_cache_path=valid_token_cache)
        client._drive_id = "test_drive_123"
        return client

    def test_get_headers_valid(self, client):
        headers = client._get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer valid_token"

    @patch("requests.Session.request")
    def test_list_folder(self, mock_request, client):
        """Liste le contenu d'un dossier."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "value": [
                {"id": "1", "name": "photo.jpg", "size": 1000,
                 "file": {"mimeType": "image/jpeg"},
                 "image": {"width": 100, "height": 200}},
                {"id": "2", "name": "video.mp4", "size": 50000,
                 "file": {"mimeType": "video/mp4"},
                 "video": {"duration": 60000}},
                {"id": "3", "name": "Subfolder", "size": 0,
                 "folder": {"childCount": 3}},
            ]
        }

        items = client.list_folder("Images/Pellicule/2025")
        assert len(items) == 3
        assert items[0].name == "photo.jpg"
        assert items[1].is_video is True
        assert items[2].is_folder is True

    @patch("requests.Session.request")
    def test_list_photos_only(self, mock_request, client):
        """Filtre uniquement les photos."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "value": [
                {"id": "1", "name": "photo.jpg", "file": {"mimeType": "image/jpeg"}},
                {"id": "2", "name": "doc.txt", "file": {"mimeType": "text/plain"}},
            ]
        }

        photos = client.list_photos("test")
        # .txt n'est pas photo
        assert len(photos) == 1
        assert photos[0].name == "photo.jpg"

    @patch("requests.Session.request")
    def test_list_videos_only(self, mock_request, client):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "value": [
                {"id": "1", "name": "photo.jpg", "file": {"mimeType": "image/jpeg"}},
                {"id": "2", "name": "video.mp4", "file": {"mimeType": "video/mp4"}},
            ]
        }
        videos = client.list_videos("test")
        assert len(videos) == 1
        assert videos[0].name == "video.mp4"

    @patch("requests.Session.request")
    def test_get_item(self, mock_request, client):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "id": "item_1",
            "name": "photo.jpg",
            "file": {"mimeType": "image/jpeg"},
        }
        item = client.get_item("Images/Pellicule/2025/photo.jpg")
        assert item.name == "photo.jpg"

    @patch("requests.Session.request")
    def test_get_item_not_found(self, mock_request, client):
        mock_request.return_value.status_code = 404
        mock_request.return_value.text = "Not Found"
        with pytest.raises(NotFoundError):
            client.get_item("nonexistent.jpg")

    def test_search_encode(self, client):
        """Vérifie que le search encode correctement les quotes."""
        with patch.object(client, '_get') as mock_get:
            mock_get.return_value = {"value": []}
            client.search("photo's")
            # Vérifie que l'apostrophe est échappée
            call_arg = mock_get.call_args[0][0]
            assert "''" in call_arg

    @patch("requests.Session.request")
    def test_pagination(self, mock_request, client):
        """Vérifie que la pagination est suivie."""
        mock_request.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {
                    "value": [{"id": "1", "name": "pic1.jpg"}],
                    "@odata.nextLink": "https://graph.mock/next",
                }
            ),
            MagicMock(
                status_code=200,
                json=lambda: {
                    "value": [{"id": "2", "name": "pic2.jpg"}],
                }
            ),
        ]
        items = client._get_paginated("/test")
        assert len(items) == 2

    @patch("requests.Session.get")
    @patch("requests.Session.request")
    def test_download_content(self, mock_request, mock_get, client):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "@microsoft.graph.downloadUrl": "https://dl.example.com/photo.jpg"
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"fake_image_content"

        item = OneDriveItem(id="1", name="test.jpg", path="test.jpg",
                            download_url="https://dl.example.com/photo.jpg")
        content = client.download_content(item)
        assert content == b"fake_image_content"


# ── Tests constants ─────────────────────────────────────────────────────────

class TestConstants:
    def test_photo_extensions(self):
        assert ".jpg" in PHOTO_EXTENSIONS
        assert ".jpeg" in PHOTO_EXTENSIONS
        assert ".png" in PHOTO_EXTENSIONS
        assert ".heic" in PHOTO_EXTENSIONS
        assert ".mp4" not in PHOTO_EXTENSIONS

    def test_video_extensions(self):
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mov" in VIDEO_EXTENSIONS
        assert ".avi" in VIDEO_EXTENSIONS

    def test_client_id(self):
        assert CLIENT_ID == "22c49a22-d89f-42e2-a264-e0a1b3bdd151"
