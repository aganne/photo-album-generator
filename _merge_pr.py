#!/usr/bin/env python3
"""Merge PR #10 via GitHub API (squash)."""
import json, subprocess, os

with open(os.path.expanduser("~/.git-credentials")) as f:
    line = f.read().strip()
token = line.split(":")[2].split("@")[0]

owner = "aganne"
repo = "photo-album-generator"
pr_num = 10

payload = json.dumps({
    "merge_method": "squash",
    "commit_title": f"feat: palette automatique Colormind depuis les meilleures photos (#{pr_num})",
})

cmd = [
    "curl", "-s", "-X", "PUT",
    "-H", f"Authorization: token {token}",
    "-H", "Accept: application/vnd.github.v3+json",
    f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}/merge",
    "-d", payload,
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
print(result.stdout[:500])

# Delete remote branch
cmd2 = ["git", "push", "origin", "--delete", "feature/colormind-palette"]
result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=15)
print(result2.stdout[:200])
print(result2.stderr[:200])
