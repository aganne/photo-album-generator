#!/usr/bin/env python3
"""
Générateur d'album photo PDF — Template Jinja2 → HTML → WeasyPrint → PDF

Usage:
  python3 generate.py                       # Génère avec les données par défaut
  python3 generate.py --photos ./photos     # Scoring IA auto + dispatch 7/13/80
  python3 generate.py --photos ./photos --no-scoring  # Mode batch classique
  python3 generate.py --photos ./photos --scoring     # Forcer le scoring
  python3 generate.py --recits recits.json  # Fichier JSON des récits
  python3 generate.py --output mon_album.pdf
  python3 generate.py --html-only           # Génère seulement le HTML (pas de PDF)
  python3 generate.py --checklist           # Affiche la checklist avant génération

Exemple:
  pip install -r requirements.txt
  python3 generate.py --html-only
"""

import os
import sys
import json
import random
import argparse
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


# ── Chemins ─────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
TEMPLATES_DIR = PROJECT_DIR / "album_generator" / "templates"
STYLES_DIR = PROJECT_DIR / "styles"
PHOTOS_DIR = PROJECT_DIR / "photos"
OUTPUT_DIR = PROJECT_DIR / "output"
DATA_DIR = PROJECT_DIR / "data"
FONTS_DIR = PROJECT_DIR / "fonts"


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
        {
            "type": "grille",
            "photos": ["path1.jpg", "path2.jpg", ...]
        },
        {
            "type": "video_54",
            "video_title": "Premiers pas",
            "frames": ["frame1.jpg", ...],
            "timecodes": ["00:01:23", ...],
            "quote": "...",
            "meta": "..."
        }
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

    # 1. Photos
    print(f"\n📸 Photos : {len(photo_files)} trouvées")
    for pf in sorted(photo_files)[:10]:
        print(f"   • {pf.name}")
    if len(photo_files) > 10:
        print(f"   ... et {len(photo_files) - 10} autres")

    # 2. Pages
    print(f"\n📄 Pages : {len(pages)} (dont garde et crédits)")

    # Styles utilisés
    styles = {}
    for p in pages:
        s = p.get("style", "?")
        styles[s] = styles.get(s, 0) + 1
    print("\n🎨 Répartition :")
    for s, c in sorted(styles.items()):
        name = PAGE_STYLES.get(s, {}).get("name", s)
        print(f"   • {name} ({s}) : {c} page(s)")

    # 3. Multiple de 4
    mod4 = len(pages) % 4
    if mod4 != 0:
        need = 4 - mod4
        print(f"\n⚠️  Nombre de pages ({len(pages)}) NON multiple de 4.")
        print(f"   → {need} page(s) blanche(s) seront ajoutées pour la reliure.")
    else:
        print(f"\n✅ Nombre de pages ({len(pages)}) multiple de 4 — OK reliure.")

    # 4. Bleed
    print(f"\n🩸 Fonds perdus (bleed) : {BLEED_MM} mm")
    print(f"   Marge de sécurité : {SAFE_MARGIN_MM} mm")
    print(f"   Format page : {PAGE_WIDTH_MM} × {PAGE_HEIGHT_MM} mm")

    # 5. Désaturation
    ds = PALETTE.get("desaturation", 0)
    if ds > 0:
        print(f"\n🎨 Désaturation activée : -{ds}% (compensation impression)")
    else:
        print(f"\n🎨 Désaturation : désactivée")

    # 6. Polices
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

    Retourne une liste de (mois, [photos]) triée chronologiquement.

    On essaie d'extraire la date depuis EXIF en priorité.
    Format fallback iPhone: IMG_YYYYMMDD_HHMMSS.jpg
    Format fallback appareil: DSC_1234.jpg (modification time)
    """
    from collections import OrderedDict
    import re

    # Si EXIF disponible, l'utiliser en priorité
    if use_exif:
        try:
            return group_photos_by_exif_month(photo_files)
        except Exception:
            pass  # fallback au nom de fichier

    months = OrderedDict()
    month_names = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ]

    for fp in sorted(photo_files, key=lambda p: str(p)):
        if not fp.exists():
            continue
        stem = fp.stem
        month_idx = None

        # IMG_YYYYMMDD pattern (iPhone)
        m = re.search(r'(\\d{4})(\\d{2})(\\d{2})', stem)
        if m:
            month_idx = int(m.group(2)) - 1  # 0-based
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


def arrange_pages(photo_files, recits=None, photos_root=None):
    """
    Organise les pages de l'album à partir des photos et récits.

    Types supportés :
      - heroique      : 1 photo pleine page (ouverture, moments forts)
      - duo           : 2 photos côte à côte
      - grille        : 3-6 photos structurées
      - collage       : 5+ photos disposition organique
      - typographique : texte + 0-1 photo (pause, citation)
      - hero_texte    : legacy — photo + texte narratif
      - polaroid      : legacy — photos éparpillées
      - video_extrait : legacy — pellicule vidéo
      - video_54      : grille 5×4 style pellicule sombre

    Args:
        photo_files: liste de Paths vers les photos scannées
        recits: liste de récits formatés (ou None pour mode auto)
        photos_root: dossier racine pour résoudre les chemins relatifs
                     des photos dans les récits (défaut: PHOTOS_DIR)

    Returns: liste de dicts représentant chaque page.
    """
    if photos_root is None:
        photos_root = PHOTOS_DIR
    pages = []

    # 1. Page de garde
    pages.append({"style": "titre", "data": {"album": ALBUM}})

    # 2. Si on a des récits, les intégrer selon leur type
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

            elif rtype == "duo":
                photos = []
                for rel_path in entry.get("photos", [])[:2]:
                    pd = _build_photo_data(rel_path, photos_root)
                    if pd:
                        photos.append(pd)
                if photos:
                    pages.append({
                        "style": "duo",
                        "data": {
                            "photos": photos,
                            "title": entry.get("title", ""),
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

            elif rtype == "collage":
                photos = []
                for rel_path in entry.get("photos", []):
                    pd = _build_photo_data(rel_path, photos_root)
                    if pd:
                        photos.append(pd)
                if len(photos) >= 5:
                    pages.append({
                        "style": "collage",
                        "data": {
                            "photos": photos,
                            "title": entry.get("title", ""),
                        },
                    })
                elif photos:
                    # Pas assez pour un collage → grille
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
                # Validate exactly 20 frames for 5x4 grid layout
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

    # 3. Si pas de récits, générer automatiquement par mois
    else:
        months = group_photos_by_month(photo_files)
        for month_name, month_photos in months:
            photos_data = []
            for fp in month_photos:
                photos_data.append({
                    "path": str(fp.resolve()),
                    "label": fp.name,
                    "date": month_name[:3],
                })

            # Répartir en pages avec variété
            batch_size = 4
            for i in range(0, len(photos_data), batch_size):
                batch = photos_data[i:i + batch_size]
                n = len(batch)

                if n == 1:
                    pages.append({"style": "heroique", "data": {"photo": batch[0]}})
                elif n == 2:
                    pages.append({"style": "duo", "data": {"photos": batch}})
                elif n <= 4:
                    pages.append({"style": "grille", "data": {"photos": batch}})
                else:
                    # Varier entre grille et collage
                    if (i // batch_size) % 3 == 0:
                        pages.append({"style": "grille", "data": {"photos": batch}})
                    elif (i // batch_size) % 3 == 1:
                        pages.append({"style": "collage", "data": {"photos": batch}})
                    else:
                        pages.append({"style": "duo", "data": {"photos": batch[:2]}})

    # 4. Page de crédits
    pages.append({"style": "credits", "data": {"album": ALBUM}})

    return pages


def arrange_pages_from_scores(
    dispatch: Dict[str, List[Tuple[str, float, Dict[str, float]]]],
    photos_root: Path,
    recits: Optional[List[Dict]] = None,
    collage_every: int = 4,
) -> List[Dict]:
    """Organise les pages à partir des scores et du dispatch 7/13/80.

    Args:
        dispatch: résultat de PhotoDispatcher.dispatch() —
                  dict avec clés "heroique", "duo", "grille".
        photos_root: dossier racine pour résoudre les chemins.
        recits: récits optionnels (pour les pages typographiques intercalées).
        collage_every: insérer une page collage toutes les N pages grille.

    Returns:
        Liste de dicts représentant chaque page.
    """
    pages: List[Dict] = []

    # 1. Page de garde
    pages.append({"style": "titre", "data": {"album": ALBUM}})

    # 2. Pages héroïques (top 7%)
    for path, score, details in dispatch.get("heroique", []):
        photo_data = _build_photo_data(str(path), Path("/"))
        if photo_data is None:
            photo_data = {
                "path": str(Path(path).resolve()),
                "label": Path(path).name,
            }
        pages.append({
            "style": "heroique",
            "data": {"photo": photo_data},
        })

    # 3. Pages duo (7-20%)
    duo_photos = dispatch.get("duo", [])
    for i in range(0, len(duo_photos), 2):
        batch = duo_photos[i:i + 2]
        photos = []
        for path, score, details in batch:
            pd = _build_photo_data(str(path), Path("/"))
            if pd is None:
                pd = {
                    "path": str(Path(path).resolve()),
                    "label": Path(path).name,
                }
            photos.append(pd)
        if photos:
            pages.append({
                "style": "duo",
                "data": {"photos": photos, "title": ""},
            })

    # 4. Pages grille (80% restant) + collages périodiques
    grille_photos = dispatch.get("grille", [])
    batch_size = 6  # 6 photos par page en grille
    grid_counter = 0

    for i in range(0, len(grille_photos), batch_size):
        batch = grille_photos[i:i + batch_size]
        photos = []
        for path, score, details in batch:
            pd = _build_photo_data(str(path), Path("/"))
            if pd is None:
                pd = {
                    "path": str(Path(path).resolve()),
                    "label": Path(path).name,
                }
            photos.append(pd)

        if not photos:
            continue

        # Insérer un collage toutes les `collage_every` pages grille
        if collage_every > 0 and grid_counter > 0 and grid_counter % collage_every == 0 and len(photos) >= 4:
            pages.append({
                "style": "collage",
                "data": {"photos": photos, "title": ""},
            })
        else:
            pages.append({
                "style": "grille",
                "data": {"photos": photos, "title": ""},
            })
        grid_counter += 1

    # 5. Pages typographiques si des récits sont fournis
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

    # 6. Page de crédits
    pages.append({"style": "credits", "data": {"album": ALBUM}})

    return pages


def ensure_multiple_of_4(pages):
    """
    Ajoute des pages blanches pour que le nombre total de pages
    soit un multiple de 4 (contrainte de reliure).
    """
    n = len(pages)
    remainder = n % 4
    if remainder == 0:
        return pages

    needed = 4 - remainder
    for _ in range(needed):
        pages.insert(-1, {"style": "blank", "data": {}})  # avant les crédits

    return pages


def desaturate_photo(image_path, amount=10):
    """
    Désature une photo de `amount` pourcents (0 = pas de changement, 100 = N&B).
    Appliquée avant l'injection HTML pour compenser la sursaturation à l'impression.

    Args:
        image_path: chemin absolu vers le fichier image
        amount: pourcentage de désaturation (0-100)

    Returns:
        Chemin vers l'image (potentiellement modifiée en place ou copie)
    """
    if amount <= 0:
        return image_path

    from PIL import Image, ImageEnhance

    try:
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # amount=10 → saturation réduite de 10% → facteur 0.9
        factor = 1.0 - (amount / 100.0)
        enhancer = ImageEnhance.Color(img)
        img_desat = enhancer.enhance(factor)

        # Sauvegarder dans un cache pour ne pas modifier l'original
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
    """
    Applique la désaturation sur toutes les photos référencées dans les pages.
    Modifie les chemins des photos en place.
    """
    ds_amount = PALETTE.get("desaturation", 0)
    if ds_amount <= 0:
        return

    print(f"🎨 Désaturation -{ds_amount}% en cours...")
    count = 0

    for page in pages:
        data = page.get("data", {})

        # Cas 1: page.photo (heroique, typographique, hero_texte)
        if "photo" in data and data["photo"] and "path" in data["photo"]:
            data["photo"]["path"] = desaturate_photo(data["photo"]["path"], ds_amount)
            count += 1

        # Cas 2: page.photos (duo, grille, collage, polaroid)
        if "photos" in data:
            for p in data["photos"]:
                if "path" in p:
                    p["path"] = desaturate_photo(p["path"], ds_amount)
                    count += 1

        # Cas 3: page.frames (video_extrait, video_54)
        if "frames" in data:
            for f in data["frames"]:
                if "path" in f:
                    f["path"] = desaturate_photo(f["path"], ds_amount)
                    count += 1

    print(f"   ✓ {count} photos traitées")


def generate_html(pages):
    """Génère le HTML complet à partir des pages."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.globals["album"] = ALBUM
    env.globals["album_css"] = load_styles()

    template = env.get_template("base.html")

    # Préparer les pages avec numérotation
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
    args = parser.parse_args()

    # Scanner les photos
    photo_files = scan_photos(args.photos)
    print(f"📸 Photos trouvées : {len(photo_files)}")

    if not photo_files:
        print("⚠️  Aucune photo trouvée. Utilisation de photos mock pour test.")
        create_mock_photos()
        photo_files = scan_photos()

    # Déterminer si on active le scoring
    # --scoring explicite OU --photos sans --no-scoring → scoring auto
    use_scoring = args.scoring
    if use_scoring is None:
        use_scoring = bool(args.photos) and not args.no_scoring

    # Charger les récits
    if args.recits:
        recits = load_recits(args.recits)
    elif args.photos:
        recits = None  # mode auto : arrange_pages utilise photo_files
    else:
        recits = load_recits()  # mode démo : récits par défaut

    # Déterminer la racine des photos (utilisateur ou projet)
    photos_root = Path(args.photos).resolve() if args.photos else PHOTOS_DIR

    # Scoring IA + dispatch intelligent
    scoring_report_path = None
    if use_scoring:
        print("🧠 Scoring IA des photos en cours...")
        scorer = PhotoScorer()
        dispatcher = PhotoDispatcher()

        # Trier par EXIF pour l'ordre chronologique
        photo_files = sort_by_exif_date(photo_files)

        # Scorer chaque photo
        photo_scores = []
        for i, fp in enumerate(photo_files):
            try:
                total, details = scorer.score(str(fp))
                photo_scores.append((str(fp), total, details))
            except Exception as exc:
                print(f"   ⚠️  Score échoué pour {fp.name}: {exc}")
            if (i + 1) % 20 == 0:
                print(f"   ... {i + 1}/{len(photo_files)} photos notées")

        print(f"   ✓ {len(photo_scores)}/{len(photo_files)} photos notées")

        # Dispatch 7/13/80
        dispatch = dispatcher.dispatch(photo_scores)
        n_h = len(dispatch["heroique"])
        n_d = len(dispatch["duo"])
        n_g = len(dispatch["grille"])
        print(f"   📊 Dispatch : {n_h} héroïque, {n_d} duo, {n_g} grille")

        # Rapport JSON
        scoring_report_path = OUTPUT_DIR / "scoring_report.json"
        scoring_report_path.parent.mkdir(parents=True, exist_ok=True)
        export_scoring_report(photo_scores, dispatch, scoring_report_path)
        print(f"   📋 Rapport : {scoring_report_path}")

        # Arranger les pages avec le dispatch
        pages = arrange_pages_from_scores(
            dispatch, photos_root, recits=recits
        )
    else:
        # Mode classique (sans scoring)
        pages = arrange_pages(photo_files, recits, photos_root=photos_root)

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
    html = generate_html(pages)

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
