// theme.js — cockpit-redesign Stage 2b (spec §9/§20): the one-tap light/
// dark toggle in the header. Light is the product-owner-decided default;
// the choice is remembered in localStorage (spec: "window frontage and
// basement corridor follow each other within one round, faster than any
// ambient heuristic tracks" — so no prefers-color-scheme auto-detection,
// a manual switch only). The whole theme is one attribute on <html>; every
// colour in style.css is a custom property keyed off it — no per-component
// dark-mode overrides anywhere else.
const STORAGE_KEY = 'cockpit-theme';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  // Almost everything re-colours itself through custom properties. The one
  // exception is the heatmap, whose *text* colour has to be derived from the
  // composite of its own shading over the page background — that composite
  // changes with the theme, so those cells must be recomputed, not restyled.
  document.dispatchEvent(new CustomEvent('cockpit:themechange', { detail: { theme } }));
  const btn = document.getElementById('btn-theme-toggle');
  if (btn) {
    btn.setAttribute('aria-pressed', String(theme === 'dark'));
    btn.textContent = theme === 'dark' ? '☀' : '☾';
    btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }
}

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem(STORAGE_KEY, next); } catch (_) { /* private mode — theme just won't persist */ }
  applyTheme(next);
}

/** Applied as early as possible (called from app.js before first render) so
 * there is no flash of the wrong theme. Falls back to 'light' — the
 * product-owner-decided default — when nothing is stored yet. */
export function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem(STORAGE_KEY); } catch (_) { /* private mode */ }
  applyTheme(stored === 'dark' ? 'dark' : 'light');

  const btn = document.getElementById('btn-theme-toggle');
  if (btn) btn.addEventListener('click', toggleTheme);
}
