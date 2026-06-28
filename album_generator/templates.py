"""
Système de templates structurés V2 (P1-P7 portrait-friendly + T9 conservé).

8 templates prédéfinis avec zones photo (hero/medium/small) et zones texte (10-40%).
Workflow : scoring → TemplateSelector.select() → PhotoDispatcher.dispatch() →
           TextGenerator.generate() → rendu HTML.

Usage :
    from album_generator.templates import (
        TemplateSelector, PhotoDispatcher, TextGenerator,
        get_all_templates, get_template_by_id,
    )

    selector = TemplateSelector()
    template = selector.select(photo_scores, window_idx)
    dispatcher = PhotoDispatcher(template)
    assignments = dispatcher.dispatch(photo_scores)
    tg = TextGenerator()
    assignments = tg.generate_texts(assignments, photo_scores)
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Classe Zone ───────────────────────────────────────────────────────


class Zone:
    """Une zone dans un template.

    Attributes:
        id: identifiant unique dans le template (ex: "hero", "txt01", "small")
        type: "photo" | "text"
        size: "hero" | "medium" | "small"
        col, row: position dans la grille CSS (unités fractionnaires)
        width, height: étendue dans la grille
        min_score: score minimum requis (zones photo uniquement)
        content: pour les zones texte — "legend" | "month" | "event" |
                 "description" | "full"
        spiral_pos: position dans la spirale (T9 uniquement)
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: str = data["id"]
        self.type: str = data["type"]
        self.size: str = data["size"]
        self.col: int = data["col"]
        self.row: int = data["row"]
        self.width: int = data["width"]
        self.height: int = data["height"]
        self.min_score: float = data.get("min_score", 0.0)
        self.content: str = data.get("content", "legend")
        self.spiral_pos: Optional[int] = data.get("spiral_pos")
        self.aspect_target: Optional[float] = data.get("aspect_target")

    def area(self) -> int:
        """Surface en unités de grille."""
        return self.width * self.height

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "size": self.size,
            "col": self.col,
            "row": self.row,
            "width": self.width,
            "height": self.height,
            "min_score": self.min_score,
            "content": self.content if self.type == "text" else None,
        }

    def __repr__(self) -> str:
        return (f"Zone(id={self.id}, type={self.type}, size={self.size}, "
                f"area={self.area()})")


# ── Classe Template ────────────────────────────────────────────────────


class Template:
    """Un template de page d'album avec ses zones.

    Attributes:
        id: identifiant unique (P1, P2, ..., P7, T9)
        name: nom lisible (ex: "heroique-vertical")
        description: description textuelle
        zones: liste de Zone
        total_zones, photo_zones, text_zones: compteurs
        best_for: description du cas d'usage idéal
        spiral_grid: grille spirale (T9 uniquement)
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: str = data.get("description", "")
        self.total_zones: int = data["total_zones"]
        self.photo_zones: int = data["photo_zones"]
        self.text_zones: int = data["text_zones"]
        self.best_for: str = data.get("best_for", "")
        self.spiral_grid: Optional[List[List[int]]] = data.get("spiral_grid")
        self._zones: List[Zone] = [Zone(z) for z in data["zones"]]

    @property
    def zones(self) -> List[Zone]:
        return self._zones

    def photo_zones_list(self) -> List[Zone]:
        """Zones photo, triées par taille décroissante (hero → medium → small)."""
        zones = [z for z in self._zones if z.type == "photo"]
        zones.sort(key=lambda z: z.area(), reverse=True)
        return zones

    def text_zones_list(self) -> List[Zone]:
        """Zones texte."""
        return [z for z in self._zones if z.type == "text"]

    def hero_min_score(self) -> float:
        """Score minimum requis pour la zone photo la plus exigeante."""
        photos = self.photo_zones_list()
        return max(z.min_score for z in photos) if photos else 0.0

    def validate(self) -> bool:
        """Vérifie l'intégrité du template (pas de chevauchement)."""
        cells: Dict[Tuple[int, int], str] = {}
        for z in self._zones:
            for r in range(z.row, z.row + z.height):
                for c in range(z.col, z.col + z.width):
                    key = (c, r)
                    if key in cells:
                        return False
                    cells[key] = z.id
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "total_zones": self.total_zones,
            "photo_zones": self.photo_zones,
            "text_zones": self.text_zones,
            "best_for": self.best_for,
            "zones": [z.to_dict() for z in self._zones],
        }

    def __repr__(self) -> str:
        return (f"Template(id={self.id}, name={self.name}, "
                f"photos={self.photo_zones}, text={self.text_zones})")


# ── 8 Templates JSON V2 (P1-P7 portrait-friendly + T9 conservé) ──────
# Source : rapport Athéna V2 (sections 4.1–4.8)

_TEMPLATES_JSON: List[Dict[str, Any]] = [
    # ═══ P1 — Colonne unique (3 photos + 1 texte) ═══
    {
        "id": "P1",
        "name": "colonne-unique",
        "description": "Hero 100% largeur sur 70% hauteur + texte EXIF + 2 small en bas",
        "total_zones": 4,
        "photo_zones": 3,
        "text_zones": 1,
        "best_for": "Photo hero portrait forte + légende EXIF + 2 photos contextuelles en bas",
        "zones": [
            {"id": "hero", "type": "photo", "size": "hero",
             "col": 0, "row": 0, "width": 2, "height": 4, "min_score": 0.75, "aspect_target": 1.5},
            {"id": "txt01", "type": "text", "size": "medium",
             "col": 0, "row": 4, "width": 2, "height": 1, "content": "legend"},
            {"id": "small_l", "type": "photo", "size": "small",
             "col": 0, "row": 5, "width": 1, "height": 1, "min_score": 0.30, "aspect_target": 1.0},
            {"id": "small_r", "type": "photo", "size": "small",
             "col": 1, "row": 5, "width": 1, "height": 1, "min_score": 0.30, "aspect_target": 1.0},
        ],
    },
    # ═══ P2 — Duo colonnes (4 photos + 1 texte) ═══
    {
        "id": "P2",
        "name": "duo-colonnes",
        "description": "Deux colonnes verticales — hero à gauche, 2 medium empilées à droite, texte large en bas",
        "total_zones": 6,
        "photo_zones": 5,
        "text_zones": 1,
        "best_for": "Deux photos fortes en parallèle (before/after, duo) + légende développée",
        "zones": [
            {"id": "hero", "type": "photo", "size": "hero",
             "col": 0, "row": 0, "width": 1, "height": 3, "min_score": 0.75, "aspect_target": 1.41},
            {"id": "medium_t", "type": "photo", "size": "medium",
             "col": 1, "row": 0, "width": 1, "height": 1, "min_score": 0.50, "aspect_target": 1.41},
            {"id": "medium_b", "type": "photo", "size": "medium",
             "col": 1, "row": 1, "width": 1, "height": 2, "min_score": 0.50, "aspect_target": 1.41},
            {"id": "txt01", "type": "text", "size": "medium",
             "col": 0, "row": 3, "width": 2, "height": 2, "content": "legend"},
            {"id": "small_l", "type": "photo", "size": "small",
             "col": 0, "row": 5, "width": 1, "height": 1, "min_score": 0.30, "aspect_target": 1.0},
            {"id": "small_r", "type": "photo", "size": "small",
             "col": 1, "row": 5, "width": 1, "height": 1, "min_score": 0.30, "aspect_target": 1.0},
        ],
    },
    # ═══ P3 — Triptyque 60/40 (2 photos + 1 texte) ═══
    {
        "id": "P3",
        "name": "triptyque-60-40",
        "description": "60% haut = 2 photos hero côte à côte + 40% bas = texte EXIF long",
        "total_zones": 3,
        "photo_zones": 2,
        "text_zones": 1,
        "best_for": "Événement avec 2 photos fortes + longue description narrative (Anniversaire, Mariage)",
        "zones": [
            {"id": "hero_l", "type": "photo", "size": "hero",
             "col": 0, "row": 0, "width": 1, "height": 4, "min_score": 0.60, "aspect_target": 1.41},
            {"id": "hero_r", "type": "photo", "size": "hero",
             "col": 1, "row": 0, "width": 1, "height": 4, "min_score": 0.60, "aspect_target": 1.41},
            {"id": "txt01", "type": "text", "size": "hero",
             "col": 0, "row": 4, "width": 2, "height": 2, "content": "full"},
        ],
    },
    # ═══ P4 — Mosaïque portrait (5 photos + 1 texte) ═══
    {
        "id": "P4",
        "name": "mosaique-portrait",
        "description": "5 photos en mosaïque verticale — medium large en haut, 2 medium côte à côte, small en bas + texte",
        "total_zones": 6,
        "photo_zones": 5,
        "text_zones": 1,
        "best_for": "5 photos de qualité moyenne à bonne — narrative riche, densité équilibrée",
        "zones": [
            {"id": "medium_t", "type": "photo", "size": "medium",
             "col": 0, "row": 0, "width": 2, "height": 2, "min_score": 0.50, "aspect_target": 1.41},
            {"id": "medium_l", "type": "photo", "size": "medium",
             "col": 0, "row": 2, "width": 1, "height": 2, "min_score": 0.45, "aspect_target": 1.41},
            {"id": "medium_r", "type": "photo", "size": "medium",
             "col": 1, "row": 2, "width": 1, "height": 2, "min_score": 0.45, "aspect_target": 1.41},
            {"id": "txt01", "type": "text", "size": "small",
             "col": 0, "row": 4, "width": 2, "height": 1, "content": "legend"},
            {"id": "small_l", "type": "photo", "size": "small",
             "col": 0, "row": 5, "width": 1, "height": 1, "min_score": 0.30, "aspect_target": 1.0},
            {"id": "small_r", "type": "photo", "size": "small",
             "col": 1, "row": 5, "width": 1, "height": 1, "min_score": 0.30, "aspect_target": 1.0},
        ],
    },
    # ═══ P5 — Asymétrique vertical (4 photos + 1 texte) ═══
    {
        "id": "P5",
        "name": "asymetrique-vertical",
        "description": "Hero gauche verticale + bloc droit (medium + texte) + medium large en bas + 2 small",
        "total_zones": 6,
        "photo_zones": 5,
        "text_zones": 1,
        "best_for": "Photo hero forte + 3 secondaires + légende — l'équivalent portrait du T2 original",
        "zones": [
            {"id": "hero", "type": "photo", "size": "hero",
             "col": 0, "row": 0, "width": 1, "height": 3, "min_score": 0.75, "aspect_target": 1.41},
            {"id": "medium_r", "type": "photo", "size": "medium",
             "col": 1, "row": 0, "width": 1, "height": 2, "min_score": 0.50, "aspect_target": 1.41},
            {"id": "txt01", "type": "text", "size": "small",
             "col": 1, "row": 2, "width": 1, "height": 1, "content": "legend"},
            {"id": "medium_b", "type": "photo", "size": "medium",
             "col": 0, "row": 3, "width": 2, "height": 2, "min_score": 0.45, "aspect_target": 1.41},
            {"id": "small_l", "type": "photo", "size": "small",
             "col": 0, "row": 5, "width": 1, "height": 1, "min_score": 0.25, "aspect_target": 1.0},
            {"id": "small_r", "type": "photo", "size": "small",
             "col": 1, "row": 5, "width": 1, "height": 1, "min_score": 0.25, "aspect_target": 1.0},
        ],
    },
    # ═══ P6 — Diptyque (2 photos + 1 texte) ═══
    {
        "id": "P6",
        "name": "diptyque",
        "description": "Hero grand format (67% hauteur) + texte EXIF large + small contextuelle en bas",
        "total_zones": 3,
        "photo_zones": 2,
        "text_zones": 1,
        "best_for": "Photo très forte (score ≥ 0.80) = exceptionnelle, avec légende longue + photo d'ambiance",
        "zones": [
            {"id": "hero", "type": "photo", "size": "hero",
             "col": 0, "row": 0, "width": 1, "height": 4, "min_score": 0.80, "aspect_target": 1.5},
            {"id": "txt01", "type": "text", "size": "medium",
             "col": 0, "row": 4, "width": 1, "height": 1, "content": "full"},
            {"id": "small", "type": "photo", "size": "small",
             "col": 0, "row": 5, "width": 1, "height": 1, "min_score": 0.35, "aspect_target": 1.0},
        ],
    },
    # ═══ P7 — Quadriptyque (4 photos, sans texte) ═══
    {
        "id": "P7",
        "name": "quadriptyque",
        "description": "4 zones medium de taille égale en grille 2×2 — sans texte, 100% photo",
        "total_zones": 4,
        "photo_zones": 4,
        "text_zones": 0,
        "best_for": "4 photos de force égale — grille dense, pas de hiérarchie, ambiance galerie",
        "zones": [
            {"id": "medium_tl", "type": "photo", "size": "medium",
             "col": 0, "row": 0, "width": 1, "height": 3, "min_score": 0.40, "aspect_target": 1.41},
            {"id": "medium_tr", "type": "photo", "size": "medium",
             "col": 1, "row": 0, "width": 1, "height": 3, "min_score": 0.40, "aspect_target": 1.41},
            {"id": "medium_bl", "type": "photo", "size": "medium",
             "col": 0, "row": 3, "width": 1, "height": 3, "min_score": 0.40, "aspect_target": 1.41},
            {"id": "medium_br", "type": "photo", "size": "medium",
             "col": 1, "row": 3, "width": 1, "height": 3, "min_score": 0.40, "aspect_target": 1.41},
        ],
    },
    # ═══ T9 — Pellicule spirale (conservé de V1) ═══
    {
        "id": "T9",
        "name": "pellicule-spirale",
        "description": "20 frames vidéo en disposition spirale 5×4, habillage pellicule 35mm",
        "total_zones": 21,
        "photo_zones": 20,
        "text_zones": 1,
        "spiral_grid": [
            [1, 2, 3, 4],
            [14, 15, 16, 5],
            [13, 20, 17, 6],
            [12, 19, 18, 7],
            [11, 10, 9, 8],
        ],
        "zones": [
            {"id": "frame_01", "type": "photo", "size": "small",
             "col": 0, "row": 0, "width": 1, "height": 1, "spiral_pos": 1},
            {"id": "frame_02", "type": "photo", "size": "small",
             "col": 1, "row": 0, "width": 1, "height": 1, "spiral_pos": 2},
            {"id": "frame_03", "type": "photo", "size": "small",
             "col": 2, "row": 0, "width": 1, "height": 1, "spiral_pos": 3},
            {"id": "frame_04", "type": "photo", "size": "small",
             "col": 3, "row": 0, "width": 1, "height": 1, "spiral_pos": 4},
            {"id": "frame_05", "type": "photo", "size": "small",
             "col": 3, "row": 1, "width": 1, "height": 1, "spiral_pos": 5},
            {"id": "frame_06", "type": "photo", "size": "small",
             "col": 3, "row": 2, "width": 1, "height": 1, "spiral_pos": 6},
            {"id": "frame_07", "type": "photo", "size": "small",
             "col": 3, "row": 3, "width": 1, "height": 1, "spiral_pos": 7},
            {"id": "frame_08", "type": "photo", "size": "small",
             "col": 3, "row": 4, "width": 1, "height": 1, "spiral_pos": 8},
            {"id": "frame_09", "type": "photo", "size": "small",
             "col": 2, "row": 4, "width": 1, "height": 1, "spiral_pos": 9},
            {"id": "frame_10", "type": "photo", "size": "small",
             "col": 1, "row": 4, "width": 1, "height": 1, "spiral_pos": 10},
            {"id": "frame_11", "type": "photo", "size": "small",
             "col": 0, "row": 4, "width": 1, "height": 1, "spiral_pos": 11},
            {"id": "frame_12", "type": "photo", "size": "small",
             "col": 0, "row": 3, "width": 1, "height": 1, "spiral_pos": 12},
            {"id": "frame_13", "type": "photo", "size": "small",
             "col": 0, "row": 2, "width": 1, "height": 1, "spiral_pos": 13},
            {"id": "frame_14", "type": "photo", "size": "small",
             "col": 0, "row": 1, "width": 1, "height": 1, "spiral_pos": 14},
            {"id": "frame_15", "type": "photo", "size": "small",
             "col": 1, "row": 1, "width": 1, "height": 1, "spiral_pos": 15},
            {"id": "frame_16", "type": "photo", "size": "small",
             "col": 2, "row": 1, "width": 1, "height": 1, "spiral_pos": 16},
            {"id": "frame_17", "type": "photo", "size": "small",
             "col": 2, "row": 2, "width": 1, "height": 1, "spiral_pos": 17},
            {"id": "frame_18", "type": "photo", "size": "small",
             "col": 2, "row": 3, "width": 1, "height": 1, "spiral_pos": 18},
            {"id": "frame_19", "type": "photo", "size": "small",
             "col": 1, "row": 3, "width": 1, "height": 1, "spiral_pos": 19},
            {"id": "frame_20", "type": "photo", "size": "small",
             "col": 1, "row": 2, "width": 1, "height": 1, "spiral_pos": 20},
            {"id": "txt01", "type": "text", "size": "medium",
             "col": 0, "row": 5, "width": 4, "height": 1, "content": "legend"},
        ],
        "best_for": "vidéos découpées en best frames, storytelling chronologique",
    },
]


def get_all_templates() -> List[Template]:
    """Charge et retourne les 8 templates (P1-P7 + T9)."""
    return [Template(t) for t in _TEMPLATES_JSON]


def get_template_by_id(template_id: str) -> Optional[Template]:
    """Retourne un template par son ID (ex: 'P1', 'P5')."""
    tid = template_id.upper()
    for t in _TEMPLATES_JSON:
        if t["id"] == tid:
            return Template(t)
    return None


# ── TemplateSelector ───────────────────────────────────────────────────


class TemplateSelector:
    """Sélectionne le meilleur template pour un lot de photos scorées.

    Critères de sélection :
    1. Nombre de photos disponibles (≥ photo_zones du template)
    2. Score de la meilleure photo (≥ min_score de la hero)
    3. Variété : pas deux fois le même template consécutif
    4. Priorité au template dont la hero correspond le mieux au top_score
    """

    # Templates utilisables pour la sélection automatique (T9 exclu car
    # réservé aux vidéos — sera sélectionné explicitement par le pipeline)
    _AUTO_TEMPLATES = ["P1", "P2", "P3", "P4", "P6", "P7"]

    def __init__(
        self,
        templates: Optional[List[Template]] = None,
    ) -> None:
        self._templates = templates or get_all_templates()
        self._last_used: Optional[str] = None

    @property
    def last_used(self) -> Optional[str]:
        return self._last_used

    @last_used.setter
    def last_used(self, template_id: Optional[str]) -> None:
        self._last_used = template_id

    def select(
        self,
        photo_scores: List[Tuple[str, float, Dict[str, float]]],
        used_templates: Optional[List[str]] = None,
    ) -> Optional[Template]:
        """Sélectionne le meilleur template pour un lot de photos.

        Args:
            photo_scores: liste de (path, score, details)
            used_templates: IDs des templates déjà utilisés (évite répétition)

        Returns:
            Le Template sélectionné, ou None si aucun n'est compatible.
        """
        if not photo_scores:
            return None

        top_score = max(ps[1] for ps in photo_scores)
        photo_count = len(photo_scores)
        # Ne bloquer que le template précédent (pas tous les utilisés)
        last_used_id = used_templates[-1] if used_templates else None

        candidates = []
        for t in self._templates:
            # T9 réservé aux vidéos — pas dans la sélection auto
            if t.id == "T9":
                continue

            # Doit avoir assez de photos pour remplir les zones photo
            if t.photo_zones > photo_count:
                # P6 toléré même avec 1 photo si le score est exceptionnel
                if t.id != "P6":
                    continue

            # Top score doit atteindre le min_score de la hero
            hero_min = t.hero_min_score()
            if top_score < hero_min:
                continue

            # Éviter seulement la répétition consécutive du même template
            if t.id == last_used_id:
                continue

            # Score de matching : écart entre top_score et hero_min
            match_score = abs(top_score - hero_min)
            candidates.append((match_score, t))

        if not candidates:
            # Fallback : aucun template ne matche → None (les appelants tombent sur grille)
            return None

        # Prendre le meilleur match (plus petit écart)
        candidates.sort(key=lambda x: x[0])
        best = candidates[0][1]
        self._last_used = best.id
        return best

    def select_by_id(self, template_id: str) -> Optional[Template]:
        """Force la sélection d'un template par son ID."""
        return get_template_by_id(template_id)

    def select_for_video(
        self,
        frame_count: int,
    ) -> Optional[Template]:
        """Sélectionne T9 pour les vidéos si le nombre de frames correspond."""
        if frame_count >= 16:
            for t in self._templates:
                if t.id == "T9":
                    return t
        # < 16 frames → fallback sur sélection auto (comportement standard)
        return None


# ── PhotoDispatcher ────────────────────────────────────────────────────


class PhotoDispatcher:
    """Dispatch les photos scorées dans les zones d'un template.

    Règle d'or : la meilleure photo va dans la plus grande zone (hero).
    Les suivantes remplissent medium → small.
    """

    def __init__(self, template: Template) -> None:
        self._template = template

    def dispatch(
        self,
        photo_scores: List[Tuple[str, float, Dict[str, float]]],
    ) -> Dict[str, Dict[str, Any]]:
        """Assigne les photos aux zones du template.

        Args:
            photo_scores: liste de (path, score, details)

        Returns:
            Dict {zone_id: assignment} où chaque assignment contient:
                - zone_id, type, size
                - Pour les photos : photo_path, score, scores_detail
                - Pour le texte  : content (template de légende), text (vide, rempli
                                   par TextGenerator ensuite)
        """
        assignments: Dict[str, Dict[str, Any]] = {}

        # 1. Trier les photos par score décroissant
        sorted_photos = sorted(photo_scores, key=lambda ps: ps[1], reverse=True)

        # 2. Récupérer les zones photo triées par taille décroissante
        photo_zones = self._template.photo_zones_list()

        # 3. Dispatch : top score → plus grande zone
        for i, zone in enumerate(photo_zones):
            base = zone.to_dict()

            if i < len(sorted_photos):
                path, score, details = sorted_photos[i]
                base["photo_path"] = path
                base["score"] = round(score, 4)
                base["scores_detail"] = details
            else:
                # Pas assez de photos → zone vide (fond de page visible)
                base["photo_path"] = None
                base["score"] = 0.0
                base["scores_detail"] = {}

            assignments[zone.id] = base

        # 4. Zones texte → placeholder (remplies par TextGenerator)
        text_zones = self._template.text_zones_list()
        for zone in text_zones:
            assignments[zone.id] = zone.to_dict()
            # Contenu texte sera généré par TextGenerator.generate_texts()
            assignments[zone.id]["rendered_text"] = ""

        return assignments


# ── TextGenerator ──────────────────────────────────────────────────────


class TextGenerator:
    """Générateur de légendes depuis EXIF ou nom de fichier.

    Formats supportés :
        legend      → "Août 2023"
        month       → "Août"
        event       → "Anniversaire Noah" (si détecté, sinon "Août 2023")
        description → "Août 2023 — Plage" (si lieu, sinon mois+année)
        full        → "Juillet 2024 — Nos vacances en famille"

    Polices : DM Serif Display (header) / Satoshi (corps) — appliquées par CSS.
    """

    _MONTHS_FR = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    ]
    _SEASONS_FR = {
        1: "Hiver", 2: "Hiver", 3: "Printemps", 4: "Printemps",
        5: "Printemps", 6: "Été", 7: "Été", 8: "Été",
        9: "Automne", 10: "Automne", 11: "Automne", 12: "Hiver",
    }

    def __init__(self) -> None:
        self._event_cache: Dict[str, str] = {}

    def generate_texts(
        self,
        assignments: Dict[str, Dict[str, Any]],
        photo_scores: List[Tuple[str, float, Dict[str, float]]],
    ) -> Dict[str, Dict[str, Any]]:
        """Génère les textes pour toutes les zones texte d'un template.

        Args:
            assignments: dict zone_id → assignment (sortie de PhotoDispatcher.dispatch)
            photo_scores: liste de (path, score, details)

        Returns:
            assignments modifiés avec rendered_text rempli pour les zones texte.
        """
        # Trouver le chemin de la photo hero (ou la première photo)
        hero_path: Optional[str] = None
        if photo_scores:
            hero_path = photo_scores[0][0]

        # Générer le texte pour chaque zone texte
        for zone_id, assignment in assignments.items():
            if assignment.get("type") != "text":
                continue

            content_type = assignment.get("content", "legend")
            text = self.generate(hero_path or "", content_type)
            assignment["rendered_text"] = text

        return assignments

    def generate(self, photo_path: str, content_type: str = "legend") -> str:
        """Génère une légende depuis EXIF ou nom de fichier.

        Args:
            photo_path: chemin de la photo source (pour EXIF)
            content_type: "legend" | "month" | "event" | "description" | "full"

        Returns:
            Texte de légende.
        """
        dt = self._extract_date(photo_path)
        mois, annee = self._month_year(dt) if dt else (None, None)

        if content_type == "month":
            return mois or "Souvenirs"

        if content_type == "event":
            event = self._detect_event(photo_path)
            if event:
                return event
            if mois and annee:
                return f"{mois} {annee}"
            return "Souvenirs"

        if content_type == "description":
            base = f"{mois} {annee}" if mois and annee else "Souvenirs"
            lieu = self._extract_location(photo_path)
            if lieu:
                return f"{base} — {lieu}"
            return base

        if content_type == "full":
            if dt:
                saison = self._SEASONS_FR.get(dt.month, "")
                return f"{saison} {dt.year}" if saison else f"{self._MONTHS_FR[dt.month - 1]} {dt.year}"
            return "Souvenirs"

        # "legend" (défaut)
        if mois and annee:
            return f"{mois} {annee}"
        return "Souvenirs"

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_date(photo_path: str) -> Optional[datetime]:
        """Extrait la date EXIF d'une photo via Pillow.

        Returns None si pas d'EXIF ou si la photo n'existe pas.
        """
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS

            with Image.open(photo_path) as img:
                exif_data = img._getexif()
                if not exif_data:
                    return None

                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, "")
                    if tag_name == "DateTimeOriginal":
                        return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")

                return None
        except Exception:
            return None

    @classmethod
    def _month_year(cls, dt: datetime) -> Tuple[str, int]:
        """Retourne (mois_fr, année) à partir d'une date."""
        return cls._MONTHS_FR[dt.month - 1], dt.year

    def _detect_event(self, photo_path: str) -> str:
        """Détecte un événement à partir du chemin de la photo.

        Stratégie simple : analyse le nom du dossier parent pour des
        mots-clés d'événement (anniversaire, noel, vacances, etc.).
        Version enrichissable avec clustering temporel.
        """
        if photo_path in self._event_cache:
            return self._event_cache[photo_path]

        path = Path(photo_path)
        parent_name = path.parent.name.lower()

        event_keywords = {
            "anniversaire": "Anniversaire",
            "noel": "Noël",
            "noël": "Noël",
            "vacances": "Vacances",
            "plage": "Plage",
            "ski": "Ski",
            "rentree": "Rentrée",
            "naissance": "Naissance",
            "bapteme": "Baptême",
            "mariage": "Mariage",
            "paques": "Pâques",
            "halloween": "Halloween",
        }

        for keyword, label in event_keywords.items():
            if keyword in parent_name:
                # Si plusieurs mots, essayer d'extraire "Anniversaire Noah"
                # depuis un pattern "anniversaire_noah" ou "anniversaire-noah"
                rem = parent_name.replace(keyword, "").strip("_- ")
                result = f"{label} {rem.title()}" if rem else label
                self._event_cache[photo_path] = result
                return result

        # Fallback : chercher dans le nom de fichier
        stem = path.stem.lower()
        for keyword, label in event_keywords.items():
            if keyword in stem:
                self._event_cache[photo_path] = label
                return label

        return ""

    @staticmethod
    def _extract_location(photo_path: str) -> str:
        """Extrait le lieu depuis l'EXIF GPS (si disponible)."""
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS

            img = Image.open(photo_path)
            exif_data = img._getexif()
            if not exif_data:
                return ""

            gps_info = {}
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, "")
                if tag_name == "GPSInfo":
                    for gps_tag_id, gps_value in value.items():
                        gps_tag_name = GPSTAGS.get(gps_tag_id, "")
                        gps_info[gps_tag_name] = gps_value
                    break

            if not gps_info:
                return ""

            # GPS info trouvée mais pas de reverse geocoding dans cette v1
            return ""

        except Exception:
            return ""


# ── Helpers pour generate.py ───────────────────────────────────────────

_MONTH_NAMES = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def generate_spiral_grid(rows: int, cols: int) -> List[List[int]]:
    """Génère une grille R×C remplie en spirale horaire depuis (0,0).

    Utile pour étendre T9 à d'autres dimensions (4×3, 6×4).
    """
    grid = [[0] * cols for _ in range(rows)]
    dirs = [(0, 1), (1, 0), (0, -1), (-1, 0)]
    di, r, c = 0, 0, 0
    for val in range(1, rows * cols + 1):
        grid[r][c] = val
        dr, dc = dirs[di]
        if not (0 <= r + dr < rows and 0 <= c + dc < cols
                and grid[r + dr][c + dc] == 0):
            di = (di + 1) % 4
            dr, dc = dirs[di]
        r, c = r + dr, c + dc
    return grid


def template_assignments_to_pages(
    assignments: Dict[str, Dict[str, Any]],
    template: Template,
    page_num: int = 0,
) -> Dict[str, Any]:
    """Convertit les assignments d'un template en dict de page pour le rendu HTML.

    Args:
        assignments: dict zone_id → assignment
        template: le Template sélectionné
        page_num: numéro de page

    Returns:
        Dict compatible avec le système de pages existant :
        {"style": "template_P3", "data": {"template_id": "P3", "zones": [...]}}
    """
    zones_output = []
    for zone_id, assignment in assignments.items():
        zone_out = dict(assignment)
        zones_output.append(zone_out)

    return {
        "style": "template_structured",
        "data": {
            "template_id": template.id,
            "template_name": template.name,
            "zones": zones_output,
            "page_num": page_num,
        },
    }


def new_arrange_pages_with_templates(
    photo_scores: List[Tuple[str, float, Dict[str, float]]],
    window_size: int = 40,
    forced_template_id: Optional[str] = None,
) -> List[Dict]:
    """Version modifiée de arrange_pages_from_scores_v3 utilisant les templates.

    Remplace rectpack par les templates structurés P1-P7 + T9.
    Garde les styles heroique et quatuor existants pour la compatibilité.

    Args:
        photo_scores: liste de (path, score, details) triée par EXIF
        window_size: taille de la fenêtre glissante
        forced_template_id: si spécifié, force ce template pour toutes les pages

    Returns:
        Liste de dicts représentant chaque page.
    """
    from album_generator.config import ALBUM
    from album_generator.scoring import extract_exif_date

    pages: List[Dict] = []
    selector = TemplateSelector()
    text_gen = TextGenerator()

    # Page de garde
    pages.append({"style": "titre", "data": {"album": ALBUM}})

    n = len(photo_scores)
    used_templates: List[str] = []

    for start in range(0, n, window_size):
        window = photo_scores[start:start + window_size]
        if not window:
            break

        # ── Mois/Année du premier élément chronologique ──
        first_path = window[0][0]
        month_label = ""
        dt = extract_exif_date(first_path)
        if dt:
            month_label = f"{_MONTH_NAMES[dt.month - 1]} {dt.year}"
        else:
            month_label = f"Fenêtre {(start // window_size) + 1}"

        # Trier par score décroissant
        window_sorted = sorted(window, key=lambda x: x[1], reverse=True)

        # ── Héroïque : top 1 ──
        top_path, _, _ = window_sorted[0]
        pages.append({
            "style": "heroique",
            "data": {
                "photo": {
                    "path": str(Path(top_path).resolve()),
                    "label": Path(top_path).name,
                },
            },
        })

        # ── Quatuor : positions 2-4 (conservé pour compatibilité) ──
        if len(window_sorted) >= 4:
            quatuor_photos = [
                {
                    "path": str(Path(window_sorted[i][0]).resolve()),
                    "label": Path(window_sorted[i][0]).name,
                }
                for i in range(1, 4)
            ]
            pages.append({
                "style": "quatuor",
                "data": {
                    "photos": quatuor_photos,
                    "month_label": month_label,
                },
            })
        elif len(window_sorted) == 3:
            photos = [
                {
                    "path": str(Path(window_sorted[i][0]).resolve()),
                    "label": Path(window_sorted[i][0]).name,
                }
                for i in range(1, 3)
            ]
            pages.append({
                "style": "grille",
                "data": {"photos": photos, "title": month_label},
            })
        elif len(window_sorted) == 2:
            path2, _, _ = window_sorted[1]
            pages.append({
                "style": "heroique",
                "data": {
                    "photo": {
                        "path": str(Path(path2).resolve()),
                        "label": Path(path2).name,
                    },
                },
            })

        # ── Templates structurés : reste (positions 5+) ──
        rest_start = 4
        rest = window_sorted[rest_start:]

        idx = 0
        while idx < len(rest):
            remaining = rest[idx:]

            if forced_template_id:
                template = selector.select_by_id(forced_template_id)
            else:
                template = selector.select(remaining, used_templates=used_templates)

            if template is None:
                break

            # Combien de photos ce template consomme-t-il ?
            consume = template.photo_zones

            # Si pas assez de photos restantes pour ce template,
            # essayer un template plus petit
            if len(remaining) < consume:
                # Essayer les templates plus petits (P6→P7, par nb de zones)
                smaller = sorted(
                    [t for t in get_all_templates()
                     if t.id != "T9" and t.photo_zones <= len(remaining)],
                    key=lambda t: t.photo_zones,
                    reverse=True,
                )
                if smaller:
                    template = smaller[0]
                    consume = template.photo_zones
                else:
                    # Plus aucun template ne matche → grille simple
                    photos = [
                        {
                            "path": str(Path(r[0]).resolve()),
                            "label": Path(r[0]).name,
                        }
                        for r in remaining
                    ]
                    if photos:
                        pages.append({
                            "style": "grille",
                            "data": {"photos": photos, "title": ""},
                        })
                    break

            batch = remaining[:consume]

            # Dispatch
            dispatcher = PhotoDispatcher(template)
            assignments = dispatcher.dispatch(batch)
            assignments = text_gen.generate_texts(assignments, batch)

            # Convertir en page
            page = template_assignments_to_pages(assignments, template)
            pages.append(page)

            used_templates.append(template.id)
            idx += consume

    # Page de crédits
    pages.append({"style": "credits", "data": {"album": ALBUM}})

    return pages
