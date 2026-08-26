// list.js — cockpit-redesign Stage 2b (spec §12/§19/§20.2): ONE reusable
// search + filter + sort component, built once and mounted only where
// data volume justifies it — the event log, the RF vendor tail and the RF
// foreign-devices list (332/53/14 rows). Deliberately NOT mounted on the
// five-device landing list (variant A's self-criticism, spec §20.2: that
// much control surface is disproportionate for five cards).
//
// A list is fully client-side (the caller already has every row in
// memory) — this component only filters/sorts/renders what it is given; it
// never fetches. The event log's server-side keyset "Load more" stays in
// events.js unchanged — mountList() here only searches/sorts whatever page
// has been loaded so far, which is a deliberate, documented simplification
// (KISS): a full cross-page search would need a server-side search
// endpoint that does not exist and that this stage does not add.
import { esc } from './format.js';

/**
 * @param {Object} cfg
 * @param {HTMLElement} cfg.root - container with an `input[type=search]`
 *   (optional), `.chip[data-filter]` buttons (optional), a `.lt-sort`
 *   button (optional) and a `.list-body` target — see index.html's
 *   `.list-block` markup, reused verbatim by every mount point.
 * @param {any[]} cfg.items
 * @param {(item: any) => string} cfg.renderRow
 * @param {(item: any) => string} cfg.searchFields - text to match against
 * @param {{key: string, test: (item: any) => boolean}[]} [cfg.filters]
 * @param {{label: string, cmp: (a: any, b: any) => number}[]} [cfg.sorts]
 * @param {string} [cfg.emptyText]
 * @returns {{ setItems(items: any[]): void }} — lets the caller push fresh
 *   data into an already-mounted list (e.g. events.js's "Load more").
 */
export function mountList(cfg) {
  const root = cfg.root;
  // input[type=search] rather than a class name — one real HTML semantic
  // for "this is a search box" everywhere it appears, reused by
  // ui_audit.py's control inventory too (spec §19).
  const search = root.querySelector('input[type=search]');
  const chips = Array.from(root.querySelectorAll('.chip[data-filter]'));
  const sortBtn = root.querySelector('.lt-sort');
  const body = root.querySelector('.list-body');

  const s = { query: '', filter: 'all', sortIdx: 0, items: cfg.items || [] };

  function apply() {
    let out = s.items.slice();
    if (cfg.filters && s.filter !== 'all') {
      const f = cfg.filters.find(x => x.key === s.filter);
      if (f) out = out.filter(f.test);
    }
    if (s.query) {
      const q = s.query.toLowerCase();
      out = out.filter(it => cfg.searchFields(it).toLowerCase().includes(q));
    }
    if (cfg.sorts && cfg.sorts.length) {
      out = out.slice().sort(cfg.sorts[s.sortIdx].cmp);
    }
    body.innerHTML = out.length
      ? out.map(cfg.renderRow).join('')
      : `<p class="hint" style="padding:16px">${esc(cfg.emptyText || 'No results.')}</p>`;
  }

  if (search) {
    search.addEventListener('input', (e) => { s.query = e.target.value; apply(); });
  }
  chips.forEach(btn => {
    btn.addEventListener('click', () => {
      chips.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      s.filter = btn.dataset.filter;
      apply();
    });
  });
  if (sortBtn && cfg.sorts && cfg.sorts.length) {
    sortBtn.textContent = cfg.sorts[0].label;
    sortBtn.addEventListener('click', () => {
      s.sortIdx = (s.sortIdx + 1) % cfg.sorts.length;
      sortBtn.textContent = cfg.sorts[s.sortIdx].label;
      apply();
    });
  } else if (sortBtn) {
    sortBtn.classList.add('is-hidden');
  }

  apply();

  return {
    setItems(items) { s.items = items || []; apply(); },
  };
}
