// overlays.js — the two static, always-in-the-DOM overlay dialogs: the
// generic confirm modal (reused for stop-run + gateway-force loss prompts)
// and the help/guide overlay. Both share the same backdrop-click-to-close
// idiom, which is why they live together. Unchanged behaviour from the old
// app.js — inline onclick/backdrop-onclick replaced with addEventListener
// (cockpit-redesign Stage 2a, spec §6).

// ---------------------------------------------------------------------------
// Generic confirm modal
// ---------------------------------------------------------------------------

let _confirmResolve = null;

export function confirmModal({ title, message, icon = '⚠️', okLabel = 'Confirm', cancelLabel = 'Cancel', listHtml = '' }) {
  return new Promise(resolve => {
    _confirmResolve = resolve;
    document.getElementById('confirm-icon').textContent = icon;
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').innerHTML = message;
    document.getElementById('confirm-list').innerHTML = listHtml;
    document.getElementById('confirm-ok-btn').textContent = okLabel;
    document.getElementById('confirm-cancel-btn').textContent = cancelLabel;
    document.getElementById('confirm-ov').classList.add('open');
    document.body.classList.add('scroll-locked');
  });
}

function _resolveConfirm(result) {
  document.getElementById('confirm-ov').classList.remove('open');
  document.body.classList.remove('scroll-locked');
  const resolve = _confirmResolve;
  _confirmResolve = null;
  if (resolve) resolve(result);
}

function _closeConfirmBackdrop(e) {
  if (e.target === document.getElementById('confirm-ov')) _resolveConfirm(false);
}

// ---------------------------------------------------------------------------
// Help overlay
// ---------------------------------------------------------------------------

function openHelp() {
  document.getElementById('help-ov').classList.add('open');
  document.body.classList.add('scroll-locked');
}

function closeHelp() {
  document.getElementById('help-ov').classList.remove('open');
  document.body.classList.remove('scroll-locked');
}

function _closeHelpBackdrop(e) {
  if (e.target === document.getElementById('help-ov')) closeHelp();
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initOverlays() {
  document.getElementById('confirm-ov').addEventListener('click', _closeConfirmBackdrop);
  document.getElementById('confirm-cancel-btn').addEventListener('click', () => _resolveConfirm(false));
  document.getElementById('confirm-ok-btn').addEventListener('click', () => _resolveConfirm(true));

  document.getElementById('btn-help').addEventListener('click', openHelp);
  document.getElementById('help-ov').addEventListener('click', _closeHelpBackdrop);
  document.getElementById('help-close-btn').addEventListener('click', closeHelp);
}
