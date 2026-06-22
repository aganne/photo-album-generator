# Photo Album Generator 🖼️ → 📄 → 📕

Générateur d'album photo PDF à partir de templates HTML/CSS avec WeasyPrint.
Écrivez vos récits en JSON, choisissez une palette de couleurs, et obtenez un PDF
prêt pour l'impression (Lulu, etc.).

## Principe

```
Photos + Récits (JSON) → Templates Jinja2 → HTML → WeasyPrint → PDF
```

## Démarrage rapide

```bash
pip install -r requirements.txt
python3 fonts/download_fonts.py    # Télécharge les polices (une fois)
python3 generate.py --html-only
```

Génère un HTML de démonstration avec des photos mock (pas besoin de photos réelles).

## Utilisation

```bash
# Checklist pré-génération (vérifie tout avant de lancer)
python3 generate.py --checklist

# Génération complète → PDF
python3 generate.py --photos ./photos --recits data/recits.json

# HTML seulement (pour preview)
python3 generate.py --photos ./photos --html-only

# Spécifier le fichier de sortie
python3 generate.py --photos ./photos -o mon_album.pdf
```

## Structure du projet

```
photo-album-generator/
├── album_generator/          # Module Python
│   ├── __init__.py
│   ├── config.py             # Configuration (palettes, polices, métadonnées)
│   └── templates/            # Templates Jinja2
│       ├── base.html         # Layout principal + inclusion des pages
│       ├── titre.html        # Page de garde
│       ├── heroique.html     # 1 photo pleine page (ouverture)
│       ├── duo.html          # 2 photos côte à côte
│       ├── grille.html       # 3-6 photos structurées
│       ├── collage.html      # 5+ photos organiques
│       ├── typographique.html# Texte + 0-1 photo (pause, citation)
│       ├── hero_texte.html   # Legacy — photo + texte narratif
│       ├── polaroid.html     # Legacy — photos éparpillées
│       ├── video_extrait.html# Legacy — pellicule vidéo
│       ├── video_54.html     # Pellicule 5×4 (20 frames/page)
│       ├── blank.html        # Page blanche (reliure)
│       └── credits.html      # Page de crédits
├── styles/
│   └── album.css             # CSS print-ready (A4+bleed)
├── fonts/                    # Polices (téléchargeables)
│   └── download_fonts.py     # Script de téléchargement
├── data/
│   └── recits.json           # Exemple de fichier récits (anonymisé)
├── photos/                   # Dossier photos (non versionné — à fournir)
├── generate.py               # Générateur principal
├── check_deps.py             # Vérification des dépendances
├── requirements.txt
└── .gitignore
```

## Types de pages (v0.2.0)

| Type | Densité | Photos | Usage |
|------|---------|--------|-------|
| **Héroïque** | Aérée | 1 | Ouverture, moment fort — photo pleine page |
| **Duo** | Modérée | 2 | Symétrie, contraste — deux photos côte à côte |
| **Grille** | Dense | 3-6 | Photos structurées en grille classique |
| **Collage** | Très dense | 5+ | Disposition organique façon scrapbook |
| **Typographique** | Aérée | 0-1 | Texte, citation — pause dans la narration |
| **Vidéo 5×4** | Dense | 20 | Pellicule sombre 5 lignes × 4 colonnes |

Types legacy conservés : `hero_texte`, `polaroid`, `video_extrait`.

## Traitement photo

Désaturation automatique de -10% (configurable dans `config.py` via `PALETTE.desaturation`)
pour compenser la sursaturation des couleurs à l'impression (10-15%).

```python
PALETTES_DISPONIBLES = {
    "Soleil": {
        ...
        "desaturation": 10,   # 0 = pas de désaturation, 10 = -10%
    },
}
```

## Checklist pré-génération

```bash
python3 generate.py --photos ./photos --recits data/recits.json --checklist
```

Affiche :
- Nombre de photos et répartition des types de page
- Vérification multiple de 4 (reliure)
- Fonds perdus (bleed) et marges de sécurité
- État de la désaturation
- Disponibilité des polices

## Contrainte de reliure

Le nombre total de pages est automatiquement ajusté à un multiple de 4
(ajout de pages blanches si nécessaire). C'est une contrainte standard
d'impression pour les livres reliés.

## Format des récits (data/recits.json)

```json
[
  {
    "type": "heroique",
    "photo": "chemin/photo.jpg",
    "title": "Titre",
    "date": "Janvier 2025",
    "text": "Texte du récit..."
  },
  {
    "type": "duo",
    "title": "Comparaison",
    "photos": ["photo1.jpg", "photo2.jpg"]
  },
  {
    "type": "collage",
    "title": "Souvenirs",
    "photos": ["p1.jpg", "p2.jpg", "p3.jpg", "p4.jpg", "p5.jpg"]
  },
  {
    "type": "typographique",
    "title": "Pause",
    "text": "Une citation...",
    "quote": true
  },
  {
    "type": "video_54",
    "video_title": "Premiers pas",
    "frames": ["f01.jpg", "f02.jpg", ...],
    "timecodes": ["00:00:01", "00:00:02", ...],
    "quote": "Chaque instant compte",
    "meta": "Extrait de 20 frames"
  }
]
```

## Configuration

### Palettes de couleurs

Les palettes se définissent dans `album_generator/config.py`. Exemple :

```python
PALETTES_DISPONIBLES = {
    "Soleil": {
        "bg_start": "#fefcf5",
        "bg_mid": "#f5ede0",
        "bg_end": "#e8cfa0",
        "desaturation": 10,
        ...
    },
}
```

Changez la palette active avec `PALETTE_NAME = "Soleil"`.

### Polices

```bash
python3 fonts/download_fonts.py
```

Télécharge DM Serif Display (Google Fonts) et Satoshi (Fontshare).
Les polices sont sous licence SIL Open Font License — libres d'utilisation.

## Spécifications d'impression

Les dimensions par défaut sont configurées pour Lulu (A4 + bleed 1/8") :
- Page : 216.35 × 302.75 mm
- Bleed : 3.175 mm
- Marge de sécurité : 12.7 mm
- DPI : 300

Ajustez `PAGE_WIDTH_MM`, `PAGE_HEIGHT_MM`, etc. dans `config.py` pour d'autres formats.

## Dépendances

- **weasyprint** — conversion HTML → PDF (rendu CSS complet)
- **jinja2** — templates HTML
- **Pillow** — traitement photo (désaturation) + mock photos

```bash
pip install -r requirements.txt
```

Ou vérifiez avec :
```bash
python3 check_deps.py
```

## Licence

MIT — faites-en ce que vous voulez, mais les photos personnelles dans `photos/`
restent votre propriété.

Polices : DM Serif Display (SIL OFL), Satoshi (SIL OFL).
