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
        # Désaturation avant injection HTML (compense la sursaturation à l'impression)
        "desaturation": 10,   # 0 = pas de désaturation, 10 = -10% saturation
    },
    # Exemple de palette Océan :
    # "Ocean": {
    #     "name": "Océan 🌊",
    #     "bg_start": "#e8f4f8",
    #     "bg_mid": "#d0e8f0",
    #     "bg_end": "#a8d4e8",
    #     ...
    #     "desaturation": 10,
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
    "title": "Album Photo",             # Titre principal
    "subtitle": "Année Mémorable",       # Sous-titre / année
    "author": "La Famille",              # Auteurs
    "year": 2025,
    "enfant": "Mon Enfant",              # Prénom générique
}

# ── Styles de page disponibles ─────────────────────────────────────
PAGE_STYLES = {
    "heroique": {
        "name": "Héroïque",
        "density": "Aérée",
        "photos_per_page": (1, 1),
        "description": "1 photo pleine page — ouverture, moments forts",
        "colors": {"bg": "#fefcf5", "overlay": "rgba(254,252,245,0.7)", "title": "#3a2a1a"},
    },
    "duo": {
        "name": "Duo",
        "density": "Modérée",
        "photos_per_page": (2, 2),
        "description": "2 photos côte à côte (symétrie ou contraste)",
        "colors": {"bg": "#fefcf5", "border": "#ffffff", "accent": "#c49a5a"},
    },
    "grille": {
        "name": "Grille classique",
        "density": "Dense",
        "photos_per_page": (3, 6),
        "description": "3-6 photos structurées",
        "colors": {"bg": "#fefcf5", "border": "#ffffff", "accent": "#c49a5a"},
    },
    "collage": {
        "name": "Collage",
        "density": "Très dense",
        "photos_per_page": (5, 10),
        "description": "5+ photos disposition organique",
        "colors": {"bg": "#f5ede0", "border": "#ffffff", "shadow": "#d4b888"},
    },
    "typographique": {
        "name": "Typographique",
        "density": "Aérée",
        "photos_per_page": (0, 1),
        "description": "Texte + 0-1 photo — pause, citation",
        "colors": {"bg": "#fefcf5", "deco": "#c49a5a", "quote": "#8a6a3a"},
    },
    "hero_texte": {
        "name": "Hero + Texte (legacy)",
        "density": "Aérée",
        "photo_ratio": 0.55,
        "colors": {"bg": "#fefcf5", "deco": "#c49a5a"},
    },
    "polaroid": {
        "name": "Polaroid éparpillé (legacy)",
        "density": "Très dense",
        "photos_per_page": (4, 6),
        "rotation_range": (-3, 3),
        "border_px": 30,
        "colors": {"bg": "#f5ede0", "border": "#ffffff", "shadow": "#d4b888"},
    },
    "video_extrait": {
        "name": "Extrait vidéo (legacy)",
        "cols": 4,
        "rows": 5,
        "total_frames": 20,
        "film_border_color": "#1a1a1a",
        "colors": {"bg": "#1a1a1a", "text": "#e8cfa0"},
    },
    "video_54": {
        "name": "Extrait vidéo 5×4",
        "cols": 4,
        "rows": 5,
        "total_frames": 20,
        "description": "Grille 5 lignes × 4 colonnes, style pellicule sombre",
        "colors": {"bg": "#0d0d0d", "border": "#2a2a2a", "text": "#e8cfa0"},
    },
}
