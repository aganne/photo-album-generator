#!/usr/bin/env python3
"""Check dependencies for album generator."""
import sys

deps = {
    "jinja2": "jinja2",
    "weasyprint": "weasyprint",
    "PIL": "pillow",
}

missing = []
for mod, pkg in deps.items():
    try:
        __import__(mod)
        print(f"  ✓ {pkg}")
    except ImportError:
        missing.append(pkg)
        print(f"  ✗ {pkg} — missing")

if missing:
    print(f"\nMissing: {' '.join(missing)}")
    sys.exit(1)
else:
    print("\nAll dependencies OK!")
