"""
Système de templates V6 — N1 à N12 (9 templates validés par Armel).

Les définitions JSON sont dans templates_N.json.
Ce module fournit le chargement et les fonctions de dispatch.

Usage:
    from album_generator.templates import load_templates, dispatch_album
    tpl_by_id = load_templates()
    pages = dispatch_album(photo_scores, tpl_by_id, window_size=40)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_TEMPLATES_FILE = Path(__file__).parent / "templates_N.json"


def load_templates(path: Optional[Path] = None) -> Dict[str, Dict]:
    """Charge les templates depuis le fichier JSON.

    Returns:
        Dict {template_id: template_dict} avec les clés:
        id, name, grid, zones, hero (optionnel), max_per_window (optionnel)
    """
    p = path or _TEMPLATES_FILE
    templates = json.loads(p.read_text())
    return {t["id"]: t for t in templates}


# IDs réservés pour les pages spéciales
HERO_IDS = ["N3", "N7"]  # Templates héro : 1 par fenêtre, alternent
MAX_PER_WINDOW = {"N6": 2}  # Templates limités
REGULAR_IDS = ["N1", "N2", "N9", "N10", "N11", "N12"]  # Templates standards


def dispatch_album(
    photo_scores: List[Tuple[str, float, Any]],
    tpl_by_id: Optional[Dict[str, Dict]] = None,
    window_size: int = 40,
) -> List[Tuple[str, List[str], bool]]:
    """Dispatch les photos dans les templates V6.

    Règles par fenêtre de window_size photos (triées chrono EXIF) :
    1. Hero : 1 page N3 ou N7 (alterne). Meilleures photos.
    2. N6 : max 2 pages.
    3. Reste : templates N1,N2,N9,N10,N11,N12 en ordre aléatoire.

    Args:
        photo_scores: liste de (path, score, details) triée EXIF
        tpl_by_id: dict des templates (chargé si None)
        window_size: taille de fenêtre glissante

    Returns:
        Liste de (template_id, [photo_paths], is_hero) par page.
    """
    import random

    if tpl_by_id is None:
        tpl_by_id = load_templates()

    pages: List[Tuple[str, List[str], bool]] = []
    hero_toggle = 0

    for start in range(0, len(photo_scores), window_size):
        window = photo_scores[start : start + window_size]
        if not window:
            break

        # Trier par score décroissant (meilleures photos en premier)
        window_sorted = sorted(window, key=lambda x: x[1], reverse=True)

        # ── Hero ──
        hid = HERO_IDS[hero_toggle % len(HERO_IDS)]
        ht = tpl_by_id[hid]
        hn = sum(1 for z in ht["zones"] if z["type"] == "photo")
        hpaths = [ws[0] for ws in window_sorted[:hn]]
        pages.append((hid, hpaths, True))
        hero_toggle += 1

        used = set(hpaths)
        remaining = [p[0] for p in window if p[0] not in used]

        # ── N6: max 2 ──
        n6n = sum(1 for z in tpl_by_id["N6"]["zones"] if z["type"] == "photo")
        ri = 0
        n6_count = 0
        while n6_count < MAX_PER_WINDOW.get("N6", 2) and ri + n6n <= len(remaining):
            pages.append(("N6", remaining[ri : ri + n6n], False))
            ri += n6n
            n6_count += 1

        # ── Templates standards (ordre aléatoire) ──
        after_n6 = remaining[ri:]
        order = list(REGULAR_IDS)
        random.shuffle(order)

        # Pré-calculer les tailles
        tpl_sizes = {tid: sum(1 for z in tpl_by_id[tid]["zones"] if z["type"] == "photo") for tid in order}

        tpl_idx = 0
        ri2 = 0
        while ri2 < len(after_n6):
            tid = order[tpl_idx % len(order)]
            rn = tpl_sizes[tid]

            if ri2 + rn <= len(after_n6):
                pages.append((tid, after_n6[ri2 : ri2 + rn], False))
                ri2 += rn
            else:
                # Dernier batch : choisir le plus grand template qui rentre
                remain = len(after_n6) - ri2
                fitting = sorted(
                    [x for x in order if tpl_sizes[x] <= remain],
                    key=lambda x: tpl_sizes[x],
                    reverse=True,
                )
                if fitting:
                    fn = tpl_sizes[fitting[0]]
                    pages.append((fitting[0], after_n6[ri2 : ri2 + fn], False))
                    ri2 += fn
                else:
                    ri2 = len(after_n6)
            tpl_idx += 1

    return pages
