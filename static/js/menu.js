/* ═══════════════════════════════════════════════════════════════════
   LUME — menu.js
   Handles category filter chips + live search on the menu grid.
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', () => {
    const grid        = document.getElementById('dishGrid');
    const chipsWrap   = document.getElementById('categoryChips');
    const searchInput = document.getElementById('menuSearch');

    if (!grid) return;

    const cards = Array.from(grid.querySelectorAll('[data-category]'));
    let activeCategory = 'all';
    let searchQuery    = '';

    /* ── Apply filters ────────────────────────────────────────────── */
    function applyFilters() {
      let anyVisible = false;

      cards.forEach(card => {
        const catMatch    = activeCategory === 'all' || card.dataset.category === activeCategory;
        const searchText  = (card.dataset.search || '').toLowerCase();
        const searchMatch = searchQuery === '' || searchText.includes(searchQuery);
        const visible     = catMatch && searchMatch;

        card.style.display = visible ? '' : 'none';
        if (visible) anyVisible = true;
      });

      /* Empty state */
      let emptyEl = grid.querySelector('.menu-empty');
      if (!anyVisible) {
        if (!emptyEl) {
          emptyEl = document.createElement('div');
          emptyEl.className = 'menu-empty glass-card';
          emptyEl.style.cssText = 'grid-column:1/-1;padding:48px 24px;text-align:center;border-radius:20px;';
          emptyEl.innerHTML = `
            <span class="material-symbols-outlined" style="font-size:36px;color:var(--text-muted);opacity:.4;display:block;margin-bottom:10px">search_off</span>
            <p class="muted" style="font-size:14px">No dishes match your search. Try a different term or category.</p>
          `;
          grid.appendChild(emptyEl);
        }
      } else if (emptyEl) {
        emptyEl.remove();
      }
    }

    /* ── Category chips ───────────────────────────────────────────── */
    if (chipsWrap) {
      chipsWrap.addEventListener('click', e => {
        const chip = e.target.closest('[data-category]');
        if (!chip) return;

        chipsWrap.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        activeCategory = chip.dataset.category;
        applyFilters();
      });
    }

    /* ── Live search ──────────────────────────────────────────────── */
    if (searchInput) {
      let debounceTimer;
      searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          searchQuery = searchInput.value.trim().toLowerCase();
          applyFilters();
        }, 160);
      });

      /* Clear on Escape */
      searchInput.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
          searchInput.value = '';
          searchQuery = '';
          applyFilters();
          searchInput.blur();
        }
      });
    }
  });
})();
