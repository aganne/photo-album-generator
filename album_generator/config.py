"""
Configuration de l'album photo.

Personnalisez PALETTE, ALBUM et PAGE_STYLES pour chaque enfant ou thème.
Les palettes sont réutilisables — gardez-les dans PALETTES_DISPONIBLES et
affectez-en une via PALETTE_NAME.
"""

# ── Spécifications du livre (Lulu / impression standard) ────────────
PAGE_WIDTH_MM = 216.35   # A4 + bleed
PAGE_HEIGHT_MM = 302.75
BLEED_MM = 3.175          # 1/8"
SAFE_MARGIN_MM = 12.7     # 1/2"
DPI = 300

# ── Palettes disponibles ────────────────────────────────────────────
# Ajoutez vos palettes ici, puis référencez-les par leur nom dans ALBUM.

PALETTES_DISPONIBLES = {
    "Soleil": {
        "name": "Soleil ☀️",
        "bg_start": "#fefcf5",
        "bg_mid": "#f5ede0",
        "bg_end": "#e8cfa0",
        "band_top": "#8a6a3a",
        "band_bottom": "#c49a5a",
        "text_primary": "#3a2a1a",
        "text_secondary": "#5a3a1a",
        "text_tertiary": "#8a6a3a",
        "accent_1": "#c49a5a",
        "accent_2": "#e8cfa0",
        "accent_3": "#d4b888",
        "photo_border": "#ffffff",
        "deco_line": "#c49a5a",
    },
    # Exemple de palette Océan :
    # "Ocean": {
    #     "name": "Océan 🌊",
    #     "bg_start": "#e8f4f8",
    #     "bg_mid": "#d0e8f0",
    #     "bg_end": "#a8d4e8",
    #     ...
    # },
}

# ── Palette active ──────────────────────────────────────────────────
PALETTE_NAME = "Soleil"
PALETTE = PALETTES_DISPONIBLES[PALETTE_NAME]

# ── Polices ─────────────────────────────────────────────────────────
# Utilisez des polices système ou installez-les dans le dossier fonts/.
FONTS = {
    "title": "DM Serif Display",  # Titres élégants
    "body": "Satoshi",            # Texte courant
}

# ── Métadonnées de l'album ──────────────────────────────────────────
ALBUM = {
    "title": "Mael — Première année",   # Titre principal
    "subtitle": "2012",                  # Sous-titre / année
    "author": "Armel & Anna",            # Auteurs
    "year": 2012,
    "enfant": "Mael",                    # Prénom de l'enfant
}

# ── Styles de page disponibles ─────────────────────────────────────
PAGE_STYLES = {
    "grille": {
        "name": "Grille classique",
        "photos_per_page": (3, 6),  # min, max
        "colors": {"bg": "#fefcf5", "border": "#ffffff", "accent": "#c49a5a"},
    },
    "hero_texte": {
        "name": "Hero + Texte",
        "photo_ratio": 0.55,
        "colors": {"bg": "#fefcf5", "deco": "#c49a5a"},
    },
    "polaroid": {
        "name": "Polaroid éparpillé",
        "photos_per_page": (4, 6),
        "rotation_range": (-3, 3),
        "border_px": 30,
        "colors": {"bg": "#f5ede0", "border": "#ffffff", "shadow": "#d4b888"},
    },
    "video_extrait": {
        "name": "Extrait vidéo",
        "cols": 4,
        "rows": 5,
        "total_frames": 20,
        "film_border_color": "#1a1a1a",
        "colors": {"bg": "#1a1a1a", "text": "#e8cfa0"},
    },
}
