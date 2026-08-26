// lightbox.js — tap a placement photo to see it full size.
//
// The 72 px thumbnails in the device detail and in History are too small to
// tell two similar rooms apart, which is the one thing a placement photo
// exists for. This opens the original.
//
// Everything runs off one delegated listener on document, so photo strips
// that are re-rendered (the device detail and both History columns redraw
// on every refresh) keep working without re-binding — the same reason the
// lists use delegation.
//
// Loading state matters here rather than being polish: the images come
// straight from the phone camera at 2-4 MB each (spec §19.3, there is no
// thumbnail endpoint yet), so on a building's Wi-Fi there is a real pause
// between the tap and the picture.
import { esc } from './format.js';

let _group = [];   // photo ids of the strip that was tapped
let _index = 0;

function _els() {
  return {
    ov: document.getElementById('photo-ov'),
    img: document.getElementById('photo-ov-img'),
    counter: document.getElementById('photo-ov-counter'),
    spinner: document.getElementById('photo-ov-loading'),
    prev: document.getElementById('photo-ov-prev'),
    next: document.getElementById('photo-ov-next'),
  };
}

function _show(i) {
  const { img, counter, spinner, prev, next } = _els();
  if (!img || !_group.length) return;
  _index = (i + _group.length) % _group.length;
  const id = _group[_index];

  spinner.classList.remove('is-hidden');
  img.classList.add('is-loading');
  img.alt = `Placement photo ${_index + 1} of ${_group.length}`;
  img.src = `/api/photo/${encodeURIComponent(id)}`;

  counter.textContent = _group.length > 1 ? `${_index + 1} / ${_group.length}` : '';
  // A single photo needs no stepper; hiding rather than disabling keeps the
  // 56 px close button alone in the thumb zone.
  const many = _group.length > 1;
  prev.classList.toggle('is-hidden', !many);
  next.classList.toggle('is-hidden', !many);
}

function open(ids, startId) {
  const { ov } = _els();
  if (!ov || !ids.length) return;
  _group = ids;
  document.body.classList.add('scroll-locked');
  ov.classList.add('open');
  ov.setAttribute('aria-hidden', 'false');
  _show(Math.max(0, ids.indexOf(startId)));
  const closeBtn = document.getElementById('photo-ov-close');
  if (closeBtn) closeBtn.focus();
}

function close() {
  const { ov, img } = _els();
  if (!ov) return;
  ov.classList.remove('open');
  ov.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('scroll-locked');
  // Drop the src so a 4 MB image is not held decoded while it is invisible.
  if (img) img.removeAttribute('src');
  _group = [];
}

function isOpen() {
  const { ov } = _els();
  return !!ov && ov.classList.contains('open');
}

/** Photo ids of the strip a given thumbnail belongs to, so the stepper
 * walks that placement's photos and not every photo on the screen. */
function _groupFor(thumb) {
  const strip = thumb.closest('[data-photo-strip]') || thumb.parentElement;
  if (!strip) return [];
  return [...strip.querySelectorAll('.pthumb.view img')]
    .map(i => (i.getAttribute('src') || '').split('/').pop())
    .filter(Boolean);
}

export function initLightbox() {
  document.addEventListener('click', (e) => {
    const thumb = e.target.closest('.pthumb.view');
    if (thumb) {
      const img = thumb.querySelector('img');
      if (!img) return;
      const id = (img.getAttribute('src') || '').split('/').pop();
      const group = _groupFor(thumb);
      open(group.length ? group : [id], id);
      return;
    }
    if (!isOpen()) return;
    if (e.target.closest('#photo-ov-close') || e.target.id === 'photo-ov') { close(); return; }
    if (e.target.closest('#photo-ov-prev')) { _show(_index - 1); return; }
    if (e.target.closest('#photo-ov-next')) { _show(_index + 1); }
  });

  document.addEventListener('keydown', (e) => {
    // The thumbnails carry role="button", so they must answer to Enter and
    // Space like one — a tabindex without key handling is worse than no
    // tabindex, because it puts a dead stop in the tab order.
    if (!isOpen() && (e.key === 'Enter' || e.key === ' ')) {
      const thumb = e.target.closest && e.target.closest('.pthumb.view');
      if (thumb) {
        e.preventDefault();
        thumb.click();
      }
      return;
    }
    if (!isOpen()) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') _show(_index - 1);
    else if (e.key === 'ArrowRight') _show(_index + 1);
  });

  const { img, spinner } = _els();
  if (img) {
    img.addEventListener('load', () => {
      img.classList.remove('is-loading');
      if (spinner) spinner.classList.add('is-hidden');
    });
    img.addEventListener('error', () => {
      img.classList.remove('is-loading');
      if (spinner) spinner.innerHTML = `<span class="hint">${esc('Could not load this photo.')}</span>`;
    });
  }
}
