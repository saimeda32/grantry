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

    body = (
        f"<thead><tr><th>account \\ role</th>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
    )
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


def render_assignments(assignments: list[Assignment], generated_on: str) -> str:
    # Aggregate so the page stays legible at 10k+ rows: rank principals by reach
    # and permission sets by spread, rather than dumping every raw row.
    principals: dict[str, set[str]] = {}
    principal_type: dict[str, str] = {}
    psets: dict[str, set[str]] = {}
    accounts: set[str] = set()
    for a in assignments:
        principals.setdefault(a.principal_name, set()).add(f"{a.account_id}/{a.permission_set_name}")
        principal_type[a.principal_name] = a.principal_type
        psets.setdefault(a.permission_set_name, set()).add(a.account_id)
        accounts.add(a.account_id)

    kpis = [
        (len(assignments), "assignments"),
        (len(principals), "principals"),
        (len(psets), "permission sets"),
        (len(accounts), "accounts"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="k">{_esc(k)}</div></div>'
        for v, k in kpis
    )

    top_principals = sorted(principals.items(), key=lambda kv: len(kv[1]), reverse=True)
    prow = "".join(
        "<tr>"
        f"<td>{_esc(name)}</td>"
        f"<td>{_esc(principal_type.get(name, ''))}</td>"
        f"<td class='num'>{len(grants)}</td>"
        "</tr>"
        for name, grants in top_principals[:100]
    )
    top_ps = sorted(psets.items(), key=lambda kv: len(kv[1]), reverse=True)
    psrow = "".join(
        f"<tr><td>{_esc(name)}</td><td class='num'>{len(accts)}</td></tr>"
        for name, accts in top_ps
    )

    note = ""
    if len(top_principals) > 100:
        note = f"<div class='sub'>Showing the top 100 of {len(top_principals)} principals by reach.</div>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>grantry org assignments</title>
<style>{_STYLE}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 18px; }}
.card {{ border: 1px solid var(--line); border-radius: 12px; background: var(--surface); overflow: hidden; }}
.card h2 {{ font-size: 13px; margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--line); color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
@media (max-width: 780px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<h1>Organization access map</h1>
<div class="sub">Who can assume which permission set in which account. Snapshot {_esc(generated_on)}.</div>
<div class="kpis">{kpi_html}</div>
{note}
<div class="grid">
  <div class="card"><h2>Principals by reach (account + permission-set grants)</h2>
    <table><thead><tr><th>principal</th><th>type</th><th class="num">grants</th></tr></thead>
    <tbody>{prow}</tbody></table></div>
  <div class="card"><h2>Permission sets by account spread</h2>
    <table><thead><tr><th>permission set</th><th class="num">accounts</th></tr></thead>
    <tbody>{psrow}</tbody></table></div>
</div>
</body></html>
"""


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
