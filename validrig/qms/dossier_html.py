# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render a validation dossier as a self-contained, printable HTML page.

Design choices (a document meant to be printed, possibly in grayscale):
* status is never colour-alone — every pass/fail/N-A carries a text label;
* information value is a magnitude bar with the number directly labelled;
* one accessible hue for magnitude, reserved status colours with labels;
* fully self-contained (inline CSS, no external fonts/scripts/CDN) so it works
  offline and prints deterministically;
* ``@media print`` hides navigation and keeps table rows intact.
"""

from __future__ import annotations

import html
from typing import Any

_BAR_HUE = "#2563eb"
_STATUS = {  # colour is paired with the label text, never used alone
    "pass": "#16a34a", "approved_for_release": "#16a34a",
    "fail": "#dc2626", "not_approved_for_release": "#dc2626",
    "blocked_pending_calibration": "#dc2626",
    "not_run": "#b45309", "not_applicable": "#b45309", "not_collected": "#6b7280",
}


def _e(v: Any) -> str:
    return html.escape(str(v))


def _pill(label: str) -> str:
    color = _STATUS.get(label, "#6b7280")
    return (f'<span class="pill" style="--c:{color}">{_e(label)}</span>')


def _iv_bar(value, max_iv: float) -> str:
    if value is None:
        return '<span class="muted">not measured</span>'
    pct = 0 if max_iv <= 0 else max(2, round(value / max_iv * 100))
    return (f'<span class="bar"><span class="fill" style="width:{pct}%"></span></span>'
            f'<span class="barval">{value:.3f}</span>')


def render_dossier_html(d: dict[str, Any]) -> str:
    vv = d["vv_report"]
    s = vv["summary_of_results"]
    att = d["attestation"]
    contract_elems = d["contract"].get("elements", [])
    measured_ivs = [e["information_value"] for e in contract_elems
                    if e.get("measured") and e.get("information_value") is not None]
    max_iv = max(measured_ivs) if measured_ivs else 0.0
    rec = vv["release_recommendation"]

    rows_tc = "\n".join(
        f"<tr><td>{_e(item)}</td><td>{_pill(status)}</td></tr>"
        for item, status in s["per_test_case"].items()
    )
    rows_contract = "\n".join(
        f"<tr><td>{_e(e['name'])}</td><td>{_e(e.get('modality',''))}</td>"
        f"<td>{'yes' if e['name'] in d['contract'].get('minimal_sufficient_set_candidate', []) else '—'}</td>"
        f"<td>{_iv_bar(e.get('information_value'), max_iv)}</td></tr>"
        for e in contract_elems
    )
    acc_rows = "\n".join(
        f"<tr><td>{_e(r['threshold'])}</td><td>{_e(r['value'])}</td>"
        f"<td>{_e(r['limit'])}</td><td>{_pill('pass' if r['passed'] else 'fail')}</td></tr>"
        for r in d.get("acceptance", {}).get("results", [])
    )

    cal = vv.get("calibration", {"status": "not_collected"})
    if cal.get("status") == "not_collected":
        cal_html = f'<p>{_pill("not_collected")} No physician double-grading recorded yet.</p>'
    else:
        g = cal.get("gate", {})
        o = cal.get("agreement", {}).get("overall", {})
        cal_html = (f'<p>Gate: {_pill(g.get("status","?"))} · overall κ = '
                    f'{o.get("kappa")} (n = {o.get("n")})</p>')

    pins = att["pins"]
    pins_rows = "\n".join(f"<tr><td>{_e(k)}</td><td><code>{_e(v)}</code></td></tr>"
                          for k, v in pins.items())

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validation Dossier — {_e(d['product_id'])} — {_e(d['run_id'])}</title>
<style>
  :root {{ --ink:#111; --muted:#666; --line:#d0d0d0; --hue:{_BAR_HUE}; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui,-apple-system,Segoe UI,sans-serif; color:var(--ink);
         background:#fff; max-width:900px; margin:0 auto; padding:2rem 1.5rem;
         line-height:1.5; }}
  h1 {{ font-size:1.5rem; margin:0 0 .2rem; }} h2 {{ font-size:1.1rem; margin-top:2rem;
         border-bottom:2px solid var(--line); padding-bottom:.2rem; }}
  .sub {{ color:var(--muted); font-size:.9rem; }}
  .draft {{ border:1px solid #b45309; background:#fff7ed; color:#9a3412;
           padding:.5rem .75rem; border-radius:6px; margin:1rem 0; font-size:.9rem; }}
  table {{ border-collapse:collapse; width:100%; margin:.5rem 0; font-size:.92rem; }}
  th,td {{ border:1px solid var(--line); padding:.4rem .6rem; text-align:left; vertical-align:middle; }}
  th {{ background:#f3f4f6; }}
  .pill {{ display:inline-block; padding:.05rem .5rem; border-radius:999px; font-size:.8rem;
          font-weight:600; color:#fff; background:var(--c,#6b7280); }}
  .bar {{ display:inline-block; width:140px; height:10px; background:#eef2f7;
         border-radius:5px; vertical-align:middle; overflow:hidden; }}
  .fill {{ display:block; height:100%; background:var(--hue); border-radius:5px; }}
  .barval {{ margin-left:.5rem; font-variant-numeric:tabular-nums; }}
  .muted {{ color:var(--muted); }}
  code {{ font-size:.82rem; word-break:break-all; }}
  .verdict {{ font-size:1.05rem; margin:.5rem 0; }}
  footer {{ margin-top:2rem; color:var(--muted); font-size:.8rem;
           border-top:1px solid var(--line); padding-top:.75rem; }}
  @media print {{
    body {{ max-width:none; padding:0; }}
    a {{ color:inherit; text-decoration:none; }}
    tr, .bar, .pill {{ page-break-inside:avoid; }}
    h2 {{ page-break-after:avoid; }}
    * {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  }}
</style></head>
<body>
  <h1>Validation Dossier</h1>
  <p class="sub">{_e(d['product_id'])} v{_e(d['product_version'])} · run <code>{_e(d['run_id'])}</code>
     · generated {_e(d['generated_at'])} · QMS baseline {_e(d['qms_baseline_tag'])}</p>
  <div class="draft"><strong>DRAFT — unsigned.</strong> {_e(att['draft_notice'])}
     Signing: {_e(d['signing']['mechanism'])} (not yet anchored).</div>

  <p class="verdict"><strong>Release recommendation:</strong> {_pill(rec)}</p>
  <p class="sub">{_e(d['intended_use'])}</p>

  <h2>1. Validation summary (baseline, intended input)</h2>
  <p>{s['passed']} / {s['total_test_cases']} rubric items passed · {s['failed']} failed
     · condition: {_e(s['condition'])}</p>
  <table><thead><tr><th>Requirement (rubric item)</th><th>Result</th></tr></thead>
  <tbody>{rows_tc}</tbody></table>

  <h2>2. Acceptance criteria</h2>
  <table><thead><tr><th>Threshold</th><th>Value</th><th>Limit</th><th>Result</th></tr></thead>
  <tbody>{acc_rows or '<tr><td colspan=4 class=muted>none defined</td></tr>'}</tbody></table>

  <h2>3. Input contract (characterization)</h2>
  <p class="sub">Information value = mean score drop when the element is ablated.
     Perturbation results characterize the input contract; they are not pass/fail.</p>
  <table><thead><tr><th>Element</th><th>Modality</th><th>Necessary</th><th>Information value</th></tr></thead>
  <tbody>{rows_contract}</tbody></table>

  <h2>4. Judge calibration</h2>
  {cal_html}

  <h2>5. Attestation</h2>
  <p>Generated by <strong>{_e(att['generated_by'])}</strong>.
     Pinned-inputs hash: <code>{_e(att['pinned_inputs_hash'])}</code></p>
  <p class="sub">{_e(att['model_version_note'])}</p>
  <table><thead><tr><th>Pinned input</th><th>Value</th></tr></thead>
  <tbody>{pins_rows}</tbody></table>

  <h2>6. Signatures</h2>
  <p>{_pill('unsigned')} Meaning: Approved V&amp;V Evidence and Report.
     Signer roles: {_e(', '.join(vv['signatures']['signer_roles']))}.</p>
  <p class="sub">Sign by review + anchoring to an immutable release
     ({_e(d['signing']['mechanism'])}).</p>

  <footer>Draft evidence generated by the evaluation harness from pinned inputs.
     Requires human review and signature before use as QMS evidence.</footer>
</body></html>
"""
