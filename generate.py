#!/usr/bin/env python3
"""
Générateur d'album photo PDF — Template Jinja2 → HTML → WeasyPrint → PDF

Usage:
  python3 generate.py                       # Génère avec les données par défaut
  python3 generate.py --photos ./photos     # Spécifie un dossier photos
  python3 generate.py --recits recits.json  # Fichier JSON des récits
  python3 generate.py --output mon_album.pdf
  python3 generate.py --html-only           # Génère seulement le HTML (pas de PDF)
  python3 generate.py --enfant Noah         # Utilise la config d'un enfant spécifique

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

# Ajouter le projet au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from album_generator.config import (
    PALETTE, FONTS, ALBUM, PAGE_STYLES,
    PAGE_WIDTH_MM, PAGE_HEIGHT_MM,
)


# ── Chemins ─────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
TEMPLATES_DIR = PROJECT_DIR / "album_generator" / "templates"
STYLES_DIR = PROJECT_DIR / "styles"
PHOTOS_DIR = PROJECT_DIR / "photos"
OUTPUT_DIR = PROJECT_DIR / "output"
DATA_DIR = PROJECT_DIR / "data"


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
            "type": "hero_texte",
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
            "type": "video_extrait",
            "video_title": "Premiers pas",
            "frames": ["frame1.jpg", ...],
            "timecode": "00:01:23",
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


def group_photos_by_month(photo_files):
    """
    Trie les photos par mois (basé sur nom de fichier ou metadata).
    Retourne une liste de (mois, [photos]) triée chronologiquement.
    
    On essaie d'extraire la date depuis le nom de fichier.
    Format iPhone: IMG_YYYYMMDD_HHMMSS.jpg
    Format appareil: DSC_1234.jpg (fallback: modification time)
    """
    from collections import OrderedDict
    import re
    
    months = OrderedDict()
    month_names = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ]
    
    for fp in sorted(photo_files, key=lambda p: str(p)):
        stem = fp.stem
        month_idx = None
        
        # IMG_YYYYMMDD pattern (iPhone)
        m = re.search(r'(\d{4})(\d{2})(\d{2})', stem)
        if m:
            month_idx = int(m.group(2)) - 1  # 0-based
        else:
            # Fallback: utiliser mtime ou un mois aléatoire pour les photos non datées
            try:
                mtime = os.path.getmtime(fp)
                dt = datetime.fromtimestamp(mtime)
                month_idx = dt.month - 1
            except:
                month_idx = None
        
        if month_idx is not None and 0 <= month_idx < 12:
            month_name = month_names[month_idx]
            if month_name not in months:
                months[month_name] = []
            months[month_name].append(fp)
        else:
            # Photos sans date → "Non classé"
            if "Non classé" not in months:
                months["Non classé"] = []
            months["Non classé"].append(fp)
    
    return list(months.items())


def arrange_pages(photo_files, recits=None):
    """
    Organise les pages de l'album à partir des photos et récits.
    
    Returns: liste de dicts représentant chaque page.
    """
    pages = []
    
    # 1. Page de garde
    pages.append({"style": "titre", "data": {"album": ALBUM}})
    
    # 2. Si on a des récits, les intégrer
    if recits:
        # Trier récits par date si disponible
        for entry in recits:
            rtype = entry.get("type", "grille")
            if rtype == "grille":
                photos = []
                for rel_path in entry.get("photos", []):
                    fp = PHOTOS_DIR / rel_path
                    if fp.exists():
                        photos.append({
                            "path": str(fp.resolve()),
                            "label": rel_path,
                            "date": entry.get("date", ""),
                        })
                if photos:
                    pages.append({
                        "style": "grille",
                        "data": {"photos": photos, "title": entry.get("title", "")},
                    })
            elif rtype == "hero_texte":
                rel_path = entry.get("photo", "")
                fp = PHOTOS_DIR / rel_path
                pages.append({
                    "style": "hero_texte",
                    "data": {
                        "photo": {"path": str(fp.resolve()), "label": rel_path} if fp.exists() else None,
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
                    fp = PHOTOS_DIR / rel_path
                    if fp.exists():
                        photos.append({
                            "path": str(fp.resolve()),
                            "label": rel_path,
                        })
                if photos:
                    # Positionnement automatique des Polaroid
                    n = len(photos)
                    for i, photo in enumerate(photos):
                        # Répartir dans l'espace disponible
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
                    fp = PHOTOS_DIR / rel_path
                    if fp.exists():
                        frames.append({"path": str(fp.resolve()), "label": rel_path})
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
    
    # 3. Si pas de récits, générer automatiquement par mois
    else:
        months = group_photos_by_month(photo_files)
        for month_name, month_photos in months:
            # Parser les photos en lots
            photos_data = []
            for fp in month_photos:
                photos_data.append({
                    "path": str(fp.resolve()),
                    "label": fp.name,
                    "date": month_name[:3],  # Abréviation
                })
            
            # Répartir en pages de 4-6 photos (grille)
            batch_size = 4
            for i in range(0, len(photos_data), batch_size):
                batch = photos_data[i:i + batch_size]
                n = len(batch)
                if n <= 3:
                    pages.append({"style": "grille", "data": {"photos": batch}})
                else:
                    # Alterner entre grille et polaroid pour varier
                    if (i // batch_size) % 2 == 0:
                        pages.append({"style": "grille", "data": {"photos": batch}})
                    else:
                        # Polaroid layout
                        for j, p in enumerate(batch):
                            col = j % 2
                            row = j // 2
                            p["top"] = 5 + row * (80 // max((n + 1) // 2, 1))
                            p["left"] = 5 + col * 50
                            p["width"] = 40
                            p["rotation"] = random.uniform(-3, 3)
                            p["zindex"] = j
                        pages.append({"style": "polaroid", "data": {"photos": batch}})
    
    # 4. Page de crédits
    pages.append({"style": "credits", "data": {"album": ALBUM}})
    
    return pages


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
    args = parser.parse_args()
    
    # Scanner les photos
    photo_files = scan_photos(args.photos)
    print(f"📸 Photos trouvées : {len(photo_files)}")
    
    if not photo_files:
        print("⚠️  Aucune photo trouvée. Utilisation de photos mock pour test.")
        # Créer des placeholders pour les tests
        create_mock_photos()
        photo_files = scan_photos()
    
    # Charger les récits
    recits = load_recits(args.recits)
    
    # Organiser les pages
    pages = arrange_pages(photo_files, recits)
    print(f"📄 Pages à générer : {len(pages)}")
    
    # Générer le HTML
    html = generate_html(pages)
    
    # Sauvegarder le HTML intermédiaire
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
