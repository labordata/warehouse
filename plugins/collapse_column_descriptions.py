"""Collapse the table's column-descriptions dl into a <details> element.

Otherwise it dominates above-the-fold on tables with many columns.
"""

from datasette import hookimpl

_JS = """
(function () {
    const dl = document.querySelector('dl.column-descriptions');
    if (!dl) { return; }
    const count = dl.querySelectorAll('dt').length;
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Column descriptions (' + count + ')';
    summary.style.cursor = 'pointer';
    summary.style.padding = '0.25em 0';
    summary.style.color = '#666';
    details.appendChild(summary);
    dl.parentNode.insertBefore(details, dl);
    details.appendChild(dl);
})();
"""


@hookimpl
def extra_body_script(view_name):
    if view_name in ("table", "row"):
        return _JS
    return None
