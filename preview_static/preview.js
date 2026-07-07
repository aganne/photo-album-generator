/* ── preview.js — Interface de prévisualisation album photo ────────── */

// ── État global ─────────────────────────────────────────────────────
const state = {
  pages: [],
  photos: [],
  taggedPhotos: {},
  filters: { hero: true, favori: true, supprimer: true, redater: true, texte: true },
  searchQuery: '',
  regenerating: false,
  currentContextPhoto: null,
};

// ── Initialisation ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadPreview();
  loadTagged();
  setupEventListeners();
  pollRegenerateStatus();
});

// ── Event Listeners ─────────────────────────────────────────────────
function setupEventListeners() {
  // Sidebar toggle
  document.getElementById('btnSidebar').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('sidebar-hidden');
  });

  // Regenerate
  document.getElementById('btnRegenerate').addEventListener('click', triggerRegenerate);

  // Search
  document.getElementById('searchInput').addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase();
    renderPages();
  });

  // Filters
  document.querySelectorAll('#filterList input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', (e) => {
      state.filters[e.target.dataset.tag] = e.target.checked;
      renderPages();
    });
  });

  // Désactiver le menu contextuel natif
  document.addEventListener('contextmenu', (e) => {
    const thumb = e.target.closest('.photo-thumb-wrapper');
    if (thumb) {
      e.preventDefault();
      showContextMenu(e.clientX, e.clientY, thumb.dataset.filename);
    }
  });

  // Clic ailleurs → fermer menu
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.context-menu')) {
      hideContextMenu();
    }
    if (!e.target.closest('.dialog-overlay')) {
      hideDialogs();
    }
  });

  // Menu contextuel items (event delegation)
  document.getElementById('contextMenuItems').addEventListener('click', (e) => {
    const item = e.target.closest('.context-item');
    if (!item) return;

    if (item.id === 'contextCancel') {
      hideContextMenu();
      return;
    }
    if (item.id === 'contextClearAll') {
      clearAllTags(state.currentContextPhoto);
      return;
    }

    const tag = item.dataset.tag;
    const type = item.dataset.type;
    if (!tag) return;

    if (type === 'str') {
      if (tag === 'redater') showDateDialog(tag);
      else if (tag === 'texte') showTextDialog(tag);
    } else {
      toggleTag(state.currentContextPhoto, tag);
    }
  });

  // Dialogs
  document.getElementById('dateConfirm').addEventListener('click', () => {
    const tag = document.getElementById('dateDialog').dataset.tag;
    const value = document.getElementById('dateInput').value;
    if (value) setTagValue(state.currentContextPhoto, tag, value);
    hideDialogs();
  });
  document.getElementById('dateCancel').addEventListener('click', hideDialogs);

  document.getElementById('textConfirm').addEventListener('click', () => {
    const tag = document.getElementById('textDialog').dataset.tag;
    const value = document.getElementById('textInput').value;
    if (value) setTagValue(state.currentContextPhoto, tag, value);
    hideDialogs();
  });
  document.getElementById('textCancel').addEventListener('click', hideDialogs);

  // Keyboard: Escape to close
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      hideContextMenu();
      hideDialogs();
    }
  });
}

// ── API ─────────────────────────────────────────────────────────────
async function apiFetch(url, options = {}) {
  try {
    const resp = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }
    return await resp.json();
  } catch (err) {
    console.error(`API error [${url}]:`, err);
    throw err;
  }
}

// ── Chargement des données ──────────────────────────────────────────
async function loadPreview() {
  showLoading('Chargement de la prévisualisation...');
  document.getElementById('errorMessage').classList.add('hidden');

  try {
    // Charger les pages et les photos en parallèle
    const [previewData, photosData] = await Promise.all([
      apiFetch('/api/preview'),
      apiFetch('/api/photos'),
    ]);

    if (previewData.error) {
      if (previewData.need_scoring) {
        showError('Aucun score disponible. <button onclick="triggerRegenerate()" class="btn-primary" style="margin-top:12px">Lancer le scoring</button>');
      } else {
        showError(previewData.error);
      }
      state.pages = [];
    } else {
      // /api/preview retourne un tableau directement (pas d'enrobage "pages")
      state.pages = Array.isArray(previewData) ? previewData : (previewData.pages || []);
    }

    state.photos = photosData || [];
    document.getElementById('photoCount').textContent = `${state.photos.length} photos`;
    renderPages();
  } catch (err) {
    showError(`Erreur de chargement : ${err.message}`);
  }
}

async function loadTagged() {
  try {
    state.taggedPhotos = await apiFetch('/api/tagged-photos');
    renderTaggedList();
  } catch (err) {
    console.warn('Impossible de charger les photos taggées:', err.message);
  }
}

// ── Rendu ───────────────────────────────────────────────────────────
function renderPages() {
  const grid = document.getElementById('pagesGrid');
  const loading = document.getElementById('loadingIndicator');

  if (!state.pages.length) {
    if (!loading.classList.contains('hidden')) return;
    grid.innerHTML = '<p class="placeholder" style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--text-muted)">Aucune page à afficher. Lancez d\'abord le scoring.</p>';
    return;
  }

  loading.classList.add('hidden');
  grid.innerHTML = '';

  state.pages.forEach(page => {
    const card = document.createElement('div');
    card.className = 'page-card';

    // Filter photos by search query and checkbox filters
    const filteredPhotos = page.photos.filter(photo => {
      // Search filter
      if (state.searchQuery) {
        const filename = (photo.filename || '').toLowerCase();
        if (!filename.includes(state.searchQuery)) return false;
      }
      // Tag checkbox filters: show photo if it has ANY of the checked tags
      // (or no tags at all — we always show untagged photos)
      const photoInfo = state.photos.find(p => p.filename === photo.filename) || {};
      const tags = photoInfo.tags || {};
      const activeFilters = Object.entries(state.filters)
        .filter(([, checked]) => checked)
        .map(([tag]) => tag);
      if (activeFilters.length > 0) {
        // If all filters are unchecked, show nothing tagged; otherwise show if any match
        const hasAnyFilterMatch = activeFilters.some(tag => tags[tag]);
        // Also show untagged photos
        const hasTags = Object.values(tags).some(v => v);
        if (hasTags && !hasAnyFilterMatch) return false;
      }
      return true;
    });

    if (filteredPhotos.length === 0) return; // Skip empty pages after filtering

    // Header
    const header = document.createElement('div');
    header.className = 'page-header';
    header.innerHTML = `
      <span class="page-number">Page ${page.page_num}</span>
      <span class="page-template">${page.template_id}</span>
      ${page.is_hero ? '<span class="page-hero-badge">⭐ Héro</span>' : ''}
    `;
    card.appendChild(header);

    // Photos grid
    const photosDiv = document.createElement('div');
    photosDiv.className = 'page-photos';

    const templateId = page.template_id;
    // Grille: on détermine le layout en fonction du template
    // Pour la preview, on utilise un layout simple 4×5 ou en fonction du nombre de photos
    const numPhotos = filteredPhotos.length;
    photosDiv.style.gridTemplateColumns = getGridCols(numPhotos, templateId);

    filteredPhotos.forEach(photo => {
      const photoInfo = state.photos.find(p => p.filename === photo.filename) || {};
      const tags = photoInfo.tags || {};
      const hasSupprimer = tags.supprimer === true;

      const wrapper = document.createElement('div');
      wrapper.className = 'photo-thumb-wrapper';
      wrapper.dataset.filename = photo.filename;

      const img = document.createElement('img');
      img.className = 'photo-thumb';
      if (hasSupprimer) img.classList.add('photo-supprimee');
      img.loading = 'lazy';
      img.src = `/api/photo/${encodeURIComponent(photo.filename)}/thumbnail`;
      img.alt = photo.filename;
      wrapper.appendChild(img);

      // Badge de tag
      const activeTags = getActiveTags(tags);
      if (activeTags.length > 0) {
        const badge = document.createElement('div');
        badge.className = 'photo-tag-badge' + (activeTags.length > 1 ? ' multi' : '');
        if (activeTags.length === 1) {
          badge.textContent = getTagEmoji(activeTags[0]);
        } else {
          badge.textContent = activeTags.map(getTagEmoji).join('');
        }
        wrapper.appendChild(badge);
      }

      // Score
      if (photoInfo.score !== undefined) {
        const scoreDiv = document.createElement('div');
        scoreDiv.className = 'photo-score';
        scoreDiv.textContent = (photoInfo.score * 100).toFixed(0);
        wrapper.appendChild(scoreDiv);
      }

      // Nom overlay
      const nameDiv = document.createElement('div');
      nameDiv.className = 'photo-name-overlay';
      nameDiv.textContent = photo.filename;
      wrapper.appendChild(nameDiv);

      // Left-click alternative: click thumbnail to open tag context menu
      wrapper.addEventListener('click', (e) => {
        // Don't trigger if the user is clicking on a dialog or other interactive element
        if (e.target.closest('.context-menu') || e.target.closest('.dialog-overlay')) return;
        e.preventDefault();
        const rect = wrapper.getBoundingClientRect();
        showContextMenu(rect.left + 10, rect.top + 10, photo.filename);
      });

      photosDiv.appendChild(wrapper);
    });

    card.appendChild(photosDiv);
    grid.appendChild(card);
  });
}

function getGridCols(numPhotos, templateId) {
  // Déduire le nombre de colonnes du nombre de photos pour un rendu proportionnel
  if (numPhotos <= 1) return '1fr';
  if (numPhotos === 2) return '1fr 1fr';
  if (numPhotos <= 4) return '1fr 1fr';
  if (numPhotos <= 6) return '1fr 1fr 1fr';
  return '1fr 1fr 1fr 1fr';
}

// Ajuster la hauteur des photos en fonction du nombre total dans la page
function getPhotoHeight(numPhotos) {
  if (numPhotos <= 1) return '280px';
  if (numPhotos <= 2) return '200px';
  if (numPhotos <= 4) return '160px';
  return '130px';
}

function getActiveTags(tags) {
  const active = [];
  if (tags.hero) active.push('hero');
  if (tags.favori) active.push('favori');
  if (tags.supprimer) active.push('supprimer');
  if (tags.redater) active.push('redater');
  if (tags.texte) active.push('texte');
  return active;
}

function getTagEmoji(tag) {
  const map = { hero: '⭐', favori: '❤️', supprimer: '🗑️', redater: '📅', texte: '📝' };
  return map[tag] || '🏷️';
}

// ── Tagged photos sidebar ───────────────────────────────────────────
function renderTaggedList() {
  const container = document.getElementById('taggedList');
  const entries = Object.entries(state.taggedPhotos);

  if (entries.length === 0) {
    container.innerHTML = '<p class="placeholder">Aucune photo taggée</p>';
    return;
  }

  container.innerHTML = '';
  entries.forEach(([filename, tags]) => {
    const div = document.createElement('div');
    div.className = 'tagged-entry';

    const activeTags = getActiveTags(tags);

    const filenameSpan = document.createElement('span');
    filenameSpan.className = 'filename';
    filenameSpan.textContent = filename;
    div.appendChild(filenameSpan);
    div.appendChild(document.createTextNode(' '));

    // Append badge spans safely via DOM (no innerHTML)
    activeTags.forEach(t => {
      const badgeSpan = document.createElement('span');
      badgeSpan.className = `tag-badge tag-${t}`;
      badgeSpan.textContent = `${getTagEmoji(t)} ${t}`;
      div.appendChild(badgeSpan);
      div.appendChild(document.createTextNode(' '));
    });
    div.addEventListener('click', () => scrollToPhoto(filename));
    container.appendChild(div);
  });
}

function scrollToPhoto(filename) {
  const wrapper = document.querySelector(`[data-filename="${filename}"]`);
  if (wrapper) {
    wrapper.scrollIntoView({ behavior: 'smooth', block: 'center' });
    wrapper.style.outline = '2px solid var(--accent)';
    setTimeout(() => { wrapper.style.outline = ''; }, 2000);
  }
}

// ── Context Menu ────────────────────────────────────────────────────
function showContextMenu(x, y, filename) {
  state.currentContextPhoto = filename;
  const menu = document.getElementById('contextMenu');

  // Nom de la photo
  document.getElementById('contextPhotoName').textContent = filename;

  // Mettre à jour les checkmarks
  const photoInfo = state.photos.find(p => p.filename === filename) || {};
  const tags = photoInfo.tags || {};

  document.querySelectorAll('.context-item[data-tag]').forEach(item => {
    const tag = item.dataset.tag;
    const check = item.querySelector('.context-checkmark');
    if (tags[tag]) {
      check.classList.remove('hidden');
    } else {
      check.classList.add('hidden');
    }
  });

  // Afficher "retirer tous les tags" si au moins un tag actif
  const hasAnyTag = Object.keys(tags).length > 0;
  document.getElementById('contextClearAll').classList.toggle('hidden', !hasAnyTag);

  // Position (éviter les débordements)
  const mw = 220, mh = 320;
  const vw = window.innerWidth, vh = window.innerHeight;
  if (x + mw > vw) x = vw - mw - 10;
  if (y + mh > vh) y = vh - mh - 10;
  if (x < 10) x = 10;
  if (y < 10) y = 10;

  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.classList.remove('hidden');
}

function hideContextMenu() {
  document.getElementById('contextMenu').classList.add('hidden');
  state.currentContextPhoto = null;
}

// ── Tag actions ─────────────────────────────────────────────────────
async function toggleTag(filename, tag) {
  const photoInfo = state.photos.find(p => p.filename === filename) || {};
  const currentValue = (photoInfo.tags || {})[tag];

  try {
    let result;
    if (currentValue) {
      // Supprimer le tag
      result = await apiFetch(`/api/photo/${encodeURIComponent(filename)}/tag/${tag}`, {
        method: 'DELETE',
      });
    } else {
      // Ajouter le tag
      result = await apiFetch(`/api/photo/${encodeURIComponent(filename)}/tag`, {
        method: 'POST',
        body: JSON.stringify({ tag, value: true }),
      });
    }

    // Mettre à jour l'état local
    const idx = state.photos.findIndex(p => p.filename === filename);
    if (idx >= 0) {
      state.photos[idx].tags = result.tags || {};
    }

    hideContextMenu();
    renderPages();
    await loadTagged();
  } catch (err) {
    alert(`Erreur: ${err.message}`);
  }
}

async function setTagValue(filename, tag, value) {
  try {
    const result = await apiFetch(`/api/photo/${encodeURIComponent(filename)}/tag`, {
      method: 'POST',
      body: JSON.stringify({ tag, value }),
    });

    const idx = state.photos.findIndex(p => p.filename === filename);
    if (idx >= 0) {
      state.photos[idx].tags = result.tags || {};
    }

    hideContextMenu();
    renderPages();
    await loadTagged();
  } catch (err) {
    alert(`Erreur: ${err.message}`);
  }
}

async function clearAllTags(filename) {
  try {
    await apiFetch(`/api/photo/${encodeURIComponent(filename)}/tags`, {
      method: 'DELETE',
    });

    const idx = state.photos.findIndex(p => p.filename === filename);
    if (idx >= 0) {
      state.photos[idx].tags = {};
    }

    hideContextMenu();
    renderPages();
    await loadTagged();
  } catch (err) {
    alert(`Erreur: ${err.message}`);
  }
}

// ── Dialogs ─────────────────────────────────────────────────────────
function showDateDialog(tag) {
  const dialog = document.getElementById('dateDialog');
  dialog.dataset.tag = tag;
  document.getElementById('dateInput').value = '';
  document.getElementById('dateInput').focus();
  dialog.classList.remove('hidden');
}

function showTextDialog(tag) {
  const dialog = document.getElementById('textDialog');
  dialog.dataset.tag = tag;
  document.getElementById('textInput').value = '';
  document.getElementById('textInput').focus();
  dialog.classList.remove('hidden');
}

function hideDialogs() {
  document.getElementById('dateDialog').classList.add('hidden');
  document.getElementById('textDialog').classList.add('hidden');
}

// ── Regeneration ────────────────────────────────────────────────────
async function triggerRegenerate() {
  if (state.regenerating) return;

  try {
    await apiFetch('/api/regenerate', { method: 'POST' });
    state.regenerating = true;
    document.getElementById('btnRegenerate').disabled = true;
    document.getElementById('regenerateStatus').classList.remove('hidden');
    document.getElementById('regenerateStatus').textContent = '⏳ Régénération...';
  } catch (err) {
    alert(`Erreur: ${err.message}`);
  }
}

async function pollRegenerateStatus() {
  try {
    const status = await apiFetch('/api/regenerate/status');
    const badge = document.getElementById('regenerateStatus');
    const btn = document.getElementById('btnRegenerate');

    if (status.running) {
      state.regenerating = true;
      btn.disabled = true;
      badge.classList.remove('hidden');
      badge.textContent = `⏳ ${status.progress || 'En cours...'}`;
    } else if (state.regenerating) {
      // Vient de finir
      state.regenerating = false;
      btn.disabled = false;
      badge.textContent = `✅ ${status.progress || 'Terminé'}`;
      setTimeout(() => {
        badge.classList.add('hidden');
      }, 5000);
      // Recharger la preview
      await loadPreview();
      await loadTagged();
    }
  } catch (err) {
    // Silencieux — le poll continue
  }

  setTimeout(pollRegenerateStatus, 3000);
}

// ── Utilitaires UI ──────────────────────────────────────────────────
function showLoading(msg) {
  const el = document.getElementById('loadingIndicator');
  el.textContent = msg || 'Chargement...';
  el.classList.remove('hidden');
}

function showError(msg) {
  const el = document.getElementById('errorMessage');
  el.innerHTML = msg;
  el.classList.remove('hidden');
  document.getElementById('loadingIndicator').classList.add('hidden');
}
