"""Render grantry's visualizations as self-contained HTML. No external scripts,
styles, fonts, or network calls: the whole page is one file that opens offline.
Values are HTML-escaped since account, role, and agent names are external data.
"""

from __future__ import annotations

import html
from typing import Any

from grantry.admin import Assignment
from grantry.graphdata import AccessSurface

_STYLE = """
:root {
  --bg: #0d0d0f; --surface: #16161a; --line: #26262c; --ink: #f4f4f5;
  --muted: #a1a1aa; --allow: #16a34a; --allow-bg: #16a34a22; --deny: #dc2626;
  --deny-bg: #dc262618; --accent: #3b82f6;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 28px 32px; background: var(--bg); color: var(--ink);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 19px; font-weight: 650; margin: 0 0 4px; }
.sub { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.kpis { display: flex; gap: 12px; margin-bottom: 22px; flex-wrap: wrap; }
.kpi { background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  padding: 12px 18px; min-width: 120px; }
.kpi .v { font-size: 26px; font-weight: 650; }
.kpi .k { font-size: 12px; color: var(--muted); }
.legend { display: flex; gap: 18px; align-items: center; font-size: 12px;
  color: var(--muted); margin-bottom: 12px; }
.swatch { display: inline-block; width: 11px; height: 11px; border-radius: 3px;
  vertical-align: -1px; margin-right: 5px; }
.matrix-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px;
  background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
th, td { padding: 7px 10px; text-align: left; white-space: nowrap; }
thead th { position: sticky; top: 0; background: var(--surface); color: var(--muted);
  font-weight: 600; border-bottom: 1px solid var(--line); font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.04em; }
tbody th { color: var(--ink); font-weight: 600; border-right: 1px solid var(--line); }
td.cell { text-align: center; font-weight: 600; cursor: default; }
td.allow { background: var(--allow-bg); color: var(--allow); }
td.deny { background: var(--deny-bg); color: var(--deny); }
td.none { color: var(--line); }
tbody tr:nth-child(even) { background: #ffffff05; }
.tl { border: 1px solid var(--line); border-radius: 12px; background: var(--surface);
  overflow: hidden; }
.tl table { font-variant-numeric: tabular-nums; }
.tag-allow { color: var(--allow); font-weight: 650; }
.tag-deny { color: var(--deny); font-weight: 650; }
.empty { color: var(--muted); padding: 30px; text-align: center; }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value))


def render_access_surface(surface: AccessSurface, generated_on: str) -> str:
    accounts = surface.accounts
    roles = surface.roles
    by_key = {(c.account_name, c.role_name): c for c in surface.cells}

    kpis = [
        (len(surface.cells), "identities"),
        (surface.allowed_count, "allowed"),
        (len(surface.cells) - surface.allowed_count, "denied"),
        (surface.reachable_accounts, "accounts reachable"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="k">{_esc(k)}</div></div>'
        for v, k in kpis
    )

    head = "".join(f"<th>{_esc(r)}</th>" for r in roles)
    rows = []
    for acct in accounts:
        cells = [f"<th>{_esc(acct)}</th>"]
        for role in roles:
            cell = by_key.get((acct, role))
            if cell is None:
                cells.append('<td class="cell none" title="no such identity">·</td>')
            elif cell.allowed:
                cells.append(f'<td class="cell allow" title="{_esc(cell.reason)}">allow</td>')
            else:
                cells.append(f'<td class="cell deny" title="{_esc(cell.reason)}">deny</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")

    body = f"<thead><tr><th>account \\ role</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>grantry access surface ({_esc(surface.caller)})</title>
<style>{_STYLE}</style></head><body>
<h1>Policy access surface for {_esc(surface.caller)}s</h1>
<div class="sub">What a {_esc(surface.caller)} may reach under the current policy. Snapshot {_esc(generated_on)}. Hover a cell for the deciding rule.</div>
<div class="kpis">{kpi_html}</div>
<div class="legend">
  <span><span class="swatch" style="background:var(--allow)"></span>allowed</span>
  <span><span class="swatch" style="background:var(--deny)"></span>denied</span>
</div>
<div class="matrix-wrap"><table>{body}</table></div>
</body></html>
"""


_GRAPH_TEMPLATE = "assignments_graph_template.html"


def _escape_for_script(serialized: str) -> str:
    # The JSON is inlined inside a <script> tag, so a value containing
    # "</script>" or the JS line separators must not break out of it.
    # Principal/account names are external data.
    out = serialized.replace("<", "\\u003c")
    out = out.replace(" ", "\\u2028")
    out = out.replace(" ", "\\u2029")
    return out


def render_assignments(assignments: list[Assignment], generated_on: str) -> str:
    """Render the interactive node-link access graph: principals -> permission
    sets -> accounts with connecting lines, hover, click-to-trace, search, and a
    table view. Self-contained (no external requests). The proven template is
    bundled as package data; here we only inject the rows and date.
    """
    import json
    import pkgutil

    rows = [
        [a.principal_type, a.principal_name, a.permission_set_name, a.account_id, a.account_name]
        for a in assignments
    ]
    data = _escape_for_script(json.dumps(rows, separators=(",", ":")))

    raw = pkgutil.get_data(__package__, _GRAPH_TEMPLATE)
    if raw is None:
        raise RuntimeError(f"graph template {_GRAPH_TEMPLATE} not found in package")
    template = raw.decode("utf-8")
    if "/*DATA*/" not in template:
        raise RuntimeError("graph template is missing its data placeholder")
    html = template.replace("const DATA = /*DATA*/[];", "const DATA = " + data + ";")
    html = html.replace("/*DATE*/", generated_on)
    return html


def render_audit(entries: list[dict[str, Any]], generated_on: str) -> str:
    allows = sum(1 for e in entries if e.get("allowed"))
    denies = len(entries) - allows
    callers = len({e.get("caller") for e in entries})
    kpis = [
        (len(entries), "grants logged"),
        (allows, "allowed"),
        (denies, "denied"),
        (callers, "distinct callers"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="k">{_esc(k)}</div></div>'
        for v, k in kpis
    )
    if not entries:
        table = '<div class="empty">No grants recorded yet.</div>'
    else:
        rows = []
        for e in reversed(entries):  # most recent first
            tag = (
                '<span class="tag-allow">allow</span>'
                if e.get("allowed")
                else '<span class="tag-deny">deny</span>'
            )
            rows.append(
                "<tr>"
                f"<td>{_esc(e.get('at', ''))}</td>"
                f"<td>{_esc(e.get('caller', ''))}</td>"
                f"<td>{_esc(e.get('identity', ''))}</td>"
                f"<td>{tag}</td>"
                f"<td>{_esc(e.get('reason', ''))}</td>"
                "</tr>"
            )
        table = (
            "<div class='tl'><table>"
            "<thead><tr><th>time</th><th>caller</th><th>identity</th>"
            "<th>decision</th><th>reason</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>grantry audit</title>
<style>{_STYLE}</style></head><body>
<h1>grantry audit trail</h1>
<div class="sub">Every credential grant decision, most recent first. Snapshot {_esc(generated_on)}.</div>
<div class="kpis">{kpi_html}</div>
{table}
</body></html>
"""
