#!/usr/bin/env python3
"""Create PR via GitHub API."""
import json, subprocess, os

# Get token from git credentials
with open(os.path.expanduser("~/.git-credentials")) as f:
    line = f.read().strip()
# Format: https://user:TOKEN@github.com
token = line.split(":")[2].split("@")[0]

owner = "aganne"
repo = "photo-album-generator"
branch = "feature/colormind-palette"

body = r"""## Résumé

Ajoute l'extraction automatique de palette chromatique via l'API Colormind. La palette est générée à partir des couleurs dominantes des 5 meilleures photos de l'album, puis appliquée au CSS et aux styles inline du HTML.

## Changements

### Nouveau module `album_generator/colors.py`
- **`extract_palette(photo_scores, n_samples=5)`** — extrait une palette de 5 couleurs via l'API Colormind
  - Extrait la couleur moyenne de chaque photo (RGB, réduite à 256px pour la perf)
  - Appelle Colormind avec les couleurs dominantes comme hints
  - Fallback automatique sur la palette Soleil si l'API est indisponible
  - Retourne un dict palette compatible avec le format existant
- **`generate_dynamic_css(palette)`** — génère le CSS en substituant les couleurs Soleil → Colormind
- **`apply_palette_to_html(html, palette)`** — applique aussi les couleurs aux styles inline des templates

### Modification `generate.py`
- Nouvelle option `--palette` dans le CLI
- Workflow : scoring → layout → **palette** → render
- La palette s'applique au CSS et aux styles inline du HTML
- Nécessite `--scoring` (avertissement si utilisé sans)

### Mapping Colormind → CSS
| Index | Usage CSS |
|-------|-----------|
| 0 | `bg_start` (fond dégradé haut) |
| 1 | `band_top` + `text_primary` |
| 2 | `bg_mid` + `accent_1` |
| 3 | `bg_end` + `accent_2` |
| 4 | `band_bottom` + `deco_line` |

## Test
```bash
python3 generate.py --photos photos/mock --scoring --palette --html-only --window-size 4
```
✅ Toutes les couleurs Soleil sont remplacées dans le HTML final (0 occurrences restantes).
✅ Fallback fonctionnel si Colormind est indisponible.
✅ Polices DM Serif Display + Satoshi inchangées."""

payload = json.dumps({
    "title": "feat: palette automatique Colormind depuis les meilleures photos",
    "body": body,
    "head": branch,
    "base": "main",
})

cmd = [
    "curl", "-s", "-X", "POST",
    "-H", f"Authorization: token {token}",
    "-H", "Accept: application/vnd.github.v3+json",
    f"https://api.github.com/repos/{owner}/{repo}/pulls",
    "-d", payload,
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
print(result.stdout)

# Extract PR number
try:
    data = json.loads(result.stdout)
    pr_num = data.get("number")
    pr_url = data.get("html_url")
    print(f"\nPR #{pr_num}: {pr_url}")
except Exception as e:
    print(f"Parse error: {e}")
    print(f"HTTP status: {result.returncode}")
