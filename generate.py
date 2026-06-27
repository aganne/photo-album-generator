#!/usr/bin/env python3
"""
Générateur d'album photo PDF — Template Jinja2 → HTML → WeasyPrint → PDF

Usage:
  python3 generate.py                       # Génère avec les données par défaut
  python3 generate.py --photos ./photos     # Scoring IA auto + dispatch v3 fenêtre glissante
  python3 generate.py --photos ./photos --no-scoring  # Mode batch classique
  python3 generate.py --photos ./photos --scoring     # Forcer le scoring
  python3 generate.py --recits recits.json  # Fichier JSON des récits
  python3 generate.py --output mon_album.pdf
  python3 generate.py --html-only           # Génère seulement le HTML (pas de PDF)
  python3 generate.py --checklist           # Affiche la checklist avant génération
  python3 generate.py --no-smartcrop        # Désactiver le smart crop
  python3 generate.py --window-size 50      # Taille de fenêtre glissante (défaut: 40)
  python3 generate.py --palette              # Palette automatique via Colormind

Exemple:
  pip install -r requirements.txt
  python3 generate.py --html-only
"""

import os
import sys
import json
import random
import hashlib
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Ajouter le projet au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from album_generator.config import (
    PALETTE, FONTS, ALBUM, PAGE_STYLES,
    PAGE_WIDTH_MM, PAGE_HEIGHT_MM, BLEED_MM, SAFE_MARGIN_MM,
)
from album_generator.scoring import (
    PhotoScorer, PhotoDispatcher, extract_exif_date,
    sort_by_exif_date, group_photos_by_exif_month,
    export_scoring_report, find_micro_events,
)
from album_generator.colors import extract_palette, generate_dynamic_css, apply_palette_to_html
from album_generator.enhance import batch_enhance
from album_generator.print_risk import compute_print_penalty_file


# ── Chemins ─────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
TEMPLATES_DIR = PROJECT_DIR / "album_generator" / "templates"
STYLES_DIR = PROJECT_DIR / "styles"
PHOTOS_DIR = PROJECT_DIR / "photos"
OUTPUT_DIR = PROJECT_DIR / "output"
DATA_DIR = PROJECT_DIR / "data"
FONTS_DIR = PROJECT_DIR / "fonts"

# Mois en français
_MONTH_NAMES = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def load_styles():
    """Charge le CSS pour l'inliner dans le template."""
    css_path = STYLES_DIR / "album.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return ""


def load_recits(recits_path=None):
    """
    Charge les récits depuis un fichier JSON.
    Format attendu :
    [
        {
            "type": "heroique",
            "photo": "relative/path.jpg",
            "title": "Titre du récit",
            "date": "Janvier 2012",
            "text": "Texte du récit..."
        },
        ...
    ]
    """
    if recits_path:
        path = Path(recits_path)
    else:
        path = DATA_DIR / "recits.json"

    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def print_checklist(pages, photo_files):
    """Affiche la checklist pré-génération."""
    print("=" * 60)
    print("📋 CHECKLIST PRÉ-GÉNÉRATION")
    print("=" * 60)

    print(f"\n📸 Photos : {len(photo_files)} trouvées")
    for pf in sorted(photo_files)[:10]:
        print(f"   • {pf.name}")
    if len(photo_files) > 10:
        print(f"   ... et {len(photo_files) - 10} autres")

    print(f"\n📄 Pages : {len(pages)} (dont garde et crédits)")

    styles = {}
    for p in pages:
        s = p.get("style", "?")
        styles[s] = styles.get(s, 0) + 1
    print("\n🎨 Répartition :")
    for s, c in sorted(styles.items()):
        name = PAGE_STYLES.get(s, {}).get("name", s)
        print(f"   • {name} ({s}) : {c} page(s)")

    mod4 = len(pages) % 4
    if mod4 != 0:
        need = 4 - mod4
        print(f"\n⚠️  Nombre de pages ({len(pages)}) NON multiple de 4.")
        print(f"   → {need} page(s) blanche(s) seront ajoutées pour la reliure.")
    else:
        print(f"\n✅ Nombre de pages ({len(pages)}) multiple de 4 — OK reliure.")

    print(f"\n🩸 Fonds perdus (bleed) : {BLEED_MM} mm")
    print(f"   Marge de sécurité : {SAFE_MARGIN_MM} mm")
    print(f"   Format page : {PAGE_WIDTH_MM} × {PAGE_HEIGHT_MM} mm")

    ds = PALETTE.get("desaturation", 0)
    if ds > 0:
        print(f"\n🎨 Désaturation activée : -{ds}% (compensation impression)")
    else:
        print(f"\n🎨 Désaturation : désactivée")

    print(f"\n🔤 Polices :")
    for role, font in FONTS.items():
        status = "✓" if _font_available(font) else "✗ (non trouvée)"
        print(f"   • {role} : {font} {status}")

    print("\n" + "=" * 60)


def _font_available(font_name):
    """Vérifie si une police est disponible (fichiers dans fonts/)."""
    base_name = font_name.replace(' ', '')
    candidates_regular = [
        FONTS_DIR / f"{base_name}-Regular.ttf",
        FONTS_DIR / f"{base_name}-Regular.woff2",
        FONTS_DIR / f"{base_name}.ttf",
    ]
    has_regular = any(c.exists() for c in candidates_regular)
    has_bold = any([
        (FONTS_DIR / f"{base_name}-Bold.ttf").exists(),
        (FONTS_DIR / f"{base_name}-Bold.woff2").exists(),
    ])
    has_italic = any([
        (FONTS_DIR / f"{base_name}-Italic.ttf").exists(),
        (FONTS_DIR / f"{base_name}-Italic.woff2").exists(),
    ])
    return has_regular and has_bold and has_italic


def group_photos_by_month(photo_files, use_exif=True):
    """
    Trie les photos par mois (basé sur EXIF si disponible, sinon nom de fichier).
    """
    from collections import OrderedDict
    import re

    if use_exif:
        try:
            return group_photos_by_exif_month(photo_files)
        except Exception:
            pass

    months = OrderedDict()
    month_names = _MONTH_NAMES

    for fp in sorted(photo_files, key=lambda p: str(p)):
        if not fp.exists():
            continue
        stem = fp.stem
        month_idx = None

        m = re.search(r'(\d{4})(\d{2})(\d{2})', stem)
        if m:
            month_idx = int(m.group(2)) - 1
        else:
            try:
                mtime = os.path.getmtime(fp)
                dt = datetime.fromtimestamp(mtime)
                month_idx = dt.month - 1
            except OSError:
                month_idx = None

        if month_idx is not None and 0 <= month_idx < 12:
            month_name = month_names[month_idx]
            if month_name not in months:
                months[month_name] = []
            months[month_name].append(fp)
        else:
            if "Non classé" not in months:
                months["Non classé"] = []
            months["Non classé"].append(fp)

    return list(months.items())


def _build_photo_data(rel_path, photos_root, extra=None):
    """Construit un dict photo à partir d'un chemin relatif."""
    fp = photos_root / rel_path
    data = {"path": str(fp.resolve()), "label": rel_path}
    if extra:
        data.update(extra)
    return data if fp.exists() else None


def _make_photo_dict(path: str) -> Dict[str, str]:
    """Crée un dict photo standard à partir d'un chemin absolu."""
    return {
        "path": str(Path(path).resolve()),
        "label": Path(path).name,
    }


# ── Rectpack layout ─────────────────────────────────────────────────

def _layout_rectpack_collage(
    photo_batch: List[Tuple[str, float, Dict[str, float]]],
) -> List[Dict[str, Any]]:
    """Dispose un batch de 6-9 photos avec rectpack.

    Les photos mieux notées reçoivent des rectangles plus grands.
    Retourne une liste de dicts avec path, label, left, top, width, height
    (positions en pourcentage de la zone disponible).
    """
    from rectpack import newPacker, MaxRectsBaf

    packer = newPacker(rotation=False, pack_algo=MaxRectsBaf)

    # Extraire les scores pour pondérer les tailles
    paths = [p for p, _, _ in photo_batch]
    scores = [s for _, s, _ in photo_batch]
    min_s, max_s = min(scores), max(scores)

    # Dimensions de base en pourcentage du conteneur
    base_w = 26.0
    base_h = 26.0

    for idx, (path, score, details) in enumerate(photo_batch):
        # Score → facteur de taille : 0.7 (min) à 1.3 (max)
        if max_s > min_s:
            factor = 0.7 + 0.6 * (score - min_s) / (max_s - min_s)
        else:
            factor = 1.0

        w = int(base_w * factor)
        h = int(base_h * factor)
        packer.add_rect(w, h, rid=idx)

    # Packer dans un conteneur 100×100
    packer.add_bin(100, 100)
    packer.pack()

    # Indexer les résultats
    rects = {}
    for rect in packer.rect_list():
        # rect = (bin_id, x, y, w, h, rid)
        _, x, y, w, h, rid = rect
        rects[rid] = (x, y, w, h)

    # Construire la liste de photos avec positions
    photos = []
    for idx in range(len(photo_batch)):
        path, score, details = photo_batch[idx]
        if idx in rects:
            x, y, w, h = rects[idx]
            photos.append({
                "path": str(Path(path).resolve()),
                "label": Path(path).name,
                "left": x,
                "top": y,
                "width": w,
                "height": h,
            })
        else:
            # Fallback : la photo n'a pas pu être packée
            fw = int(base_w)
            fh = int(base_h)
            photos.append({
                "path": str(Path(path).resolve()),
                "label": Path(path).name,
                "left": 5 + (idx % 3) * (fw + 5),
                "top": 5 + (idx // 3) * (fh + 5),
                "width": fw,
                "height": fh,
            })

    return photos


# ── Nouveau dispatch v3 — Fenêtre glissante ─────────────────────────

def arrange_pages_from_scores_v3(
    photo_scores: List[Tuple[str, float, Dict[str, float]]],
    window_size: int = 40,
    collage_min: int = 6,
    collage_max: int = 9,
) -> List[Dict]:
    """Dispatch fenêtre glissante — remplace l'ancien 7/13/80.

    Les photos sont déjà triées chronologiquement (EXIF) par l'appelant.
    On les découpe en fenêtres de `window_size`. Dans chaque fenêtre :
      - Top 1 score  → Héroïque (pleine page)
      - 2-4 scores   → Quatuor (3 photos + mois/année)
      - Reste         → Collage rectpack (6-9 photos)

    Args:
        photo_scores: liste de (path, score, details) triée par EXIF
        window_size: taille de la fenêtre glissante
        collage_min: nombre minimum de photos par collage
        collage_max: nombre maximum de photos par collage

    Returns:
        Liste de dicts représentant chaque page.
    """
    pages: List[Dict] = []

    if window_size <= 0:
        raise ValueError("window_size must be > 0")

    # 1. Page de garde
    pages.append({"style": "titre", "data": {"album": ALBUM}})

    n = len(photo_scores)
    window_idx = 0

    for start in range(0, n, window_size):
        window = photo_scores[start:start + window_size]
        if not window:
            break

        # Trier la fenêtre par score décroissant
        window_sorted = sorted(window, key=lambda x: x[1], reverse=True)

        # ── Mois/Année du premier élément chronologique ──
        first_path = window[0][0]
        month_label = ""
        dt = extract_exif_date(first_path)
        if dt:
            month_label = f"{_MONTH_NAMES[dt.month - 1]} {dt.year}"
        else:
            month_label = f"Fenêtre {window_idx + 1}"

        # ── Héroïque : top 1 ──
        path, score, details = window_sorted[0]
        pages.append({
            "style": "heroique",
            "data": {"photo": _make_photo_dict(path)},
        })

        # ── Quatuor : positions 2-4 ──
        if len(window_sorted) >= 4:
            quatuor_photos = [
                _make_photo_dict(window_sorted[i][0])
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
            # 3 photos total → 1 héro + 2 dans une grille
            photos = [
                _make_photo_dict(window_sorted[i][0])
                for i in range(1, 3)
            ]
            pages.append({
                "style": "grille",
                "data": {"photos": photos, "title": month_label},
            })
        elif len(window_sorted) == 2:
            # 2 photos → 1 héro + 1 dans une autre héroïque
            path2, _, _ = window_sorted[1]
            pages.append({
                "style": "heroique",
                "data": {"photo": _make_photo_dict(path2)},
            })

        # ── Collages rectpack : reste (positions 5+) ──
        rest_start = 4
        rest = window_sorted[rest_start:]

        idx = 0
        while idx < len(rest):
            batch_size = min(collage_max, len(rest) - idx)
            if batch_size < collage_min:
                # Trop peu pour un collage → grille
                photos = [_make_photo_dict(rest[i][0]) for i in range(idx, len(rest))]
                if photos:
                    pages.append({
                        "style": "grille",
                        "data": {"photos": photos, "title": ""},
                    })
                break

            batch = rest[idx:idx + batch_size]
            collage_photos = _layout_rectpack_collage(batch)
            pages.append({
                "style": "collage_rectpack",
                "data": {"photos": collage_photos},
            })
            idx += batch_size

        window_idx += 1

    # 2. Page de crédits
    pages.append({"style": "credits", "data": {"album": ALBUM}})

    return pages


# ── Arrangement legacy ──────────────────────────────────────────────

def arrange_pages(photo_files, recits=None, photos_root=None):
    """
    Organise les pages de l'album à partir des photos et récits.
    (Mode classique, conservé pour compatibilité et --no-scoring)
    """
    if photos_root is None:
        photos_root = PHOTOS_DIR
    pages = []

    pages.append({"style": "titre", "data": {"album": ALBUM}})

    if recits:
        for entry in recits:
            rtype = entry.get("type", "grille")

            if rtype == "heroique":
                rel_path = entry.get("photo", "")
                photo_data = _build_photo_data(rel_path, photos_root)
                if photo_data:
                    pages.append({
                        "style": "heroique",
                        "data": {
                            "photo": photo_data,
                            "recit": {
                                "title": entry.get("title", ""),
                                "date": entry.get("date", ""),
                                "text": entry.get("text", ""),
                            },
                        },
                    })

            elif rtype == "grille":
                photos = []
                for rel_path in entry.get("photos", []):
                    pd = _build_photo_data(
                        rel_path, photos_root,
                        extra={"date": entry.get("date", "")}
                    )
                    if pd:
                        photos.append(pd)
                if photos:
                    pages.append({
                        "style": "grille",
                        "data": {"photos": photos, "title": entry.get("title", "")},
                    })

            elif rtype == "typographique":
                rel_path = entry.get("photo", "")
                photo_data = _build_photo_data(rel_path, photos_root) if rel_path else None
                pages.append({
                    "style": "typographique",
                    "data": {
                        "photo": photo_data,
                        "recit": {
                            "title": entry.get("title", ""),
                            "date": entry.get("date", ""),
                            "text": entry.get("text", ""),
                            "quote": entry.get("quote", False),
                        },
                    },
                })

            elif rtype == "hero_texte":
                rel_path = entry.get("photo", "")
                photo_data = _build_photo_data(rel_path, photos_root)
                if photo_data:
                    pages.append({
                        "style": "hero_texte",
                        "data": {
                            "photo": photo_data,
                            "recit": {
                                "title": entry.get("title", ""),
                                "date": entry.get("date", ""),
                                "text": entry.get("text", ""),
                            },
                        },
                    })

            elif rtype == "polaroid":
                photos = []
                for rel_path in entry.get("photos", []):
                    pd = _build_photo_data(rel_path, photos_root)
                    if pd:
                        photos.append(pd)
                if photos:
                    n = len(photos)
                    for i, photo in enumerate(photos):
                        col = i % 2
                        row = i // 2
                        n_rows = (n + 1) // 2
                        photo["top"] = 5 + row * (80 // max(n_rows, 1))
                        photo["left"] = 5 + col * 50
                        photo["width"] = 40
                        photo["rotation"] = random.uniform(-3, 3)
                        photo["zindex"] = i
                    pages.append({
                        "style": "polaroid",
                        "data": {"photos": photos},
                    })

            elif rtype == "video_extrait":
                frames = []
                for rel_path in entry.get("frames", []):
                    pd = _build_photo_data(rel_path, photos_root)
                    if pd:
                        frames.append(pd)
                if frames:
                    pages.append({
                        "style": "video_extrait",
                        "data": {
                            "frames": frames,
                            "video": {
                                "title": entry.get("video_title", "Extrait vidéo"),
                                "timecode": entry.get("timecode", "00:00:00"),
                                "quote": entry.get("quote", ""),
                                "meta": entry.get("meta", ""),
                            },
                        },
                    })

            elif rtype == "video_54":
                frames = []
                timecodes = entry.get("timecodes", [])
                raw_frames = entry.get("frames", [])
                if len(raw_frames) != 20:
                    print(f"  ⚠ video_54 entry has {len(raw_frames)} frames (expected 20) — skipping")
                    continue
                for i, rel_path in enumerate(raw_frames):
                    pd = _build_photo_data(rel_path, photos_root)
                    if pd:
                        tc = timecodes[i] if i < len(timecodes) else ""
                        pd["timecode"] = tc
                        frames.append(pd)
                if frames:
                    pages.append({
                        "style": "video_54",
                        "data": {
                            "frames": frames,
                            "video": {
                                "title": entry.get("video_title", "Extrait vidéo"),
                                "timecode": entry.get("timecode", "00:00:00"),
                                "quote": entry.get("quote", ""),
                                "meta": entry.get("meta", ""),
                            },
                        },
                    })

    else:
        # Mode auto sans scoring — groupement par mois
        months = group_photos_by_month(photo_files)
        for month_name, month_photos in months:
            photos_data = []
            for fp in month_photos:
                photos_data.append({
                    "path": str(fp.resolve()),
                    "label": fp.name,
                    "date": month_name[:3],
                })

            batch_size = 4
            for i in range(0, len(photos_data), batch_size):
                batch = photos_data[i:i + batch_size]
                n = len(batch)

                if n == 1:
                    pages.append({"style": "heroique", "data": {"photo": batch[0]}})
                elif n <= 4:
                    pages.append({"style": "grille", "data": {"photos": batch}})
                else:
                    if (i // batch_size) % 3 == 0:
                        pages.append({"style": "grille", "data": {"photos": batch}})
                    else:
                        pages.append({"style": "grille", "data": {"photos": batch[:4]}})

    pages.append({"style": "credits", "data": {"album": ALBUM}})
    return pages


# ── Pré-traitement photos : smart crop + rotation EXIF ──────────────

def preprocess_scored_photos(
    photo_scores: List[Tuple[str, float, Dict[str, float]]],
    crop_dir: Optional[Path] = None,
) -> List[Tuple[str, float, Dict[str, float]]]:
    """Applique smart_crop et fix_exif_rotation aux photos notées.

    La rotation EXIF écrit des copies pivotées dans un cache,
    sans jamais modifier les fichiers source originaux.

    Args:
        photo_scores: liste de (path, score, details)
        crop_dir: dossier où sauvegarder crops et rotations
                  (None = rotation seulement, dans un cache temporaire)

    Returns:
        Nouvelle liste avec les chemins mis à jour après crop/rotation.
    """
    result = []
    rotated = 0
    cropped = 0

    # Répertoire cache pour la rotation EXIF
    rotation_dir = crop_dir if crop_dir is not None else OUTPUT_DIR / ".exif_cache"

    for path, score, details in photo_scores:
        current_path = path

        # 1. Rotation EXIF (copie dans cache, ne modifie PAS l'original)
        rotated_path = PhotoScorer.fix_exif_rotation(current_path, rotation_dir)
        if rotated_path is not None:
            # Invalider le cache visages : les coordonnées de l'image
            # originale ne sont plus valides après rotation.
            cache_key = str(Path(path).resolve())
            PhotoScorer._face_cache.pop(cache_key, None)
            current_path = rotated_path
            rotated += 1

        # 2. Smart crop (si activé)
        if crop_dir is not None:
            # Préserver la date EXIF avant crop (le fichier croppé
            # perd ses métadonnées, ce qui casse le groupement par mois).
            original_date = extract_exif_date(current_path)
            if original_date and "original_exif_date" not in details:
                details["original_exif_date"] = original_date.isoformat()

            crop_dir.mkdir(parents=True, exist_ok=True)
            # Inclure un hash du chemin complet pour éviter les
            # collisions entre fichiers de même nom dans des dossiers différents.
            path_hash = hashlib.sha256(
                str(Path(current_path).resolve()).encode()
            ).hexdigest()[:12]
            crop_out = str(
                crop_dir / f"crop_{path_hash}_{Path(current_path).name}"
            )
            if PhotoScorer.smart_crop(current_path, crop_out):
                current_path = crop_out
                cropped += 1

        result.append((current_path, score, details))

    if rotated > 0:
        print(f"   🔄 {rotated} photos pivotées (EXIF)")
    if cropped > 0:
        print(f"   ✂️  {cropped} photos recadrées (smart crop)")

    return result


# ── Ancien dispatch 7/13/80 (conservé pour compatibilité) ──────────

def arrange_pages_from_scores(
    dispatch: Dict[str, List[Tuple[str, float, Dict[str, float]]]],
    photos_root: Path,
    recits: Optional[List[Dict]] = None,
    collage_every: int = 4,
) -> List[Dict]:
    """Organise les pages à partir des scores et du dispatch 7/13/80."""
    pages: List[Dict] = []

    pages.append({"style": "titre", "data": {"album": ALBUM}})

    for path, score, details in dispatch.get("heroique", []):
        photo_data = _build_photo_data(str(path), Path("/"))
        if photo_data is None:
            photo_data = {"path": str(Path(path).resolve()), "label": Path(path).name}
        pages.append({"style": "heroique", "data": {"photo": photo_data}})

    duo_photos = dispatch.get("duo", [])
    for i in range(0, len(duo_photos), 2):
        batch = duo_photos[i:i + 2]
        photos = []
        for path, score, details in batch:
            pd = _build_photo_data(str(path), Path("/"))
            if pd is None:
                pd = {"path": str(Path(path).resolve()), "label": Path(path).name}
            photos.append(pd)
        if photos:
            pages.append({"style": "grille", "data": {"photos": photos, "title": ""}})

    grille_photos = dispatch.get("grille", [])
    batch_size = 6
    grid_counter = 0

    for i in range(0, len(grille_photos), batch_size):
        batch = grille_photos[i:i + batch_size]
        photos = []
        for path, score, details in batch:
            pd = _build_photo_data(str(path), Path("/"))
            if pd is None:
                pd = {"path": str(Path(path).resolve()), "label": Path(path).name}
            photos.append(pd)

        if not photos:
            continue

        if collage_every > 0 and grid_counter > 0 and grid_counter % collage_every == 0 and len(photos) >= 4:
            pages.append({"style": "grille", "data": {"photos": photos, "title": ""}})
        else:
            pages.append({"style": "grille", "data": {"photos": photos, "title": ""}})
        grid_counter += 1

    if recits:
        for entry in recits:
            rtype = entry.get("type", "")
            if rtype == "typographique":
                rel_path = entry.get("photo", "")
                photo_data = _build_photo_data(rel_path, photos_root) if rel_path else None
                pages.append({
                    "style": "typographique",
                    "data": {
                        "photo": photo_data,
                        "recit": {
                            "title": entry.get("title", ""),
                            "date": entry.get("date", ""),
                            "text": entry.get("text", ""),
                            "quote": entry.get("quote", False),
                        },
                    },
                })

    pages.append({"style": "credits", "data": {"album": ALBUM}})
    return pages


# ── Utilitaires PDF / HTML ──────────────────────────────────────────

def ensure_multiple_of_4(pages):
    """Ajoute des pages blanches pour que le total soit multiple de 4."""
    n = len(pages)
    remainder = n % 4
    if remainder == 0:
        return pages

    needed = 4 - remainder
    for _ in range(needed):
        pages.insert(-1, {"style": "blank", "data": {}})

    return pages


def desaturate_photo(image_path, amount=10):
    """Désature une photo de `amount` pourcents."""
    if amount <= 0:
        return image_path

    from PIL import Image, ImageEnhance

    try:
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        factor = 1.0 - (amount / 100.0)
        enhancer = ImageEnhance.Color(img)
        img_desat = enhancer.enhance(factor)

        cache_dir = OUTPUT_DIR / ".desat_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_name = Path(image_path).stem + f"_desat{amount}.jpg"
        cache_path = cache_dir / cache_name
        img_desat.save(str(cache_path), "JPEG", quality=92)

        return str(cache_path)
    except (OSError, IOError, ValueError, SyntaxError) as e:
        print(f"   ⚠️  Désaturation échouée pour {image_path}: {e}")
        return image_path


def preprocess_photos(pages):
    """Applique la désaturation sur toutes les photos référencées."""
    ds_amount = PALETTE.get("desaturation", 0)
    if ds_amount <= 0:
        return

    print(f"🎨 Désaturation -{ds_amount}% en cours...")
    count = 0

    for page in pages:
        data = page.get("data", {})

        if "photo" in data and data["photo"] and "path" in data["photo"]:
            data["photo"]["path"] = desaturate_photo(data["photo"]["path"], ds_amount)
            count += 1

        if "photos" in data:
            for p in data["photos"]:
                if "path" in p:
                    p["path"] = desaturate_photo(p["path"], ds_amount)
                    count += 1

        if "frames" in data:
            for f in data["frames"]:
                if "path" in f:
                    f["path"] = desaturate_photo(f["path"], ds_amount)
                    count += 1

    print(f"   ✓ {count} photos traitées")


def generate_html(pages, css_override=None):
    """Génère le HTML complet à partir des pages.

    Args:
        pages: liste de dicts de pages.
        css_override: CSS à utiliser à la place de album.css (optionnel,
                      pour la palette dynamique Colormind).
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.globals["album"] = ALBUM
    env.globals["album_css"] = css_override if css_override else load_styles()

    template = env.get_template("base.html")

    page_list = []
    for i, page in enumerate(pages):
        page_list.append({
            "style": page["style"],
            "page_num": i + 1,
            **page["data"],
        })

    html = template.render(pages=page_list)
    return html


def generate_pdf(html, output_path):
    """Convertit le HTML en PDF via WeasyPrint."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = HTML(string=html, base_url=str(PROJECT_DIR)).render()
    doc.write_pdf(str(output_path))

    print(f"✅ PDF généré : {output_path}")
    print(f"   Taille : {output_path.stat().st_size / 1024 / 1024:.1f} Mo")
    print(f"   Pages  : {len(doc.pages)}")


def scan_photos(photos_dir=None):
    """Scanne le dossier photos pour trouver les images."""
    if photos_dir is None:
        photos_dir = PHOTOS_DIR
    else:
        photos_dir = Path(photos_dir)

    extensions = {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov'}
    photos = sorted(
        p for p in photos_dir.rglob("*")
        if p.suffix.lower() in extensions and not p.name.startswith('.')
    )
    return photos


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Générateur d'album photo PDF")
    parser.add_argument("--photos", "-p", help="Dossier contenant les photos")
    parser.add_argument("--recits", "-r", help="Fichier JSON des récits")
    parser.add_argument("--output", "-o", default=str(OUTPUT_DIR / "album.pdf"),
                        help="Chemin du PDF de sortie")
    parser.add_argument("--html-only", action="store_true",
                        help="Générer seulement le HTML (pas de PDF)")
    parser.add_argument("--checklist", action="store_true",
                        help="Afficher la checklist pré-génération sans générer")
    parser.add_argument("--scoring", action="store_true", default=None,
                        help="Activer le scoring IA des photos (auto si --photos)")
    parser.add_argument("--no-scoring", action="store_true",
                        help="Désactiver le scoring IA (mode batch classique)")
    parser.add_argument("--no-smartcrop", action="store_true",
                        help="Désactiver le smart crop")
    parser.add_argument("--window-size", type=int, default=40,
                        help="Taille de la fenêtre glissante (défaut: 40)")
    parser.add_argument("--palette", action="store_true",
                        help="Extraire la palette automatique via Colormind (sinon palette configurée)")
    parser.add_argument("--enhance", choices=["default", "strong"], nargs="?",
                        const="default", default=None,
                        help="Retouche photo automatique avant scoring (default|strong)")
    args = parser.parse_args()

    # Scanner les photos
    photo_files = scan_photos(args.photos)
    print(f"📸 Photos trouvées : {len(photo_files)}")

    if not photo_files:
        print("⚠️  Aucune photo trouvée. Utilisation de photos mock pour test.")
        create_mock_photos()
        photo_files = scan_photos()

    # Déterminer si on active le scoring
    use_scoring = args.scoring
    if use_scoring is None:
        use_scoring = bool(args.photos) and not args.no_scoring

    # Charger les récits
    if args.recits:
        recits = load_recits(args.recits)
    elif args.photos:
        recits = None
    else:
        recits = load_recits()

    # Déterminer la racine des photos
    photos_root = Path(args.photos).resolve() if args.photos else PHOTOS_DIR

    # Scoring IA + nouveau dispatch v3
    scoring_report_path = None
    photo_scores = []  # Initialisé pour --palette sans scoring
    if use_scoring:
        print("🧠 Scoring IA des photos en cours...")
        scorer = PhotoScorer()

        # Trier par EXIF pour l'ordre chronologique
        photo_files = sort_by_exif_date(photo_files)

        # Scorer chaque photo en parallèle
        photo_scores = []
        max_workers = min(os.cpu_count() or 4, len(photo_files), 8)

        def _score_one(fp: Path):
            try:
                total, details = scorer.score(str(fp))
                return (str(fp), total, details)
            except Exception as exc:
                print(f"   ⚠️  Score échoué pour {fp.name}: {exc}")
                # Donner un score neutre au lieu de perdre la photo
                return (str(fp), 0.5, {})

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_score_one, fp): fp for fp in photo_files}
            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                if result is not None:
                    photo_scores.append(result)
                if (i + 1) % 20 == 0:
                    print(f"   ... {i + 1}/{len(photo_files)} photos notées")

        # Ré-ordonner par ordre EXIF (l'ordre de complétion parallèle est arbitraire)
        exif_order = {str(fp): idx for idx, fp in enumerate(photo_files)}
        photo_scores.sort(key=lambda ps: exif_order.get(ps[0], 9999))

        print(f"   ✓ {len(photo_scores)}/{len(photo_files)} photos notées")

        # ── Retouche photo --enhance ──
        if args.enhance:
            print(f"🖼️  Retouche photo activée (mode: {args.enhance})...")
            enhanced_dir = OUTPUT_DIR / "enhanced"
            enhanced_dir.mkdir(parents=True, exist_ok=True)

            # Extraire les chemins originaux (avant rotation/crop)
            original_paths = [ps[0] for ps in photo_scores]

            enhanced_paths = batch_enhance(
                original_paths, enhanced_dir,
                level=args.enhance,
                max_workers=min(os.cpu_count() or 4, 8),
                max_dim=1024,  # 1024 px suffisant pour le scoring
            )
            print(f"   ✓ {len(enhanced_paths)} photos retouchées")

            # Re-scorer les photos retouchées
            enhanced_scores: List[Tuple[str, float, Dict[str, float]]] = []
            enhanced_by_name = {
                Path(p).name: p for p in enhanced_paths
            }

            # Mapping original → enhanced pour le print_risk
            orig_by_name = {
                Path(ps[0]).name: ps for ps in photo_scores
            }

            for ps in photo_scores:
                orig_path = ps[0]
                fname = Path(orig_path).name
                enh_path = enhanced_by_name.get(fname)
                if enh_path is None:
                    # Fallback : garder l'original
                    enhanced_scores.append(ps)
                    continue

                try:
                    enh_total, enh_details = scorer.score(enh_path)
                except Exception as exc:
                    print(f"   ⚠️  Re-score échoué pour {fname}: {exc}")
                    enhanced_scores.append(ps)
                    continue

                # Calculer la pénalité d'impression
                try:
                    penalty = compute_print_penalty_file(orig_path, enh_path)
                except Exception:
                    penalty = 0.0

                adjusted = enh_total * (1.0 - penalty)

                # Ajouter les métadonnées d'enhancement
                enh_details["enhanced"] = True
                enh_details["enhance_level"] = args.enhance
                enh_details["print_risk"] = round(penalty, 4)
                enh_details["score_raw"] = round(enh_total, 4)
                enh_details["score_adjusted"] = round(adjusted, 4)

                enhanced_scores.append((enh_path, adjusted, enh_details))

            # Remplacer les scores
            photo_scores = enhanced_scores
            print(f"   📊 {len(photo_scores)} photos re-notées avec pénalité print_risk")

        # ── Smart crop + rotation EXIF ──
        if not args.no_smartcrop:
            crop_dir = OUTPUT_DIR / ".crop_cache"
            photo_scores = preprocess_scored_photos(photo_scores, crop_dir=crop_dir)
        else:
            # Appliquer seulement la rotation EXIF
            photo_scores = preprocess_scored_photos(photo_scores, crop_dir=None)

        # ── Nouveau dispatch v3 : fenêtre glissante ──
        pages = arrange_pages_from_scores_v3(
            photo_scores,
            window_size=args.window_size,
        )
        print(f"   📊 Dispatch v3 (fenêtre {args.window_size})")

        # Rapport JSON — reconstruire le dispatch depuis les pages v3
        scoring_report_path = OUTPUT_DIR / "scoring_report.json"
        scoring_report_path.parent.mkdir(parents=True, exist_ok=True)
        # Index résolu : chemin absolu → (path, score, details)
        score_by_path: Dict[str, Tuple] = {}
        for ps in photo_scores:
            score_by_path[str(Path(ps[0]).resolve())] = ps
        dispatch: Dict[str, List] = {"heroique": [], "duo": [], "grille": []}
        for page in pages:
            style = page.get("style", "")
            if style in ("titre", "credits"):
                continue
            photos_in_page: List[Dict] = []
            if style == "heroique":
                photos_in_page = [page["data"]["photo"]]
            else:
                photos_in_page = page["data"].get("photos", [])
            for photo in photos_in_page:
                resolved = str(Path(photo["path"]).resolve())
                if resolved in score_by_path:
                    if style == "heroique":
                        dispatch["heroique"].append(score_by_path[resolved])
                    elif style == "grille":
                        dispatch["grille"].append(score_by_path[resolved])
                    else:
                        # quatuor, collage_rectpack → duo
                        dispatch["duo"].append(score_by_path[resolved])
        export_scoring_report(photo_scores, dispatch, scoring_report_path)
        print(f"   📋 Rapport : {scoring_report_path}")

    else:
        # Mode classique (sans scoring)
        pages = arrange_pages(photo_files, recits, photos_root=photos_root)

    # ── Palette Colormind automatique ──
    css_override = None
    dynamic_palette = None
    if args.palette:
        if not use_scoring:
            print("   ⚠️  --palette nécessite le scoring (--scoring). Ignoré.")
        else:
            print("🎨 Palette Colormind — extraction depuis les meilleures photos...")
            dynamic_palette = extract_palette(photo_scores, n_samples=5)
            css_override = generate_dynamic_css(dynamic_palette)
            print(f"   ✓ Palette générée : {len(dynamic_palette)} couleurs")
    # ═══════════════════════════════════════════════════════════════

    # Stats
    styles = {}
    for p in pages:
        s = p.get("style", "?")
        styles[s] = styles.get(s, 0) + 1
    print(f"   🎨 Répartition : {dict(sorted(styles.items()))}")
    print(f"📄 Pages à générer : {len(pages)}")

    # Checklist
    if args.checklist:
        print_checklist(pages, photo_files)
        print("\n✨ Checklist terminée. Relancez sans --checklist pour générer.")
        return

    # Forcer multiple de 4 pour la reliure
    pages = ensure_multiple_of_4(pages)
    if len(pages) % 4 == 0:
        print(f"📚 Pages après reliure (multiple de 4) : {len(pages)}")

    # Prétraitement photo (désaturation)
    preprocess_photos(pages)

    # Générer le HTML
    html = generate_html(pages, css_override=css_override)

    # Appliquer la palette aux styles inline si dynamique
    if dynamic_palette:
        html = apply_palette_to_html(html, dynamic_palette)

    # Sauvegarder le HTML intermédiaire
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUTPUT_DIR / "album.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"📝 HTML sauvegardé : {html_path}")

    # Générer le PDF
    if not args.html_only:
        generate_pdf(html, args.output)

    print("\n✨ Album généré avec succès !")


def create_mock_photos(count=12):
    """Crée des photos mock pour les tests (placeholders colorés)."""
    from PIL import Image, ImageDraw, ImageFont

    mock_dir = PHOTOS_DIR / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)

    colors = ["#c49a5a", "#e8cfa0", "#d4b888", "#8a6a3a", "#f5ede0", "#fefcf5"]

    for i in range(count):
        img = Image.new("RGB", (800, 600), colors[i % len(colors)])
        draw = ImageDraw.Draw(img)
        draw.text((400, 300), f"Photo {i+1}", fill="#3a2a1a", anchor="mm")
        path = mock_dir / f"mock_{i+1:02d}.jpg"
        img.save(str(path), "JPEG", quality=85)

    print(f"   {count} photos mock créées dans {mock_dir}")


if __name__ == "__main__":
    main()
