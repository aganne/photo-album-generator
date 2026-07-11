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
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .tag_engine import is_pas_hero_tagged

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


def _derive_ids(tpl_by_id: Dict[str, Dict]) -> Tuple[List[str], Dict[str, int], List[str]]:
    """Dérive les IDs spéciaux depuis les métadonnées des templates (source unique).

    Returns:
        (hero_ids, max_per_window, regular_ids)
    """
    hero_ids = sorted([tid for tid, t in tpl_by_id.items() if t.get("hero")])
    max_per_window = {tid: t["max_per_window"] for tid, t in tpl_by_id.items() if "max_per_window" in t}
    special = set(hero_ids) | set(max_per_window.keys())
    regular_ids = sorted([tid for tid in tpl_by_id if tid not in special])
    if not hero_ids:
        hero_ids = ["N3", "N7"]  # fallback
    if not regular_ids:
        regular_ids = ["N1", "N2", "N9", "N10", "N11", "N12"]  # fallback
    return hero_ids, max_per_window, regular_ids


def _is_hero_eligible(image_path: str, empty_threshold: float = 0.50) -> bool:
    """Vérifie si une photo est éligible comme hero.

    Blacklist :
    - >50% de surface uniforme (mur, ciel, fond vide)
    - Photo trop granuleuse dans les zones d'ombre
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return True  # si on ne peut pas lire, on laisse passer
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        if max(h, w) > 512:
            scale = 512.0 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_AREA)
        h, w = gray.shape
        block_size = 32
        n_blocks_h = h // block_size
        n_blocks_w = w // block_size
        if n_blocks_h < 2 or n_blocks_w < 2:
            return True
        gray = gray[:n_blocks_h * block_size, :n_blocks_w * block_size]
        low_var_count = 0
        total_blocks = n_blocks_h * n_blocks_w
        for i in range(n_blocks_h):
            for j in range(n_blocks_w):
                block = gray[i*block_size:(i+1)*block_size, j*block_size:(j+1)*block_size]
                if np.var(block.astype(np.float64)) < 100:
                    low_var_count += 1
        empty_ratio = low_var_count / total_blocks
        return empty_ratio <= empty_threshold
    except Exception:
        return True


def dispatch_album(
    photo_scores: List[Tuple[str, float, Any]],
    tpl_by_id: Optional[Dict[str, Dict]] = None,
    window_size: int = 40,
    tag_context: Optional[Dict[str, Dict]] = None,
) -> List[Tuple[str, List[str], bool]]:
    """Dispatch les photos dans les templates V6.

    Règles par fenêtre de window_size photos (triées chrono EXIF) :
    1. Hero : 1 page N3 ou N7 (alterne). Meilleures photos.
       Les photos taggées ``hero`` (via tag_context) sont PRIORITAIRES
       pour le slot hero de leur fenêtre. Si plusieurs hero taggés
       dans la fenêtre, la meilleure score est sélectionnée.
       Skip si fenêtre trop petite pour le template.
    2. Templates avec max_per_window : max N pages.
    3. Reste : templates standards en ordre aléatoire, toutes les photos consommées.

    Args:
        photo_scores: liste de (path, score, details) triée EXIF
        tpl_by_id: dict des templates (chargé si None)
        window_size: taille de fenêtre glissante
        tag_context: dict optionnel {chemin_absolu: {tags...}} pour
                     prioriser les photos taggées ``hero``.

    Returns:
        Liste de (template_id, [photo_paths], is_hero) par page.
    """
    if tpl_by_id is None:
        tpl_by_id = load_templates()

    if window_size <= 0:
        raise ValueError(f"window_size must be > 0, got {window_size}")

    hero_ids, max_per_window, regular_ids = _derive_ids(tpl_by_id)

    pages: List[Tuple[str, List[str], bool]] = []
    hero_toggle = 0

    for start in range(0, len(photo_scores), window_size):
        window = photo_scores[start : start + window_size]
        if not window:
            break

        window_sorted = sorted(window, key=lambda x: x[1], reverse=True)

        # ── Hero (skip si fenêtre trop petite) ──
        hid = hero_ids[hero_toggle % len(hero_ids)]
        ht = tpl_by_id[hid]
        hn = sum(1 for z in ht["zones"] if z["type"] == "photo")

        if len(window_sorted) >= hn:
            # Trouver les hn meilleures photos éligibles

            # ── Priorité hero taggées ──
            # Les photos taggées ``hero`` dans tag_context sont prioritaires
            # pour le slot hero de leur fenêtre. Elles bypassent le check
            # d'éligibilité (hero tag = l'utilisateur a décidé).
            # Les photos taggées ``pas_hero`` sont EXCLUES des slots héro.
            hero_tagged = []
            if tag_context:
                for ws in window_sorted:
                    abs_path = str(Path(ws[0]).resolve())
                    tags = tag_context.get(abs_path, {})
                    if tags.get("hero") is True and not tags.get("pas_hero"):
                        hero_tagged.append(ws[0])

            # ── Exclure les pas_hero de la sélection héro ──
            pas_hero_skip = set()
            if tag_context:
                for ws in window_sorted:
                    abs_path = str(Path(ws[0]).resolve())
                    if is_pas_hero_tagged(Path(ws[0]), tag_context):
                        pas_hero_skip.add(ws[0])

            if hero_tagged:
                # Si plusieurs hero taggés, prendre la meilleure score
                hero_candidates = hero_tagged[:hn]
                if len(hero_candidates) < hn:
                    # Compléter avec les meilleures éligibles restantes
                    eligible = []
                    for ws in window_sorted:
                        if ws[0] not in hero_candidates and ws[0] not in pas_hero_skip and _is_hero_eligible(ws[0]):
                            eligible.append(ws[0])
                            if len(hero_candidates) + len(eligible) >= hn:
                                break
                    # Si pas assez d'éligibles, prendre les meilleures dispo
                    remaining_needed = hn - len(hero_candidates)
                    if len(eligible) >= remaining_needed:
                        hero_candidates.extend(eligible[:remaining_needed])
                    else:
                        for ws in window_sorted:
                            if ws[0] not in hero_candidates and ws[0] not in pas_hero_skip:
                                hero_candidates.append(ws[0])
                                if len(hero_candidates) >= hn:
                                    break
            else:
                hero_candidates = []
                for ws in window_sorted:
                    if ws[0] not in pas_hero_skip and _is_hero_eligible(ws[0]):
                        hero_candidates.append(ws[0])
                        if len(hero_candidates) >= hn:
                            break
                if len(hero_candidates) < hn:
                    # Pas assez d'éligibles → prendre les meilleures dispo
                    hero_candidates = [ws[0] for ws in window_sorted if ws[0] not in pas_hero_skip][:hn]
                    if len(hero_candidates) < hn:
                        hero_candidates = [ws[0] for ws in window_sorted[:hn]]
            pages.append((hid, hero_candidates, True))
            hero_toggle += 1
            used = set(hero_candidates)
            remaining = [p[0] for p in window if p[0] not in used]
        else:
            remaining = [p[0] for p in window]

        # ── Templates avec max_per_window ──
        tpl_sizes_all = {tid: sum(1 for z in tpl_by_id[tid]["zones"] if z["type"] == "photo")
                         for tid in tpl_by_id}

        ri = 0
        for tid, limit in sorted(max_per_window.items()):
            count = 0
            rn = tpl_sizes_all[tid]
            while count < limit and ri + rn <= len(remaining):
                pages.append((tid, remaining[ri:ri + rn], False))
                ri += rn
                count += 1

        # ── Templates standards (remplissage exact) ──
        after_special = remaining[ri:]
        if not after_special:
            continue

        # Si moins de photos que le plus petit template, on ignore (queue de fenêtre)
        min_size = min(tpl_sizes_all.values())
        if len(after_special) < min_size:
            continue

        order = list(regular_ids)
        random.shuffle(order)

        # Knapsack-like: trouver la meilleure combinaison pour ne rien perdre
        best_pages = _pack_photos(after_special, order, tpl_sizes_all)
        for tid, batch in best_pages:
            pages.append((tid, batch, False))

    return pages


def _pack_photos(
    photos: List[str],
    template_order: List[str],
    tpl_sizes: Dict[str, int],
) -> List[Tuple[str, List[str]]]:
    """Pack les photos restantes sans en perdre.

    Essaie l'ordre aléatoire jusqu'à ce que toutes les photos soient consommées.
    Si l'ordre échoue, réessaie avec un nouvel ordre (max 50 tentatives).
    En dernier recours, utilise le plus grand template qui rentre.
    """
    for _ in range(50):
        result: List[Tuple[str, List[str]]] = []
        idx = 0
        tpl_idx = 0
        while idx < len(photos):
            tid = template_order[tpl_idx % len(template_order)]
            rn = tpl_sizes[tid]
            if idx + rn <= len(photos):
                result.append((tid, photos[idx:idx + rn]))
                idx += rn
            else:
                remain = len(photos) - idx
                fitting = sorted(
                    [x for x in template_order if tpl_sizes[x] <= remain],
                    key=lambda x: tpl_sizes[x],
                    reverse=True,
                )
                if fitting:
                    fn = tpl_sizes[fitting[0]]
                    result.append((fitting[0], photos[idx:idx + fn]))
                    idx += fn
                else:
                    break  # cet ordre a échoué
            tpl_idx += 1

        if idx == len(photos):
            return result  # toutes les photos consommées ✓

        random.shuffle(template_order)

    # Fallback: greedy avec le plus grand template qui rentre (tous les templates)
    all_ids = list(tpl_sizes.keys())
    all_ids.sort(key=lambda x: tpl_sizes[x], reverse=True)
    result = []
    idx = 0
    while idx < len(photos):
        remain = len(photos) - idx
        fitting = [x for x in all_ids if tpl_sizes[x] <= remain]
        if fitting:
            fn = tpl_sizes[fitting[0]]
            result.append((fitting[0], photos[idx:idx + fn]))
            idx += fn
        else:
            # Reste < plus petit template → ignoré (queue de fenêtre)
            break
    return result
