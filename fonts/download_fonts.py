#!/usr/bin/env python3
"""Télécharge les polices nécessaires depuis Google Fonts et Fontshare."""

import urllib.request
import zipfile
import io
import os
import sys

FONTS_DIR = os.path.dirname(os.path.abspath(__file__))

def download_dm_serif():
    """DM Serif Display from Google Fonts."""
    url = "https://fonts.google.com/download?family=DM+Serif+Display"
    try:
        resp = urllib.request.urlopen(url)
        z = zipfile.ZipFile(io.BytesIO(resp.read()))
        count = 0
        for f in z.namelist():
            if f.endswith('.ttf') and 'static' in f:
                name = f.split('/')[-1]
                path = os.path.join(FONTS_DIR, name)
                with open(path, 'wb') as out:
                    out.write(z.read(f))
                print(f"   DM Serif Display: {name}")
                count += 1
        return count > 0
    except Exception as e:
        print(f"   DM Serif Display: ERREUR — {e}")
        return False

def download_satoshi():
    """Satoshi from Fontshare CDN (open source)."""
    # Satoshi is on Fontshare; we grab individual weights
    weights = {
        "Satoshi-Regular.ttf": "regular",
        "Satoshi-Bold.ttf": "bold",
        "Satoshi-Italic.ttf": "italic",
    }
    count = 0
    for filename, weight in weights.items():
        url = f"https://api.fontshare.com/v2/fonts/download/satoshi"
        # Fontshare API: download all in one zip
        # Alternative: use CDN direct links
        pass

    # Try the zip download approach
    try:
        url = "https://api.fontshare.com/v2/fonts/download/satoshi"
        resp = urllib.request.urlopen(url)
        z = zipfile.ZipFile(io.BytesIO(resp.read()))
        for f in z.namelist():
            if f.endswith('.ttf') or f.endswith('.woff2'):
                name = f.split('/')[-1]
                if 'Regular' in name or 'Bold' in name or 'Italic' in name:
                    path = os.path.join(FONTS_DIR, name)
                    with open(path, 'wb') as out:
                        out.write(z.read(f))
                    print(f"   Satoshi: {name}")
                    count += 1
        return count > 0
    except Exception as e:
        print(f"   Satoshi: ERREUR — {e}")
        return False

if __name__ == "__main__":
    print("Telechargement des polices...")
    ok1 = download_dm_serif()
    ok2 = download_satoshi()
    if ok1 or ok2:
        print("\nPolices telechargees avec succes.")
        print("Relancez python3 generate.py --html-only pour generer l'album.")
    else:
        print("\nAucune police telechargee.")
        print("Telechargez-les manuellement :")
        print("  DM Serif Display : https://fonts.google.com/specimen/DM+Serif+Display")
        print("  Satoshi          : https://www.fontshare.com/fonts/satoshi")
        print("Placez les fichiers .ttf ou .woff2 dans le dossier fonts/")
