#!/usr/bin/env python3
"""Poll CodeRabbit reviews on PR #10."""
import json, subprocess, os, time, sys

# Get token
with open(os.path.expanduser("~/.git-credentials")) as f:
    line = f.read().strip()
token = line.split(":")[2].split("@")[0]

owner = "aganne"
repo = "photo-album-generator"
pr_num = 10

# Check PR status
def check_ci():
    # Get latest commit SHA
    sha_cmd = ["curl", "-s",
        "-H", f"Authorization: token {token}",
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}"]
    result = subprocess.run(sha_cmd, capture_output=True, text=True)
    pr_data = json.loads(result.stdout)
    sha = pr_data.get("head", {}).get("sha", "")

    # Get check runs
    check_cmd = ["curl", "-s",
        "-H", f"Authorization: token {token}",
        f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"]
    result = subprocess.run(check_cmd, capture_output=True, text=True)
    checks = json.loads(result.stdout)

    return checks.get("check_runs", []), sha

# Poll CodeRabbit reviews
def get_reviews():
    cmd = ["curl", "-s",
        "-H", f"Authorization: token {token}",
        "-H", "Accept: application/vnd.github.v3+json",
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}/reviews"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

# Get PR comments (CodeRabbit posts as comments)
def get_comments():
    cmd = ["curl", "-s",
        "-H", f"Authorization: token {token}",
        "-H", "Accept: application/vnd.github.v3+json",
        f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_num}/comments"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

start = time.time()
max_wait = 600  # 10 minutes

while time.time() - start < max_wait:
    checks, sha = check_ci()
    reviews = get_reviews()
    comments = get_comments()

    # Check for CI failures
    ci_status = "pending"
    for c in checks:
        name = c.get("name", "")
        status = c.get("status", "")
        conclusion = c.get("conclusion", "")
        print(f"  [{name}] status={status} conclusion={conclusion}")

    # Check for CodeRabbit reviews
    coderabbit_reviews = [r for r in reviews if r.get("user", {}).get("login") == "coderabbitai"]
    coderabbit_comments = [c for c in comments if c.get("user", {}).get("login") == "coderabbitai"]

    if coderabbit_reviews:
        print(f"\n✅ CodeRabbit review found ({len(coderabbit_reviews)} reviews)")
        for r in coderabbit_reviews:
            body = r.get("body", "")[:500]
            state = r.get("state", "")
            print(f"  State: {state}")
            print(f"  Body: {body}")
        sys.exit(0)

    if coderabbit_comments:
        print(f"\n✅ CodeRabbit comments found ({len(coderabbit_comments)} comments)")
        for c in coderabbit_comments[:3]:
            body = c.get("body", "")[:300]
            print(f"  {body}")
        sys.exit(0)

    elapsed = int(time.time() - start)
    print(f"[{elapsed}s] Waiting for CodeRabbit...")

    if elapsed > 120 and not reviews and not coderabbit_comments:
        # After 2 min without any reviews, check if coderabbit is configured
        print("  CodeRabbit may not be configured for this repo. Proceeding...")
        sys.exit(2)  # Exit code 2 = no review found

    time.sleep(30)

print(f"\n⏰ Timeout ({max_wait}s) — no CodeRabbit review received")
sys.exit(1)
