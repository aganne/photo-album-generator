#!/usr/bin/env python3
"""Create PR for feature/enhance-print-risk"""
import subprocess, json, os, urllib.request, urllib.error

os.chdir("/root/photo-album-generator")

remote = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
owner_repo = remote.replace("https://github.com/", "").replace(".git", "")
owner, repo = owner_repo.split("/")
branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()

with open(os.path.expanduser("~/.git-credentials")) as f:
    cred = f.readline().strip()
token = cred.split(":")[2].split("@")[0]

body = """## Resume

Implemente la pipeline de retouche photo automatique (`--enhance`) et le module de penalite d'impression (`print_risk`).

## Modules ajoutes

### `album_generator/enhance.py` — Pipeline OpenCV 5 etapes (~100 ms/photo, CPU only)
1. Balance des blancs (Grey World)
2. Bilateral filter (d=5, sigma=50) — reduction bruit
3. CLAHE sur L (clip=2.0, tile=8) — contraste local
4. Local Contrast Enhancement (r=80, a=0.3) — GIMP luminosite details
5. Unsharp Mask (r=1.5, a=0.8, th=2) — nettete

Deux niveaux : `default` (doux) et `strong`. `batch_enhance()` avec ThreadPoolExecutor.

### `album_generator/print_risk.py` — Penalite d'impression [0.0, 0.30]
3 detecteurs calibres : bruit amplifie (+0.10), halos de sharpening (+0.10), perte de texture (+0.05)

### Integration `--enhance` dans `generate.py`
Flux : retouche → re-score → penalite print_risk → dispatch

## Tests
Teste sur 5 photos (frames video iOS 1920x1080) : pipeline ~100 ms/photo, print_risk ~0.015.

## Source
Rapport Athena « Etat de l'art retouche photo automatique »"""

data = json.dumps({
    "title": "feat: pipeline retouche photo --enhance + print_risk",
    "body": body,
    "head": branch,
    "base": "main"
}).encode()

req = urllib.request.Request(
    f"https://api.github.com/repos/{owner}/{repo}/pulls",
    data=data,
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"PR created: {result['html_url']}")
        print(f"PR number: {result['number']}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode()[:500]}")
