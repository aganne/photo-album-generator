# État de l'art — Enregistrement vocal pour application web d'album photo familial

**Projet :** Album photo Mael, Noah, Eliott (v2)
**Date :** 26 juin 2026
**Auteur :** Athéna (Hermes Agent)
**Contexte :** Permettre à un parent d'enregistrer des récits bruts ("décoffrage") — souvenirs racontés à voix haute, spontanément — qui seront transcrits puis transformés en récits d'album par un agent écrivain.

---

## Sommaire

1. [Enregistrement vocal côté navigateur](#1-enregistrement-vocal-côté-navigateur)
2. [Options alternatives (messagerie)](#2-options-alternatives-messagerie)
3. [Speech-to-Text (transcription)](#3-speech-to-text-transcription)
4. [Architecture recommandée](#4-architecture-recommandée)
5. [Recommandation finale](#5-recommandation-finale)
6. [Annexes](#6-annexes)

---

## 1. Enregistrement vocal côté navigateur

### 1.1 MediaRecorder API (approche native, recommandée)

L'API **MediaStream Recording** (W3C standard) est la solution de base pour enregistrer l'audio depuis un navigateur.

**Principe :** `navigator.mediaDevices.getUserMedia({ audio: true })` → `MediaRecorder` → `Blob`

```javascript
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const recorder = new MediaRecorder(stream, {
    mimeType: 'audio/webm;codecs=opus'
});
recorder.ondataavailable = (e) => chunks.push(e.data);
recorder.start(1000); // timeslice : chunks toutes les 1s
```

#### Compatibilité navigateurs

| Navigateur | Support | Depuis | Particularité |
|---|---|---|---|
| Chrome | ✅ Complet | v49+ | webm/opus natif |
| Firefox | ✅ Complet | v29+ | ogg/opus + webm |
| Safari macOS | ✅ | v14.1+ | mp4/AAC (pas webm !) |
| Safari iOS | ✅ | v14.5+ | mp4/AAC — attention aux limitations mémoire |
| Edge | ✅ | v79+ | Chromium, compatible Chrome |
| Samsung Internet | ✅ | v5+ | Chromium |
| IE / Android Browser | ❌ | — | Aucun support |

**⚠️ Particularité Safari/iOS :**
- Safari ne supporte PAS `audio/webm` — il produit du `audio/mp4` avec codec `mp4a.40.2` (AAC)
- Contrainte iOS : maximum ~6 `AudioContext` simultanés — un seul enregistrement à la fois
- Sur iOS en PWA, le microphone fonctionne mais peut demander la permission à chaque session
- Problème connu : `MediaRecorder.start()` peut lever `NotSupportedError` même si `isTypeSupported()` retourne `true`

#### Formats audio supportés

| Format | Browsers | Bitrate | Taille (5min) | Notes |
|---|---|---|---|---|
| `audio/webm;codecs=opus` | Chrome, Firefox, Edge | ~32-128 kbps | ~1.2-4.7 Mo | Meilleur rapport qualité/taille |
| `audio/ogg;codecs=opus` | Firefox uniquement | ~32-128 kbps | ~1.2-4.7 Mo | Firefox only |
| `audio/mp4;codecs=mp4a.40.2` | Safari | ~64-128 kbps | ~2.4-4.7 Mo | Standard AAC |
| `audio/wav` | Aucun (non supporté par MediaRecorder) | 1411 kbps | ~52 Mo | Trop volumineux |

**Recommandation :** Utiliser `audio/webm;codecs=opus` avec fallback `audio/mp4` pour Safari.

#### Gestion des longs enregistrements (5-15 min)

- **Timeslice :** `recorder.start(1000)` produit des chunks toutes les secondes — permet de streamer progressivement plutôt que de tout garder en mémoire
- **Blob final :** un enregistrement de 10 min en opus à 64 kbps pèse ~4.7 Mo — tout à fait acceptable
- **Problème potentiel :** Safari iOS peut libérer la page en mémoire si l'onglet passe en arrière-plan (pas de `BackgroundAudio` pour les PWAs)

#### Pause / Reprise

```javascript
recorder.pause();   // Met en pause (disponible depuis Chrome 52+)
recorder.resume();  // Reprend
```

- Supporté partout sauf Safari iOS ≤ v16.4 (résolu depuis Safari 16.4+)
- Solution de contournement pour vieux Safari : couper le microphone via `stream.getTracks()[0].enabled = false`

### 1.2 RecordRTC (abstraction, alternative)

RecordRTC est une librairie JavaScript mature qui encapsule `MediaRecorder` et `WebRTC`.

**Avantages :**
- API plus simple qu'avec MediaRecorder nu
- Gestion des fallbacks automatiques entre navigateurs
- Support de `pause()` / `resume()` natif
- Streaming par timeslice intégré (`timeSlice: 1000`)
- Upload automatique vers serveur à l'arrêt de l'enregistrement

**Inconvénients :**
- ~50 KB (minifiée) — pas négligeable pour une app simple
- Dépendance externe supplémentaire à maintenir
- La couche d'abstraction peut masquer des erreurs spécifiques au navigateur

**Recommandation :** Utiliser directement MediaRecorder API pour un contrôle fin. RecordRTC n'apporte pas de valeur ajoutée significative sauf si on veut uploader directement depuis le navigateur (ce qui n'est pas notre cas — on veut un upload asynchrone post-transcription).

### 1.3 Stockage temporaire côté client

| Méthode | Taille max | Persistance | Cas d'usage |
|---|---|---|---|
| **Mémoire (Blob in memory)** | Illimitée (RAM) | Session uniquement | Court terme, < 5 min |
| **IndexedDB** | ~50-100 Mo (selon navigateur) | Persistant entre sessions | Moyen terme, reprise après fermeture |
| **Cache API** | Variable (StorageManager) | Persistant, effaçable | Alternative à IndexedDB |
| **SessionStorage** | ~5-10 Mo | Session uniquement | Trop petit pour l'audio |

**Recommandation :** Utiliser la mémoire (tableau de chunks Blob) pendant l'enregistrement, puis uploader dès que l'enregistrement est terminé. IndexedDB utile si on veut permettre la reprise après fermeture de l'onglet (scénario avancé).

---

## 2. Options alternatives (messagerie)

### 2.1 Via WhatsApp Messages Vocaux

- **Déjà disponible** — le système WhatsApp Bot est déjà connecté ✅
- L'utilisateur envoie un message vocal WhatsApp → le bot reçoit le fichier audio (format .ogg opus)
- **Format WhatsApp :** audio/ogg; codecs=opus, ~16 kbps — bonne qualité, très léger
- **Avantage :** fonctionne depuis n'importe quel téléphone, sans app web, sans PWA
- **Inconvénient :** pas de lien direct avec la photo en cours de visualisation (l'utilisateur doit mentionner le contexte)
- **Limite :** messages vocaux WhatsApp limités à 15 min

### 2.2 Via Telegram Messages Vocaux

- **Déjà disponible** — le système Telegram Bot est déjà connecté ✅
- Format similaire à WhatsApp (opus/ogg)
- **Avantage :** API Telegram plus flexible (pas de restrictions Business)
- Les bots Telegram peuvent recevoir des messages vocaux directement via l'API
- Possibilité de lier un message vocal à une photo via un message reply ou un bouton inline

### 2.3 PWA (Progressive Web App)

**Capacités PWA pour l'enregistrement audio :**
- Le micro fonctionne en mode PWA (standalone) sur Android et iOS
- **Limitation iOS :** pas de service worker en arrière-plan pour l'audio — l'enregistrement s'arrête si l'écran s'éteint
- **Limitation Android :** depuis Android 11, besoin de `foregroundServiceType="microphone"` pour enregistrer en arrière-plan

**Conclusion PWA :** Utile comme complément, mais pas aussi fiable qu'une app native pour les longs enregistrements.

### 2.4 Comparaison : In-App vs Messagerie

| Critère | Enregistrement in-app (MediaRecorder) | WhatsApp | Telegram |
|---|---|---|---|
| **Contexte photo** | ✅ Direct — on voit la photo en parlant | ❌ Aucun — message vocal déconnecté | ⚠️ Possible via reply/bouton |
| **Qualité audio** | ✅ Configurable (bitrate) | ✅ 16 kbps opus (suffisant) | ✅ Similaire WhatsApp |
| **Longueur max** | Aucune limite pratique | ~15 min | Aucune limite (fichier) |
| **Hors-ligne** | ⚠️ Partiel (PWA) | ❌ Non | ❌ Non |
| **Fiabilité** | ⚠️ Dépend du navigateur | ✅ Très fiable | ✅ Très fiable |
| **Mobile** | ✅ Compatible | ✅ Application native | ✅ Application native |
| **Stockage** | Côté serveur après upload | Envoi direct au bot | Envoi direct au bot |

**Conclusion :** L'enregistrement in-app est préférable quand l'utilisateur regarde une photo et veut immédiatement raconter l'histoire associée. Les messageries sont excellentes en complément pour les moments où l'utilisateur n'est pas devant l'application web.

---

## 3. Speech-to-Text (transcription)

### 3.1 OpenAI Whisper (API cloud) — ✅ Recommandé

| Caractéristique | Valeur |
|---|---|
| **Coût** | $0.006/min (Nous subscription inclus ✅) |
| **Latence** | ~10-30s pour 5 min d'audio (selon taille fichier) |
| **Précision français** | ~95-98% (selon qualité audio, accent) |
| **Langues** | 50+ langues dont français |
| **Format supporté** | webm, mp3, mp4, m4a, ogg, wav... |
| **Taille max** | 25 MB par requête |

**Avantages :**
- Aucune infrastructure GPU nécessaire (serveur CPU only = OK)
- Précision excellente, même avec accents et bruit de fond
- Gère les noms propres et le langage parlé
- Déjà disponible via la subscription Nous

**Inconvénient :**
- Nécessite une connexion Internet
- Latence réseau (acceptable pour un usage non temps réel)

### 3.2 Whisper local (whisper.cpp) — Alternative CPU

**whisper.cpp** permet de faire tourner Whisper sur CPU uniquement :

| Modèle | RAM | Taille | Vitesse CPU (estimation 500 Mo RAM) | Précision français |
|---|---|---|---|---|
| **tiny** | ~300 Mo | 39 Mo | ~2-3x temps réel | ~75-80% |
| **base** | ~400 Mo | 74 Mo | ~1-2x temps réel | ~85-90% |
| **small** | ~800 Mo | 244 Mo | ~0.5x temps réel | ~92-95% |
| **medium** | ~1.5 Go | 769 Mo | ~0.2x temps réel | ~95-97% |

**Analyse pour le serveur cible (500 Mo RAM, CPU only) :**
- **tiny** : fonctionnerait, mais précision française médiocre
- **base** : à la limite — tient en RAM, lent mais faisable pour 5-15 min
- **small** : dépasse la RAM disponible
- **medium/large** : impossible

**Conclusion local :** Le modèle `base` tiendrait dans 500 Mo RAM mais la précision (~85-90%) est insuffisante pour des récits familiaux avec noms propres. À éviter pour notre cas.

### 3.3 Web Speech API (SpeechRecognition) — Gratuit mais limité

| Caractéristique | Valeur |
|---|---|
| **Coût** | Gratuit |
| **Latence** | Temps réel (streaming) |
| **Précision français** | Bonne (moteur Google sur Chrome) |
| **Support navigateur** | Chrome, Edge, Safari (webkit), Firefox (flag) |

**Limitations importantes :**
- Envoie l'audio vers les serveurs Google (Chrome) — pas de contrôle sur les données
- Fonctionne uniquement en **temps réel** — pas de transcription différée d'un fichier audio pré-enregistré
- Pas de contrôle sur le format ni la qualité audio envoyée
- `continuous: true` pas fiable sur les longs enregistrements (perte de contexte toutes les ~60s)
- Firefox : derrière un flag, pas activé par défaut
- L'utilisateur voit une bannière de micro permanente (pas idéal UX)

**⚠️ Inadapté pour notre cas :** La Web Speech API est conçue pour la dictée en direct, pas pour la transcription d'enregistrements pré-enregistrés. Notre pipeline est : enregistrer → uploader → transcrire plus tard. La Web Speech API ne correspond pas à ce flux.

### 3.4 Comparaison STT

| Critère | Whisper API (cloud) | Whisper local (tiny/base) | Web Speech API |
|---|---|---|---|
| **Précision français** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Noms propres** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| **Coût** | $0.006/min (inclus Nous) | Gratuit (mais CPU) | Gratuit |
| **Latence** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ (temps réel) |
| **Vie privée** | ⭐⭐ (cloud) | ⭐⭐⭐⭐⭐ (local) | ⭐ (serveurs Google) |
| **Adapté à notre pipeline** | ✅ Oui | ✅ Oui | ❌ Non (temps réel seulement) |
| **Maintenance** | Aucune | Build + mise à jour | Aucune |

**Recommandation : Whisper API via la subscription Nous** — pas d'infra à gérer, excellente précision, coût nul (déjà inclus dans la subscription).

---

## 4. Architecture recommandée

### 4.1 Pipeline global

```
[Photo affichée]
     │
     ▼
[Utilisateur appuie "Raconter"]
     │
     ▼
[Enregistrement vocal (MediaRecorder)] ◄──── [Fallback : WhatsApp/Telegram voice]
     │
     ├── Chunks webm/opus (toutes les 1s)
     │
     ▼
[Upload vers serveur] ──► Stockage temporaire (fichier .webm)
     │
     ▼
[File d'attente de transcription]
     │
     ▼
[Whisper API → Texte brut]
     │
     ▼
[Agent écrivain (Mistral) → Récit d'album]
     │
     ▼
[Stockage dans l'album + association photo]
```

### 4.2 Flux utilisateur détaillé

1. **L'utilisateur navigue dans l'album** et voit une photo
2. **Il clique sur "🎤 Raconter un souvenir"** (bouton flottant)
3. **Un panneau d'enregistrement apparaît** avec :
   - La photo en fond (ou en miniature)
   - Un compteur de temps
   - Boutons : Enregistrer / Pause / Stop / Annuler
4. **L'utilisateur parle** — son récit spontané (5-15 min)
5. **Il appuie sur Stop**
6. **L'audio est uploadé** vers le serveur avec l'ID de la photo
7. **Un indicateur "Transcription en cours..."** apparaît
8. **Whisper API transcrit** le fichier audio
9. **Le texte brut est envoyé à l'agent écrivain** (Mistral/Éole)
10. **Le récit final est enregistré** dans l'album, lié à la photo
11. **L'utilisateur peut éditer** le texte avant validation finale

### 4.3 Base de données (schéma minimal)

```sql
-- Table des enregistrements vocaux
CREATE TABLE enregistrements (
    id UUID PRIMARY KEY,
    photo_id UUID NOT NULL REFERENCES photos(id),
    album_id UUID NOT NULL REFERENCES albums(id),
    fichier_path TEXT NOT NULL,           -- Chemin du fichier audio
    duree_secondes INTEGER NOT NULL,
    format_audio TEXT NOT NULL,           -- 'webm', 'mp4', 'ogg'
    statut TEXT NOT NULL DEFAULT 'enregistre',  -- enregistre, transcrit, transforme, termine
    transcription TEXT,                   -- Texte brut (sortie Whisper)
    recit_final TEXT,                     -- Récit transformé par l'agent
    date_enregistrement TIMESTAMP NOT NULL DEFAULT NOW(),
    date_transcription TIMESTAMP,
    date_transformation TIMESTAMP,
    source TEXT DEFAULT 'in-app'          -- 'in-app', 'whatsapp', 'telegram'
);
```

### 4.4 Gestion des fichiers audio

- **Stockage local :** `/var/data/albums/audio/{album_id}/{photo_id}/{timestamp}.webm`
- **Sync OneDrive optionnelle :** copie vers `Albums/{album}/Audio/{photo}/{timestamp}.webm`
- **Nettoyage :** les fichiers audio bruts peuvent être supprimés après transformation (garder seulement le texte final)
- **Taille typique :** ~4.7 Mo pour 10 min en opus 64kbps

### 4.5 Stack technique recommandée

| Couche | Technologie | Justification |
|---|---|---|
| **Frontend** | HTML/CSS/JS (ou Streamlit) | Stack existante du projet |
| **Enregistrement** | MediaRecorder API (natif) + `getUserMedia` | Pas de dépendance externe |
| **Upload** | Fetch API (multipart/form-data) | Standard, chunks possibles |
| **Backend** | Flask (déjà utilisé) | Route `/api/upload-audio` |
| **File d'attente** | Redis + RQ ou SQLite + threading simple | Faible volume (< 100/jour) |
| **STT** | Whisper API (via Nous subscription) | Pas de GPU nécessaire |
| **Agent écrivain** | Mistral API (Éole) | Déjà disponible |
| **Stockage audio** | Système de fichiers + OneDrive (sync) | Pas de base de données pour les blobs |

---

## 5. Recommandation finale

### Approche prioritaire : Enregistrement in-app (MediaRecorder)

1. **MediaRecorder API** native — légère, standard W3C, support partout
2. Format `audio/webm;codecs=opus` avec fallback `audio/mp4` pour Safari
3. Timeslice 1000ms pour upload progressif
4. Whisper API pour la transcription — inclus dans la subscription Nous, pas de GPU nécessaire
5. Stockage fichier local + sync OneDrive optionnelle

### Approche complémentaire : WhatsApp/Telegram

- Les deux sont déjà connectés ✅
- Idéal pour les moments où l'utilisateur n'est pas devant l'app web
- Le bot reçoit le message vocal et le rattache à un album/photo via un message de contexte

### Ce qu'il NE faut PAS faire

- ❌ Web Speech API (SpeechRecognition) — pas adaptée à notre pipeline différé
- ❌ RecordRTC — surcouche inutile pour notre besoin
- ❌ Whisper local (whisper.cpp) — trop lourd pour 500 Mo RAM CPU only
- ❌ Stockage des blobs audio en base de données — préférer le filesystem

### Prochaines étapes

1. Implémenter le bouton "Raconter" dans l'interface photo
2. Ajouter la route Flask `/api/upload-audio` avec réception multipart
3. Intégrer l'appel Whisper API (via Nous) pour la transcription
4. **Pipeline agent écrivain (Éole/Mistral) → récit d'album**
5. Tests sur iOS Safari et Chrome Android

---

## 6. Annexes

### A. Références

- [MediaRecorder API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder)
- [MediaStream Recording API — W3C](https://www.w3.org/TR/mediastream-recording/)
- [RecordRTC GitHub](https://github.com/muaz-khan/RecordRTC)
- [whisper.cpp — GitHub](https://github.com/ggml-org/whisper.cpp)
- [OpenAI Whisper API Pricing](https://openai.com/api/pricing/)
- [Web Speech API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [MediaRecorder Browser Support — TestMu AI](https://www.testmuai.com/learning-hub/mediarecorder-browser-support/)

### B. Compatibilité détaillée MediaRecorder par version

| Browser | Version | Support | Codec audio par défaut |
|---|---|---|---|
| Chrome | 49+ | ✅ | audio/webm;codecs=opus |
| Chrome Android | 49+ | ✅ | audio/webm;codecs=opus |
| Firefox | 29+ | ✅ | audio/ogg;codecs=opus |
| Firefox Android | 29+ | ✅ | audio/ogg;codecs=opus |
| Safari macOS | 14.1+ | ✅ | audio/mp4;codecs=mp4a.40.2 |
| Safari iOS | 14.5+ | ✅ | audio/mp4;codecs=mp4a.40.2 |
| Edge (Chromium) | 79+ | ✅ | audio/webm;codecs=opus |
| Samsung Internet | 5+ | ✅ | audio/webm;codecs=opus |
| Opera | 36+ | ✅ | audio/webm;codecs=opus |
| IE | Toutes | ❌ | — |
| Android Browser | Toutes | ❌ | — |
