/**
 * Library check — wires up #check-library-btn on the request form.
 * Calls GET /api/library/check?title=...&author=... and displays the result
 * in #library-check-result.
 */
document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('check-library-btn');
  const resultEl = document.getElementById('library-check-result');

  if (!btn || !resultEl) return;

  btn.addEventListener('click', function () {
    const title = btn.dataset.title || '';
    const author = btn.dataset.author || '';

    // Show spinner, disable button
    const savedHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Checking\u2026';
    resultEl.className = 'd-none';

    const url =
      '/api/library/check?title=' +
      encodeURIComponent(title) +
      '&author=' +
      encodeURIComponent(author);

    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        let cls = 'alert-secondary';
        let html = '';

        if (!data.configured) {
          cls = 'alert-secondary';
          html = 'Library check not available — Audiobookshelf is not configured.';
        } else if (data.found && data.is_certain) {
          cls = 'alert-danger';
          html =
            '<i class="bi bi-exclamation-triangle-fill me-2"></i>' +
            '<strong>This book appears to already be in the library!</strong><br>' +
            'Found as: <em>' +
            escHtml(data.match.title) +
            '</em>' +
            (data.match.author ? ' by ' + escHtml(data.match.author) : '') +
            '.<br><small class="text-muted">You can still submit a request if you need a different edition.</small>';
        } else if (data.found) {
          cls = 'alert-warning';
          html =
            '<i class="bi bi-question-circle me-2"></i>' +
            'This book might already be in the library: ' +
            '<em>' +
            escHtml(data.match.title) +
            '</em>' +
            (data.match.author ? ' by ' + escHtml(data.match.author) : '') +
            '.<br><small class="text-muted">Check the library to confirm before submitting.</small>';
        } else {
          cls = 'alert-success';
          html =
            '<i class="bi bi-check-circle me-2"></i>' +
            'This book was not found in the library.';
        }

        resultEl.className = 'alert ' + cls + ' mt-2';
        resultEl.innerHTML = html;
      })
      .catch(function () {
        resultEl.className = 'alert alert-secondary mt-2';
        resultEl.textContent = 'Could not check the library. Please try again later.';
      })
      .finally(function () {
        btn.disabled = false;
        btn.innerHTML = savedHtml;
      });
  });
});

/** Minimal HTML escape to prevent XSS when inserting server data into innerHTML. */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
