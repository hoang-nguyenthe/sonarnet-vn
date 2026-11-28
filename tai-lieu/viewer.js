(() => {
  const documents = window.SonarNetDocuments;
  const base = new URL('.', document.currentScript.src);
  if (!documents || typeof HTMLDialogElement === 'undefined') return;

  const viewer = document.createElement('dialog');
  viewer.className = 'sonarnet-document-viewer';
  viewer.setAttribute('aria-labelledby', 'sonarnet-document-title');
  viewer.innerHTML = `
    <div class="document-toolbar">
      <h2 id="sonarnet-document-title"></h2>
      <button class="document-button secondary" type="button" data-close>Đóng</button>
      <div class="document-page-controls" aria-label="Điều hướng trang">
        <button class="document-button secondary" type="button" data-prev aria-label="Trang trước">‹</button>
        <label>Trang <input aria-label="Số trang" type="number" inputmode="numeric" min="1"></label>
        <span data-total></span>
        <button class="document-button secondary" type="button" data-next aria-label="Trang sau">›</button>
      </div>
      <div class="document-actions">
        <button class="document-button secondary" type="button" data-zoom aria-pressed="false">Phóng to</button>
        <a class="document-button secondary" data-original target="_blank" rel="noopener">Mở PDF gốc</a>
        <a class="document-button" data-download download>Tải về</a>
      </div>
    </div>
    <div class="document-page"><img alt="" draggable="false">
      <p data-fallback hidden>Không tải được bản xem nhanh. <a data-pdf-fallback target="_blank" rel="noopener">Mở PDF gốc</a>.</p>
    </div>
    <span class="document-screen-reader" role="status" data-status></span>`;
  document.body.append(viewer);

  const find = selector => viewer.querySelector(selector);
  const title = find('h2');
  const pageInput = find('input');
  const previous = find('[data-prev]');
  const next = find('[data-next]');
  const panel = find('.document-page');
  const image = find('img');
  const fallback = find('[data-fallback]');
  const close = find('[data-close]');
  const zoom = find('[data-zoom]');
  let active;
  let trigger;
  let page = 1;

  function showPage(requested) {
    page = Math.max(1, Math.min(active.pages, requested));
    pageInput.value = page;
    previous.disabled = page === 1;
    next.disabled = page === active.pages;
    find('[data-status]').textContent = `Trang ${page} trên ${active.pages}`;
    panel.scrollTop = 0;
    fallback.hidden = true;
    image.hidden = false;
    image.alt = `${active.title}, trang ${page}`;
    image.src = new URL(`${active.preview}/${page}.webp`, base);
  }

  function setZoom(enlarged) {
    panel.classList.toggle('document-page-enlarged', enlarged);
    zoom.setAttribute('aria-pressed', String(enlarged));
    zoom.textContent = enlarged ? 'Thu nhỏ' : 'Phóng to';
    if (!enlarged) panel.scrollLeft = 0;
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-document]');
    if (!link || event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    const documentInfo = documents[link.dataset.document];
    if (!documentInfo) return;
    event.preventDefault();
    active = documentInfo;
    trigger = link;
    title.textContent = active.title;
    pageInput.max = active.pages;
    find('[data-total]').textContent = `/ ${active.pages}`;
    for (const selector of ['[data-original]', '[data-download]', '[data-pdf-fallback]']) {
      find(selector).href = new URL(active.pdf, base);
    }
    viewer.showModal();
    setZoom(false);
    showPage(1);
    close.focus();
  });

  previous.addEventListener('click', () => showPage(page - 1));
  next.addEventListener('click', () => showPage(page + 1));
  pageInput.addEventListener('change', () => {
    const value = pageInput.valueAsNumber;
    showPage(Number.isInteger(value) ? value : page);
  });
  pageInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') pageInput.blur();
  });
  zoom.addEventListener('click', () => setZoom(zoom.getAttribute('aria-pressed') === 'false'));
  close.addEventListener('click', () => viewer.close());
  viewer.addEventListener('close', () => trigger?.focus());
  viewer.addEventListener('keydown', event => {
    if (event.target === pageInput || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowLeft' && page > 1) showPage(page - 1);
    if (event.key === 'ArrowRight' && page < active.pages) showPage(page + 1);
  });
  image.addEventListener('error', () => {
    image.hidden = true;
    fallback.hidden = false;
  });
})();
