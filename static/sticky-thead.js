// Sticky <thead> for Datasette tables in a horizontally-scrolling wrapper.
//
// Pure CSS can't pull this off today: .table-wrapper has overflow-x: auto,
// which browsers coerce into overflow-y: auto, making the wrapper a scroll
// container in both axes. That kills viewport-sticky thead.
//
// The fix is a fixed-position clone of <thead>, kept width-synced via
// ResizeObserver and horizontally scroll-synced to the wrapper.
//
// Progressive enhancement: when `overflow: auto clip` ships unflagged in
// Chromium / Firefox / WebKit (Chrome 148+ has it behind a flag as of
// 2026-03), the pure-CSS path in custom.css's @supports block takes over
// and this script is a no-op.

(function () {
  'use strict';

  // We can't feature-detect the future pure-CSS solution cleanly:
  // CSS.supports('overflow', 'auto clip') already returns true in
  // Chromium, but `overflow-y: clip` gets silently coerced to `hidden`
  // when paired with `overflow-x: auto` (unless Chrome's experimental
  // per-axis-sticky flag is on). So we always run the JS path for now
  // and revisit when the spec fix ships unflagged.

  function setupStickyThead(wrapper) {
    const table = wrapper.querySelector('table.rows-and-columns');
    if (!table || !table.tHead) return;
    const thead = table.tHead;

    const cloneTable = table.cloneNode(false);
    cloneTable.appendChild(thead.cloneNode(true));

    const holder = document.createElement('div');
    holder.className = 'sticky-thead-clone';
    holder.setAttribute('aria-hidden', 'true');
    holder.appendChild(cloneTable);
    holder.style.visibility = 'hidden';
    document.body.appendChild(holder);

    function syncWidths() {
      const srcRow = thead.rows[0];
      const dstRow = cloneTable.tHead.rows[0];
      if (!srcRow || !dstRow) return;
      for (let i = 0; i < srcRow.cells.length; i++) {
        const w = srcRow.cells[i].getBoundingClientRect().width;
        dstRow.cells[i].style.minWidth = w + 'px';
        dstRow.cells[i].style.width = w + 'px';
        dstRow.cells[i].style.maxWidth = w + 'px';
      }
      cloneTable.style.width = table.getBoundingClientRect().width + 'px';
    }

    function syncPosition() {
      const wrapRect = wrapper.getBoundingClientRect();
      const tableRect = table.getBoundingClientRect();
      const theadHeight = thead.getBoundingClientRect().height;
      // Show the clone only when the original thead has scrolled above the
      // viewport and the table itself is still on-screen.
      const visible = tableRect.top < 0 && tableRect.bottom > theadHeight;
      holder.style.visibility = visible ? 'visible' : 'hidden';
      holder.style.left = wrapRect.left + 'px';
      holder.style.width = wrapRect.width + 'px';
      holder.scrollLeft = wrapper.scrollLeft;
    }

    new ResizeObserver(syncWidths).observe(table);
    wrapper.addEventListener('scroll', syncPosition, { passive: true });
    window.addEventListener('scroll', syncPosition, { passive: true });
    window.addEventListener('resize', function () {
      syncWidths();
      syncPosition();
    });

    syncWidths();
    syncPosition();
  }

  function init() {
    document.querySelectorAll('.table-wrapper').forEach(setupStickyThead);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
