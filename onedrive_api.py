#!/usr/bin/env python3
"""
onedrive_api.py — Wrapper Microsoft Graph API pour OneDrive personnel.

Authentification via MSAL (device code flow), compatible comptes Microsoft
personnels (MSA). Supporte le caching de token dans un fichier JSON local.

Usage:
    from onedrive_api import OneDriveClient

    client = OneDriveClient()
    # Première utilisation : génère un code de connexion
    if client.needs_auth():
        code = client.get_auth_url()
        print(f"Va sur {code['verification_uri']} et entre {code['user_code']}")
        input("Appuie sur Entrée après validation...")
        client.complete_auth(code)

    photos = client.list_photos("Images/Pellicule/2025")
    for p in photos:
        print(f"{p['name']} — {p.get('size', 0)} bytes")
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# ── Constantes ────────────────────────────────────────────────────────────────

CLIENT_ID = "22c49a22-d89f-42e2-a264-e0a1b3bdd151"  # Azure CLI (publique OAuth2)
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPE = ["Files.ReadWrite.All", "Files.Read.All"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RETRIES = 3
RETRY_DELAY = 2
PAGE_SIZE = 200  # Nombre max d'items par page Graph API
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".ts", ".3gp", ".webm"}


# ── Exceptions ────────────────────────────────────────────────────────────────

class OneDriveError(Exception):
    """Erreur générique OneDrive."""
    pass

class AuthError(OneDriveError):
    """Erreur d'authentification."""
    pass

class NotFoundError(OneDriveError):
    """Resource non trouvée."""
    pass

class RateLimitError(OneDriveError):
    """Rate limiting (429)."""
    pass


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OneDriveItem:
    """Un fichier ou dossier OneDrive."""
    id: str
    name: str
    path: str                 # Chemin relatif (ex: "Images/Pellicule/2025/photo.jpg")
    size: int = 0
    is_folder: bool = False
    is_video: bool = False
    is_photo: bool = False
    mime_type: str = ""
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_duration: Optional[float] = None
    image_dimensions: Optional[Tuple[int, int]] = None

    @property
    def extension(self) -> str:
        return Path(self.name).suffix.lower()

    @classmethod
    def from_graph_item(cls, item: Dict, parent_path: str = "") -> "OneDriveItem":
        """Construit un OneDriveItem depuis une réponse Graph API."""
        name = item.get("name", "")
        path = f"{parent_path}/{name}" if parent_path else name
        path = path.lstrip("/")

        ext = Path(name).suffix.lower()
        is_folder = "folder" in item
        is_video = ext in VIDEO_EXTENSIONS
        is_photo = ext in PHOTO_EXTENSIONS

        # Dimensions image
        dims = None
        if "image" in item:
            dims = (item["image"].get("width", 0), item["image"].get("height", 0))

        # Durée vidéo
        duration = None
        if "video" in item:
            duration = item["video"].get("duration", None)
            if duration is not None:
                duration = duration / 1000.0  # ms → secondes

        return cls(
            id=item.get("id", ""),
            name=name,
            path=path,
            size=item.get("size", 0),
            is_folder=is_folder,
            is_video=is_video,
            is_photo=is_photo,
            mime_type=item.get("file", {}).get("mimeType", "") if "file" in item else "",
            created_at=item.get("createdDateTime"),
            modified_at=item.get("lastModifiedDateTime"),
            download_url=item.get("@microsoft.graph.downloadUrl"),
            thumbnail_url=None,  # Nécessite un appel séparé
            video_duration=duration,
            image_dimensions=dims,
        )


# ── OneDriveClient ────────────────────────────────────────────────────────────

class OneDriveClient:
    """Client OneDrive avec authentification MSAL et cache de token."""

    def __init__(
        self,
        token_cache_path: str = "~/.config/onedrive/token.json",
        client_id: str = CLIENT_ID,
        scopes: Optional[List[str]] = None,
        drive_id: Optional[str] = None,
    ):
        self.client_id = client_id
        self.scopes = scopes or SCOPE
        self.token_cache_path = Path(token_cache_path).expanduser().resolve()
        self._drive_id = drive_id
        self._token: Optional[Dict[str, Any]] = None
        self._session = requests.Session()
        self._msal_app: Any = None
        self._load_token()

    # ── Authentification ──────────────────────────────────────────────────────

    def _lazy_msal(self):
        """Import et init MSAL au premier appel (permet d'éviter l'import si non utilisé)."""
        if self._msal_app is None:
            try:
                import msal
            except ImportError:
                raise ImportError(
                    "Le module 'msal' est requis. Installe-le avec : pip install msal"
                )
            self._msal_app = msal.PublicClientApplication(
                self.client_id, authority=AUTHORITY
            )
        return self._msal_app

    def _load_token(self) -> None:
        """Charge le token depuis le cache."""
        if self.token_cache_path.exists():
            try:
                data = json.loads(self.token_cache_path.read_text())
                self._token = data.get("token")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Impossible de lire le cache token : {e}")
                self._token = None

    def _save_token(self, token: Dict[str, Any]) -> None:
        """Sauvegarde le token dans le cache."""
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_cache_path.write_text(
            json.dumps({"token": token, "saved_at": datetime.utcnow().isoformat()},
                       indent=2)
        )
        self._token = token

    def _clear_token(self) -> None:
        """Supprime le token en cache."""
        self._token = None
        if self.token_cache_path.exists():
            self.token_cache_path.unlink()

    @property
    def drive_id(self) -> str:
        """Retourne l'ID du drive OneDrive personnel."""
        if self._drive_id is None:
            # Découverte automatique via /me/drive
            data = self._get("/me/drive")
            self._drive_id = data.get("id")
            if not self._drive_id:
                raise OneDriveError("Impossible de déterminer l'ID du drive OneDrive")
            logger.info(f"Drive ID: {self._drive_id}")
        return self._drive_id

    def needs_auth(self) -> bool:
        """Vérifie si un token valide est disponible."""
        if self._token and self._token.get("access_token"):
            # Vérifie expiration
            expires_in = self._token.get("expires_in", 3600)
            acquired_at = self._token.get("acquired_at", 0)
            if time.time() - acquired_at < expires_in - 60:
                return False
            # Token expiré — tente le refresh silencieux
            return not self._try_silent_refresh()
        return True

    def get_auth_url(self) -> Dict[str, Any]:
        """Initie le device code flow et retourne les instructions de connexion."""
        app = self._lazy_msal()
        flow = app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            raise AuthError(
                f"Échec device code flow: {flow.get('error', '')} — "
                f"{flow.get('error_description', '')[:200]}"
            )
        return flow

    def complete_auth(self, flow: Dict[str, Any]) -> bool:
        """Finalise l'authentification après validation humaine du code."""
        app = self._lazy_msal()
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise AuthError(
                f"Échec d'authentification: {result.get('error', '')} — "
                f"{result.get('error_description', '')[:200]}"
            )
        result["acquired_at"] = time.time()
        self._save_token(result)
        logger.info("Authentification OneDrive réussie")
        return True

    def _try_silent_refresh(self) -> bool:
        """Tente un refresh silencieux du token."""
        if not self._token or "refresh_token" not in self._token:
            return False
        try:
            app = self._lazy_msal()
            result = app.acquire_token_by_refresh_token(
                self._token["refresh_token"], scopes=self.scopes
            )
            if "access_token" in result:
                result["acquired_at"] = time.time()
                self._save_token(result)
                return True
        except Exception as e:
            logger.warning(f"Refresh token échoué: {e}")
        return False

    def _get_headers(self) -> Dict[str, str]:
        """Retourne les headers d'authentification."""
        if self.needs_auth():
            raise AuthError("Authentification requise. Appelle needs_auth() puis get_auth_url().")
        return {"Authorization": f"Bearer {self._token['access_token']}"}

    # ── Requêtes HTTP ─────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        retries: int = MAX_RETRIES,
    ) -> Dict[str, Any]:
        """Requête HTTP avec retry et rate limiting."""
        url = f"{GRAPH_BASE}{path}" if not path.startswith("http") else path
        headers = self._get_headers()
        if data is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(retries):
            try:
                resp = self._session.request(
                    method, url, headers=headers, params=params,
                    json=data, timeout=30,
                )

                if resp.status_code == 401:
                    # Token expiré — tente un refresh et réessaie
                    self._clear_token()
                    if self.needs_auth():
                        raise AuthError("Token expiré et refresh impossible")
                    headers = self._get_headers()
                    resp = self._session.request(
                        method, url, headers=headers, params=params,
                        json=data, timeout=30,
                    )

                if resp.status_code == 404:
                    raise NotFoundError(f"Resource non trouvée: {url}")

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", RETRY_DELAY))
                    logger.warning(f"Rate limited. Attente {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                if resp.status_code in (200, 201, 204):
                    return resp.json() if resp.text else {}

                raise OneDriveError(
                    f"HTTP {resp.status_code} sur {url}: {resp.text[:200]}"
                )

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < retries - 1:
                    wait = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Tentative {attempt + 1}/{retries} échouée. Retry dans {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise OneDriveError(f"Connexion impossible après {retries} tentatives: {e}")

        raise OneDriveError(f"Requête échouée après {retries} tentatives")

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        return self._request("GET", path, params=params)

    def _get_paginated(
        self,
        path: str,
        params: Optional[Dict] = None,
    ) -> List[Dict]:
        """Récupère TOUS les résultats avec pagination."""
        items = []
        params = dict(params or {})
        params.setdefault("$top", str(PAGE_SIZE))

        next_url = path
        while next_url:
            data = self._get(next_url, params=params)
            items.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")
            params = None  # Les paramètres sont déjà dans nextLink

        return items

    def download_content(self, item: OneDriveItem) -> bytes:
        """Télécharge le contenu binaire d'un fichier."""
        url = item.download_url or f"/drives/{self.drive_id}/items/{item.id}/content"
        if not url.startswith("http"):
            data = self._get(url)
            url = data.get("@microsoft.graph.downloadUrl", url)

        resp = self._session.get(url, headers=self._get_headers(), timeout=60)
        if resp.status_code != 200:
            raise OneDriveError(f"Échec téléchargement {item.path}: HTTP {resp.status_code}")
        return resp.content

    def download_to_file(self, item: OneDriveItem, local_path: str) -> str:
        """Télécharge un fichier OneDrive vers le disque local."""
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.download_content(item)
        path.write_bytes(content)
        logger.info(f"Téléchargé: {item.path} → {path} ({len(content)} bytes)")
        return str(path)

    # ── OneDrive API : Parcours ───────────────────────────────────────────────

    def list_folder(
        self,
        folder_path: str = "",
        recursive: bool = False,
    ) -> List[OneDriveItem]:
        """Liste le contenu d'un dossier OneDrive.

        Args:
            folder_path: Chemin relatif (ex: "Images/Pellicule/2025")
            recursive: Si True, liste récursivement tout le contenu

        Returns:
            Liste de OneDriveItem
        """
        if not folder_path:
            path = "/me/drive/root/children"
        else:
            encoded = self._encode_path(folder_path)
            path = f"/me/drive/root:/{encoded}:/children"

        raw_items = self._get_paginated(path)
        result = [OneDriveItem.from_graph_item(item, parent_path=folder_path)
                  for item in raw_items]

        if recursive:
            for item in result:
                if item.is_folder:
                    try:
                        sub_items = self.list_folder(item.path, recursive=True)
                        result.extend(sub_items)
                    except Exception as e:
                        logger.warning(f"Impossible de lister {item.path}: {e}")

        return result

    def list_photos(
        self,
        folder_path: str = "",
        recursive: bool = False,
    ) -> List[OneDriveItem]:
        """Liste uniquement les photos (pas les vidéos ni dossiers)."""
        items = self.list_folder(folder_path, recursive=recursive)
        return [i for i in items if i.is_photo]

    def list_videos(
        self,
        folder_path: str = "",
        recursive: bool = False,
    ) -> List[OneDriveItem]:
        """Liste uniquement les vidéos."""
        items = self.list_folder(folder_path, recursive=recursive)
        return [i for i in items if i.is_video]

    def get_item(self, path: str) -> OneDriveItem:
        """Récupère les infos d'un fichier/dossier par son chemin."""
        encoded = self._encode_path(path)
        data = self._get(f"/me/drive/root:/{encoded}")
        if not data:
            raise NotFoundError(f"Item non trouvé: {path}")
        return OneDriveItem.from_graph_item(data, parent_path=str(Path(path).parent))

    def search(self, query: str) -> List[OneDriveItem]:
        """Recherche des fichiers par nom."""
        data = self._get("/me/drive/root/search(q='" + query.replace("'", "''") + "')")
        return [OneDriveItem.from_graph_item(item) for item in data.get("value", [])]

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def _encode_path(self, path: str) -> str:
        """Encode un chemin OneDrive pour l'URL (sauf les slashs)."""
        from urllib.parse import quote
        parts = path.strip("/").split("/")
        return "/".join(quote(p, safe="") for p in parts)

    def get_photo_paths_by_year_month(
        self,
        base_folder: str = "Images/Pellicule",
        years: Optional[List[int]] = None,
    ) -> Dict[str, List[OneDriveItem]]:
        """Parcourt les dossiers année/mois et retourne les photos groupées.

        Args:
            base_folder: Dossier racine (ex: "Images/Pellicule")
            years: Liste d'années (ex: [2024, 2025]). None = toutes.

        Returns:
            Dict: {"2025/01": [OneDriveItem, ...], "2025/02": [...]}
        """
        result: Dict[str, List[OneDriveItem]] = {}
        root_items = self.list_folder(base_folder)

        for item in root_items:
            if not item.is_folder:
                continue
            year = item.name
            if years and year not in {str(y) for y in years}:
                continue
            if not year.isdigit():
                continue

            # Liste les mois dans cette année
            try:
                month_items = self.list_folder(item.path)
            except Exception as e:
                logger.warning(f"Impossible de lister {item.path}: {e}")
                continue

            for month_item in month_items:
                if not month_item.is_folder:
                    continue
                month = month_item.name
                key = f"{year}/{month}"
                try:
                    photos = self.list_photos(month_item.path)
                    if photos:
                        result[key] = photos
                except Exception as e:
                    logger.warning(f"Impossible de lister {month_item.path}: {e}")

        return result

    def close(self):
        """Ferme la session HTTP."""
        self._session.close()
