# Photo Album Generator 🖼️ → 📄 → 📕

Générateur d'album photo PDF à partir de templates HTML/CSS avec WeasyPrint.
Écrivez vos récits en JSON, choisissez une palette de couleurs, et obtenez un PDF
prêt pour l'impression (Lulu,印书馆…).

## Principe

```
Photos + Récits (JSON) → Templates Jinja2 → HTML → WeasyPrint → PDF
```

## Démarrage rapide

```bash
pip install -r requirements.txt
python3 generate.py --html-only
```

Génère un HTML de démonstration avec des photos mock (pas besoin de photos réelles).

## Utilisation

```bash
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
│       ├── grille.html       # Grille de photos classique
│       ├── hero_texte.html   # Grande photo + texte narratif
│       ├── polaroid.html     # Photos façon Polaroid éparpillées
│       ├── video_extrait.html# Extrait vidéo (pellicule)
│       └── credits.html      # Page de crédits
├── styles/
│   └── album.css             # CSS print-ready (A4+bleed)
├── data/
│   └── recits.json           # Exemple de fichier récits (Mael 2012)
├── photos/                   # Dossier photos (non versionné — à fournir)
├── generate.py               # Générateur principal
├── check_deps.py             # Vérification des dépendances
├── requirements.txt
└── .gitignore
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
        "band_top": "#8a6a3a",
        "band_bottom": "#c49a5a",
        ...
    },
}
```

Changez la palette active avec `PALETTE_NAME = "Soleil"`.

### Pour un autre enfant (Noah, Eliott…)

1. Ajoutez une palette (ou réutilisez-en une)
2. Modifiez les métadonnées dans `config.py` :
   ```python
   ALBUM = {
       "title": "Noah — Première année",
       "subtitle": "2024",
       "author": "Armel & Anna",
       "year": 2024,
       "enfant": "Noah",
   }
   ```
3. Copiez les photos dans `photos/`
4. Créez `data/recits.json` adapté
5. Lancez `python3 generate.py --photos ./photos`

### Formats de récits (data/recits.json)

| Type | Description |
|------|-------------|
| `hero_texte` | Grande photo pleine page + titre, date, texte narratif |
| `grille` | Grille de photos (3-6 par page) |
| `polaroid` | Photos disposées aléatoirement façon Polaroid |
| `video_extrait` | Pellicule vidéo avec frames, timecode, citation |

Voir `data/recits.json` pour un exemple complet.

### Spécifications d'impression

Les dimensions par défaut sont configurées pour Lulu (A4 + bleed ⅛") :
- Page : 216.35 × 302.75 mm
- Bleed : 3.175 mm
- Marge de sécurité : 12.7 mm
- DPI : 300

Ajustez `PAGE_WIDTH_MM`, `PAGE_HEIGHT_MM`, etc. dans `config.py` pour d'autres formats.

## Dépendances

- **weasyprint** — conversion HTML → PDF (rendu CSS complet)
- **jinja2** — templates HTML
- **Pillow** — création de mock photos pour les tests

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
