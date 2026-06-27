#!/usr/bin/env python3
"""Debug _call_colormind."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from album_generator.colors import _call_colormind

# Test with all N
try:
    result = _call_colormind(["N", "N", "N", "N", "N"])
    print(f"All N: {result}")
except Exception as e:
    print(f"All N error: {e}")

# Test with one hint
try:
    result = _call_colormind([[200, 150, 100], "N", "N", "N", "N"])
    print(f"One hint: {result}")
except Exception as e:
    print(f"One hint error: {e}")
