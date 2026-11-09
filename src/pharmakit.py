"""pharmakit: shared look for all portfolio projects (P1-P6).

One palette, one chart theme, one one-page report + flowchart generator,
so every repo looks like it came from the same person.
"""
from __future__ import annotations

import base64
import html
import io
from pathlib import Path

# ---------------------------------------------------------------- palette
PALETTE = {
    "ink": "#12324A",      # deep navy text
    "teal": "#0E7C7B",     # primary (pharmacy green-teal)
    "mint": "#2BB3A3",     # secondary
    "sage": "#8CC9B8",     # tertiary
    "bg": "#F3FAF8",       # page tint
    "panel": "#E3F2EE",    # panel tint
    "line": "#C9DED8",     # hairlines
    "grey": "#6B7C8F",     # muted text
    "coral": "#E4572E",    # alert / signal
    "amber": "#E9A23B",    # caution
}
SERIES = ["#0E7C7B", "#E4572E", "#2F6DB5", "#E9A23B", "#7A5BA6", "#2BB3A3", "#6B7C8F"]


def mpl_theme():
    """Apply the shared matplotlib theme."""
    import matplotlib as mpl
    from cycler import cycler

    mpl.rcParams.update({
        "font.family": "Inter",
        "font.size": 10,
        "axes.edgecolor": PALETTE["line"],
        "axes.labelcolor": PALETTE["ink"],
        "axes.titleweight": "bold",
        "axes.titlesize": 12,
        "axes.titlecolor": PALETTE["ink"],
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#E6EFEC",
        "grid.linewidth": 0.8,
        "xtick.color": PALETTE["grey"],
        "ytick.color": PALETTE["grey"],
        "axes.prop_cycle": cycler(color=SERIES),
        "figure.facecolor": "white",
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
        "legend.frameon": False,
    })


def img_b64(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


# ---------------------------------------------------------------- flowchart
def flowchart_svg(steps: list[dict], width: int = 760) -> str:
    """Vertical flowchart. Each step: {title, why, kind?} kind in {data, process, check, output}.
    Box on the left, reasoning ('why') on the right."""
    colors = {"data": PALETTE["ink"], "process": PALETTE["teal"],
              "check": PALETTE["amber"], "output": PALETTE["coral"]}
    box_w, gap, x0 = 250, 18, 10
    y = 10
    parts = []
    import textwrap

    for i, s in enumerate(steps):
        why_lines = textwrap.wrap(s.get("why", ""), 62)
        title_lines = textwrap.wrap(f"{i+1}. {s['title']}", 30)
        h = max(18 * len(title_lines) + 20, 16 * len(why_lines) + 16, 46)
        c = colors.get(s.get("kind", "process"), PALETTE["teal"])
        parts.append(f'<rect x="{x0}" y="{y}" width="{box_w}" height="{h}" rx="9" fill="{c}"/>')
        ty = y + (h - 18 * len(title_lines)) / 2 + 13
        for ln in title_lines:
            parts.append(f'<text x="{x0+14}" y="{ty}" fill="#fff" font-size="13" font-weight="600">{html.escape(ln)}</text>')
            ty += 18
        # reasoning panel
        parts.append(f'<rect x="{x0+box_w+14}" y="{y}" width="{width-box_w-x0-24}" height="{h}" rx="9" fill="{PALETTE["panel"]}"/>')
        parts.append(f'<rect x="{x0+box_w+14}" y="{y}" width="4" height="{h}" fill="{c}"/>')
        wy = y + (h - 16 * len(why_lines)) / 2 + 12
        for ln in why_lines:
            parts.append(f'<text x="{x0+box_w+28}" y="{wy}" fill="{PALETTE["ink"]}" font-size="11.5">{html.escape(ln)}</text>')
            wy += 16
        y += h
        if i < len(steps) - 1:
            cx = x0 + box_w / 2
            parts.append(f'<line x1="{cx}" y1="{y+2}" x2="{cx}" y2="{y+gap-4}" stroke="{PALETTE["grey"]}" stroke-width="2"/>')
            parts.append(f'<polygon points="{cx-5},{y+gap-8} {cx+5},{y+gap-8} {cx},{y+gap-1}" fill="{PALETTE["grey"]}"/>')
            y += gap
    legend = " · ".join(f'<tspan fill="{v}">■</tspan> {k}' for k, v in colors.items())
    y += 22
    parts.append(f'<text x="{x0}" y="{y}" font-size="11" fill="{PALETTE["grey"]}">{legend}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {y+8}" width="100%" '
            f'font-family="Inter, Segoe UI, sans-serif">' + "".join(parts) + "</svg>")


# ---------------------------------------------------------------- report
CSS = f"""
@page {{ size: A4; margin: 12mm; }}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,'Segoe UI',system-ui,sans-serif;color:{PALETTE['ink']};background:{PALETTE['bg']};font-size:13px;line-height:1.45}}
.page{{max-width:900px;margin:0 auto;background:#fff;padding:28px 34px 24px;border-top:8px solid {PALETTE['teal']}}}
.tag{{display:inline-block;background:{PALETTE['panel']};color:{PALETTE['teal']};font-weight:600;font-size:11px;padding:3px 9px;border-radius:20px;margin-right:6px;letter-spacing:.02em}}
.tag.warn{{background:#FDEBE5;color:{PALETTE['coral']}}}
h1{{font-size:24px;margin:10px 0 2px;letter-spacing:-.01em}}
.sub{{color:{PALETTE['grey']};margin-bottom:14px}}
.headline{{background:{PALETTE['panel']};border-left:5px solid {PALETTE['teal']};padding:12px 16px;border-radius:6px;font-size:15px;font-weight:600;margin:10px 0 16px}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}}
.tile{{border:1px solid {PALETTE['line']};border-radius:8px;padding:10px 12px}}
.tile .v{{font-size:22px;font-weight:700;color:{PALETTE['teal']}}}
.tile .l{{font-size:11px;color:{PALETTE['grey']}}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:{PALETTE['teal']};margin:14px 0 6px;border-bottom:1px solid {PALETTE['line']};padding-bottom:4px}}
ul{{margin:4px 0 0 18px;padding:0}} li{{margin:2px 0}}
figure{{margin:6px 0}} figure img{{width:100%;border:1px solid {PALETTE['line']};border-radius:6px}}
figcaption{{font-size:11px;color:{PALETTE['grey']}}}
table.t{{border-collapse:collapse;width:100%;font-size:11.5px}}
table.t th{{background:{PALETTE['teal']};color:#fff;text-align:left;padding:5px 7px;font-weight:600}}
table.t td{{border-bottom:1px solid {PALETTE['line']};padding:4px 7px}}
.foot{{margin-top:16px;font-size:10.5px;color:{PALETTE['grey']};border-top:1px solid {PALETTE['line']};padding-top:8px}}
.pb{{page-break-before:always}}
@media print {{
 body{{background:#fff;font-size:10.5px;line-height:1.35}}
 .page{{padding:10px 4px 0;max-width:none;border-top-width:6px}}
 h1{{font-size:19px}} .headline{{font-size:12.5px;padding:8px 12px;margin:6px 0 10px}}
 .tiles{{margin-bottom:8px}} .tile{{padding:6px 9px}} .tile .v{{font-size:17px}}
 h2{{margin:8px 0 4px;font-size:11px}} figure img{{max-height:205px;object-fit:contain}}
 table.t{{font-size:10px}} .foot{{margin-top:8px}}
}}
"""


def _li(items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def build_report(meta: dict, out_html: str | Path, pdf: bool = True) -> Path:
    """meta keys: code, title, subtitle, tags[list], warn_tag(optional), headline,
    tiles[list of (value,label)], question, data[list], method[list], figures[list of (path,caption)],
    table_html(optional), limitations[list], next[list], steps[list for flowchart], footer"""
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in meta.get("tags", []))
    if meta.get("warn_tag"):
        tags += f'<span class="tag warn">{html.escape(meta["warn_tag"])}</span>'
    tiles = "".join(f'<div class="tile"><div class="v">{v}</div><div class="l">{l}</div></div>'
                    for v, l in meta.get("tiles", []))
    figs = "".join(f'<figure><img src="{img_b64(p)}"><figcaption>{c}</figcaption></figure>'
                   for p, c in meta.get("figures", []))
    page1 = f"""
<div class="page">
 {tags}
 <h1>{meta['code']} · {meta['title']}</h1>
 <div class="sub">{meta['subtitle']}</div>
 <div class="headline">{meta['headline']}</div>
 <div class="tiles">{tiles}</div>
 <div class="grid2">
  <div>
   <h2>Question</h2><p style="margin:4px 0">{meta['question']}</p>
   <h2>Data</h2>{_li(meta['data'])}
   <h2>Method</h2>{_li(meta['method'])}
  </div>
  <div>
   <h2>Key result</h2>{figs}
   {meta.get('table_html','')}
  </div>
 </div>
 <div class="grid2">
  <div><h2>Limitations</h2>{_li(meta['limitations'])}</div>
  <div><h2>Next steps</h2>{_li(meta['next'])}</div>
 </div>
 <div class="foot">{meta.get('footer','')}</div>
</div>"""
    page2 = f"""
<div class="page pb">
 {tags}
 <h1>{meta['code']} · Procedure flowchart</h1>
 <div class="sub">Each step with the reasoning behind it. Left: what is done. Right: why.</div>
 {flowchart_svg(meta['steps'])}
 <div class="foot">{meta.get('footer','')}</div>
</div>"""
    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{meta['code']} · {html.escape(meta['title'])}</title><style>{CSS}</style></head>
<body>{page1}{page2}</body></html>"""
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(doc, encoding="utf-8")
    if pdf:
        from weasyprint import HTML
        HTML(string=doc).write_pdf(out_html.with_suffix(".pdf"))
    return out_html
