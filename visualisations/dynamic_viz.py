"""
visualisations/dynamic_viz.py
-----------------------------
Importable functions used by the Streamlit app to build visualisation HTML
on demand for any subject / course chosen via the sidebar.

Public API:
    build_evolution_html(subject_code, years=(2023,2024,2025,2026)) -> str
    build_prereq_tree_html(subject_code, year=2026) -> str
    build_sunburst_html(course_code, year=2026) -> str
    build_course_tree_html(course_code, year=2026) -> str
"""

from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO = Path(__file__).resolve().parent.parent
SUBJECTS_DIR = REPO / "dataset" / "subjects_archive"
COURSES_DIR = REPO / "dataset"


# ============================================================================
# Helpers
# ============================================================================

@lru_cache(maxsize=8)
def _load_subjects(year: int) -> dict:
    path = SUBJECTS_DIR / f"{year}_subjects.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _find_course_path(course_code: str, year: int) -> Path | None:
    for d in COURSES_DIR.iterdir():
        if d.is_dir() and d.name.startswith(course_code):
            p = d / f"{year}.json"
            if p.exists():
                return p
    return None


def _parse_cp(value) -> int:
    if not value:
        return 0
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else 0


SUBJECT_CODE_RE = re.compile(r"\b(\d{5}|[A-Z]{3,4}\d{4,5})\b")


# ============================================================================
# 1. Subject evolution timeline
# ============================================================================

def build_evolution_html(subject_code: str, years: Iterable[int] = (2023, 2024, 2025, 2026)) -> str:
    """Return a self-contained HTML page showing how a subject changed across years."""
    versions: dict[int, dict] = {}
    for y in years:
        s = _load_subjects(y).get(subject_code)
        if s is not None:
            versions[y] = s

    if not versions:
        return f"<div style='padding:24px;color:#a00;'>No data found for subject {subject_code} in years {list(years)}.</div>"

    subject_name = next(iter(versions.values())).get("name", subject_code)

    def metric_row(year, v):
        return dict(
            year=year,
            credit_points=_parse_cp(v.get("credit_points")),
            learning_outcomes=len(v.get("learning_outcomes") or []),
            description_chars=len(v.get("description") or ""),
            prerequisites=len(((v.get("requisite_list") or {}).get("requisite") or {}).get("items") or []),
            anti_requisites=len(((v.get("requisite_list") or {}).get("anti_requisite") or {}).get("items") or []),
        )

    df = pd.DataFrame([metric_row(y, v) for y, v in versions.items()])

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Credit points", "# of learning outcomes",
                        "Description length (characters)", "Pre / anti-requisite count"),
        vertical_spacing=0.18, horizontal_spacing=0.12,
    )
    fig.add_trace(go.Bar(x=df["year"], y=df["credit_points"], marker_color="#1abc9c", name="CP"), row=1, col=1)
    fig.add_trace(go.Bar(x=df["year"], y=df["learning_outcomes"], marker_color="#3498db", name="LOs"), row=1, col=2)
    fig.add_trace(go.Bar(x=df["year"], y=df["description_chars"], marker_color="#9b59b6", name="Desc len"), row=2, col=1)
    fig.add_trace(go.Bar(x=df["year"], y=df["prerequisites"], marker_color="#e67e22", name="Prereqs"), row=2, col=2)
    fig.add_trace(go.Bar(x=df["year"], y=df["anti_requisites"], marker_color="#c0392b", name="Anti-reqs"), row=2, col=2)

    fig.update_layout(
        showlegend=False, height=560, barmode="group",
        font=dict(family="Inter, Arial, sans-serif", size=12),
        margin=dict(t=60, l=40, r=40, b=40),
    )
    for r in (1, 2):
        for c in (1, 2):
            fig.update_xaxes(row=r, col=c, tickmode="array", tickvals=df["year"])

    chart_html = fig.to_html(include_plotlyjs=True, full_html=False)

    def diff_block(text_a, text_b, label_a, label_b):
        if not text_a and not text_b:
            return ""
        diff = list(difflib.unified_diff(
            (text_a or "").splitlines(), (text_b or "").splitlines(),
            fromfile=label_a, tofile=label_b, n=1, lineterm="",
        ))
        if not diff:
            return f"<div style='color:#999;font-style:italic;'>No changes between {label_a} and {label_b}</div>"
        out = []
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                out.append(f"<div style='color:#666;font-weight:600;margin-top:6px;'>{line}</div>")
            elif line.startswith("+"):
                out.append(f"<div style='background:#e8f5e9;color:#1b5e20;'>{line}</div>")
            elif line.startswith("-"):
                out.append(f"<div style='background:#ffebee;color:#b71c1c;'>{line}</div>")
            else:
                out.append(f"<div style='color:#444;'>{line}</div>")
        return "".join(out)

    sorted_years = sorted(versions.keys())
    diff_parts = []
    for ya, yb in zip(sorted_years, sorted_years[1:]):
        a, b = versions[ya], versions[yb]
        desc_diff = diff_block(a.get("description") or "", b.get("description") or "",
                               f"{ya} description", f"{yb} description")
        los_a = "\n".join(a.get("learning_outcomes") or [])
        los_b = "\n".join(b.get("learning_outcomes") or [])
        los_diff = diff_block(los_a, los_b, f"{ya} learning outcomes", f"{yb} learning outcomes")
        diff_parts.append(f"""
        <details {'open' if ya == sorted_years[0] else ''} style="margin-top:14px;">
          <summary style="cursor:pointer;font-size:14px;font-weight:600;padding:6px 10px;background:#f1f3f5;border-radius:6px;">
            {ya} &rarr; {yb}
          </summary>
          <div style="padding:10px 14px;font-family:'SF Mono', Menlo, Consolas, monospace;font-size:12px;line-height:1.5;background:#fff;border:1px solid #eee;border-radius:6px;margin-top:6px;">
            <div style="font-size:13px;font-weight:600;margin-bottom:6px;color:#333;font-family:Inter,sans-serif;">Description</div>
            {desc_diff}
            <div style="font-size:13px;font-weight:600;margin:14px 0 6px 0;color:#333;font-family:Inter,sans-serif;">Learning outcomes</div>
            {los_diff}
          </div>
        </details>
        """)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  body {{ font-family: Inter, Arial, sans-serif; margin: 0; padding: 16px; color: #222; background: #fafafa; }}
  h2 {{ font-size: 19px; margin: 0 0 4px 0; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 14px; }}
  .card {{ background: #fff; border-radius: 8px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 16px; }}
</style></head><body>
<h2>Subject evolution &middot; {subject_name} ({subject_code})</h2>
<div class="meta">Tracking how this subject changed across {sorted_years[0]}&ndash;{sorted_years[-1]}.</div>
<div class="card">{chart_html}</div>
<div class="card">
  <h3 style="font-size:16px;margin:0 0 4px 0;">What actually changed</h3>
  <div style="color:#666;font-size:13px;margin-bottom:6px;">Red lines were removed, green lines added. Click a year-pair to expand.</div>
  {''.join(diff_parts)}
</div>
</body></html>"""


# ============================================================================
# 2. Prerequisite tree (D3)
# ============================================================================

def _get_prereq_codes(subject, all_subjects):
    rl = subject.get("requisite_list") or {}
    out = []
    for item in (rl.get("requisite") or {}).get("items") or []:
        item_type = (item.get("type") or "").lower()
        if "academic" in item_type or "subject" in item_type or not item_type:
            for code in SUBJECT_CODE_RE.findall(item.get("details") or ""):
                if code in all_subjects:
                    out.append(code)
    return list(dict.fromkeys(out))


def _get_anti_codes(subject, all_subjects):
    rl = subject.get("requisite_list") or {}
    out = []
    for item in (rl.get("anti_requisite") or {}).get("items") or []:
        for code in SUBJECT_CODE_RE.findall(item.get("details") or ""):
            if code in all_subjects and code != subject.get("code"):
                out.append(code)
    return list(dict.fromkeys(out))


def build_prereq_tree_html(subject_code: str, year: int = 2026, max_depth: int = 4) -> str:
    """Return a D3 vertical prereq-tree HTML page for the given subject."""
    all_subjects = _load_subjects(year)
    if subject_code not in all_subjects:
        return f"<div style='padding:24px;color:#a00;'>Subject {subject_code} not in {year} archive.</div>"

    def build_node(code, depth=0, visited=None):
        if visited is None:
            visited = set()
        s = all_subjects.get(code, {})
        node = {
            "name": f"{code}  {s.get('name', code)}",
            "code": code,
            "subject_name": s.get("name", code),
            "faculty": s.get("faculty", "—"),
            "cp": s.get("credit_points", "—"),
            "antis": _get_anti_codes(s, all_subjects),
            "children": [],
        }
        if depth >= max_depth or code in visited:
            return node
        visited = visited | {code}
        for p in _get_prereq_codes(s, all_subjects):
            node["children"].append(build_node(p, depth + 1, visited))
        return node

    tree_data = build_node(subject_code)
    name = all_subjects[subject_code].get("name", subject_code)
    tree_json = json.dumps(tree_data)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>if(typeof d3==='undefined')document.write('<script src="https://unpkg.com/d3@7/dist/d3.min.js"><\\/script>');</script>
<style>
  body {{ font-family: Inter, Arial, sans-serif; margin: 0; padding: 0; background: #fafafa; color: #222; }}
  header {{ padding: 12px 18px; background: #fff; border-bottom: 1px solid #e5e5e5; }}
  header h1 {{ margin: 0 0 3px 0; font-size: 17px; }}
  header p {{ margin: 0; color: #666; font-size: 12px; }}
  #tree-container {{ width: 100vw; height: calc(100vh - 60px); overflow: hidden; background: #fafafa; }}
  .node circle {{ stroke: #fff; stroke-width: 2px; }}
  .node--root circle {{ fill: #2c3e50; }}
  .node--internal circle {{ fill: #3498db; cursor: pointer; }}
  .node--leaf circle {{ fill: #27ae60; }}
  .node text {{ font-size: 12px; pointer-events: none; }}
  .link {{ fill: none; stroke: #bbb; stroke-width: 1.6; }}
  #tooltip {{ position: absolute; pointer-events: none; background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; max-width: 320px; box-shadow: 0 4px 12px rgba(0,0,0,0.18); opacity: 0; transition: opacity 0.15s; }}
</style></head>
<body>
<header><h1>Prerequisite tree &middot; {name} ({subject_code}) &middot; {year}</h1>
<p>Vertical D3 tree. Target subject at the top, prerequisites branch downward. Click a blue node to collapse / expand.</p>
</header>
<div id="tree-container"></div>
<div id="tooltip"></div>
<script>
const data = {tree_json};
const container = document.getElementById('tree-container');
const tooltip = document.getElementById('tooltip');
const margin = {{top: 50, right: 40, bottom: 50, left: 40}};
let width = container.clientWidth - margin.left - margin.right;
const svg = d3.select('#tree-container').append('svg').attr('width', container.clientWidth).attr('height', container.clientHeight);
const zoomG = svg.append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);
svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', ev => zoomG.attr('transform', ev.transform)));
let root = d3.hierarchy(data);
let i = 0;
root.descendants().forEach(d => {{ if (d.depth > 1 && d.children) {{ d._children = d.children; d.children = null; }} }});
const tree = d3.tree().nodeSize([200, 110]);
function update(source) {{
  tree(root);
  const nodes = root.descendants();
  const links = root.links();
  let xMin=Infinity, xMax=-Infinity;
  nodes.forEach(d => {{ if(d.x<xMin)xMin=d.x; if(d.x>xMax)xMax=d.x; }});
  const xOff = -((xMin+xMax)/2) + width/2;
  nodes.forEach(d => d.x += xOff);
  const link = zoomG.selectAll('path.link').data(links, d => d.target.data.code);
  link.enter().append('path').attr('class','link').attr('d', d3.linkVertical().x(d=>d.x).y(d=>d.y))
    .merge(link).transition().duration(300).attr('d', d3.linkVertical().x(d=>d.x).y(d=>d.y));
  link.exit().remove();
  const node = zoomG.selectAll('g.node').data(nodes, d => d.data.code || (d.id = ++i));
  const nE = node.enter().append('g')
    .attr('class', d => 'node ' + (d.depth===0?'node--root':(d._children||d.children?'node--internal':'node--leaf')))
    .attr('transform', d => `translate(${{d.x}},${{d.y}})`)
    .on('click', (ev,d) => {{ if(d.children){{d._children=d.children;d.children=null;}}else if(d._children){{d.children=d._children;d._children=null;}} update(d); }})
    .on('mouseover', (ev,d) => {{
      const a = d.data.antis && d.data.antis.length ? `<div style="color:#fbbf24;margin-top:4px;">Anti-reqs: ${{d.data.antis.join(', ')}}</div>` : '';
      tooltip.innerHTML = `<strong>${{d.data.subject_name}}</strong><br>Code: ${{d.data.code}}<br>Faculty: ${{d.data.faculty}}<br>CP: ${{d.data.cp}}${{a}}`;
      tooltip.style.opacity = 1;
    }})
    .on('mousemove', ev => {{ tooltip.style.left=(ev.pageX+14)+'px'; tooltip.style.top=(ev.pageY+14)+'px'; }})
    .on('mouseout', () => tooltip.style.opacity=0);
  nE.append('circle').attr('r', 9);
  nE.append('text').attr('y', 26).attr('text-anchor','middle').attr('font-weight',600).attr('fill','#222').text(d => d.data.code);
  nE.append('text').attr('y', 42).attr('text-anchor','middle').attr('fill','#555').text(d => {{ const n=d.data.subject_name||''; return n.length>28?n.slice(0,26)+'...':n; }});
  nE.filter(d => d._children).append('text').attr('y',4).attr('text-anchor','middle').attr('fill','#fff').attr('font-weight',700).attr('font-size',10).text('+');
  node.merge(nE).transition().duration(300).attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  node.exit().remove();
}}
update(root);
</script></body></html>"""


# ============================================================================
# 3. Course sunburst (Plotly)
# ============================================================================

def _walk_course(node, parent_label, rows, depth=0, max_depth=4):
    if depth > max_depth:
        return
    if "structure_name" in node:
        label = node["structure_name"]
        my_id = f"{parent_label} / {label}"
        rows.append(dict(id=my_id, parent=parent_label, label=label, value=0, level="block"))
        for k, recurse_into in (("has_subject", True), ("has_area_of_study", True),
                                ("have_sub_structures", True), ("has_choice_block", True)):
            for child in node.get(k) or []:
                _walk_course(child, my_id, rows, depth + 1, max_depth)
    elif node.get("type") in ("Sub-Major", "Major", "Specialisation") or "have_structure" in node:
        label = node.get("name") or node.get("code", "AOS")
        my_id = f"{parent_label} / {label}"
        rows.append(dict(id=my_id, parent=parent_label, label=label, value=0, level="aos"))
        for child in node.get("have_structure") or []:
            _walk_course(child, my_id, rows, depth + 1, max_depth)
    else:
        label = f"{node.get('code','?')} {node.get('name','')}".strip()
        cp = _parse_cp(node.get("credit_points")) or 6
        my_id = f"{parent_label} / {label}"
        rows.append(dict(id=my_id, parent=parent_label, label=label, value=cp, level="subject"))


def _patch_missing(df: pd.DataFrame) -> pd.DataFrame:
    children_of = defaultdict(list)
    for _, r in df.iterrows():
        if r["parent"]:
            children_of[r["parent"]].append(r["id"])
    node_level = dict(zip(df["id"], df["level"]))

    def has_subj_descendant(nid):
        for c in children_of.get(nid, []):
            if node_level.get(c) == "subject" or has_subj_descendant(c):
                return True
        return False

    extras = []
    for _, r in df.iterrows():
        if r["level"] in ("block", "aos") and not has_subj_descendant(r["id"]):
            extras.append(dict(id=f"{r['id']} / __missing__", parent=r["id"],
                               label="(scraper data missing)", value=1, level="missing"))
    if extras:
        df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    return df


def build_sunburst_html(course_code: str, year: int = 2026) -> str:
    json_path = _find_course_path(course_code, year)
    if json_path is None:
        return f"<div style='padding:24px;color:#a00;'>Course {course_code} ({year}) not found in dataset/.</div>"

    course = json.loads(json_path.read_text(encoding="utf-8"))
    course_label = course["course_name"]
    rows = [dict(id=course_label, parent="", label=course_label, value=0, level="course")]
    for block in course["structure"]:
        _walk_course(block, course_label, rows)

    df = pd.DataFrame(rows).drop_duplicates(subset=["id"])
    df = _patch_missing(df)

    fig = px.sunburst(
        df, ids="id", names="label", parents="parent", values="value",
        color="level",
        color_discrete_map={"course": "#2c3e50", "block": "#3498db", "aos": "#9b59b6",
                            "subject": "#1abc9c", "missing": "#cccccc"},
        branchvalues="remainder",
        hover_data={"id": False, "parent": False, "level": True, "value": ":.0f"},
    )
    fig.update_layout(
        title=dict(text=f"<b>{course_label}</b> ({course_code}) - {year}<br>"
                        f"<span style='font-size:12px;color:#666;'>Click any wedge to zoom in. Grey = scraped data missing.</span>",
                   x=0.02, xanchor="left"),
        margin=dict(t=80, l=20, r=20, b=20),
        font=dict(family="Inter, Arial, sans-serif", size=12),
        height=820,
    )
    fig.update_traces(hovertemplate="<b>%{label}</b><br>%{value} CP<br>type: %{customdata[0]}<extra></extra>",
                      insidetextorientation="radial")
    return fig.to_html(include_plotlyjs=True, full_html=True)


# ============================================================================
# 4. Course tree (D3)
# ============================================================================

def _build_course_tree_node(node):
    if "structure_name" in node:
        children = []
        for k in ("has_subject", "has_area_of_study", "have_sub_structures", "has_choice_block"):
            for c in node.get(k) or []:
                children.append(_build_course_tree_node(c))
        return {"name": node["structure_name"], "level": "block",
                "cp": node.get("structure_cp", ""), "children": children}
    if node.get("type") in ("Sub-Major", "Major", "Specialisation") or "have_structure" in node:
        children = [_build_course_tree_node(s) for s in (node.get("have_structure") or [])]
        return {"name": node.get("name") or node.get("code", "AOS"), "level": "aos",
                "code": node.get("code"), "cp": node.get("credit_points", ""), "children": children}
    return {"name": f"{node.get('code','?')} {node.get('name','')}".strip(),
            "level": "subject", "code": node.get("code"),
            "cp": node.get("credit_points", ""), "faculty": node.get("faculty"),
            "study_level": node.get("study_level")}


def _patch_missing_tree(node):
    if node.get("level") in ("block", "aos"):
        if not _has_subj_desc(node):
            node["children"] = (node.get("children") or []) + [{"name": "(scraper data missing)", "level": "missing"}]
            return
    for c in node.get("children") or []:
        _patch_missing_tree(c)


def _has_subj_desc(node):
    if node.get("level") == "subject":
        return True
    for c in node.get("children") or []:
        if _has_subj_desc(c):
            return True
    return False


def build_course_tree_html(course_code: str, year: int = 2026) -> str:
    json_path = _find_course_path(course_code, year)
    if json_path is None:
        return f"<div style='padding:24px;color:#a00;'>Course {course_code} ({year}) not found in dataset/.</div>"

    course = json.loads(json_path.read_text(encoding="utf-8"))
    root = {"name": course["course_name"], "level": "course", "code": course["course_code"],
            "children": [_build_course_tree_node(b) for b in course["structure"]]}
    _patch_missing_tree(root)
    tree_json = json.dumps(root)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>if(typeof d3==='undefined')document.write('<script src="https://unpkg.com/d3@7/dist/d3.min.js"><\\/script>');</script>
<style>
  body {{ font-family: Inter, Arial, sans-serif; margin: 0; padding: 0; background: #fafafa; color: #222; }}
  header {{ padding: 12px 18px; background: #fff; border-bottom: 1px solid #e5e5e5; }}
  header h1 {{ margin: 0 0 3px 0; font-size: 17px; }}
  header p {{ margin: 0; color: #666; font-size: 12px; }}
  .legend {{ margin-top: 6px; font-size: 11px; color: #666; }}
  .legend span {{ margin-right: 14px; }}
  .legend i {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%; vertical-align: middle; margin-right: 4px; }}
  .controls {{ margin-top: 6px; }}
  .controls button {{ padding: 5px 10px; margin-right: 6px; border: 1px solid #ddd; background: #fff; border-radius: 4px; font-size: 11px; cursor: pointer; font-family: inherit; }}
  .controls button:hover {{ background: #f5f5f5; }}
  #tree-container {{ width: 100vw; height: calc(100vh - 100px); overflow: hidden; background: #fafafa; }}
  .node circle {{ stroke: #fff; stroke-width: 2px; }}
  .node--course circle {{ fill: #2c3e50; }}
  .node--block circle {{ fill: #3498db; cursor: pointer; }}
  .node--aos circle {{ fill: #9b59b6; cursor: pointer; }}
  .node--subject circle {{ fill: #1abc9c; }}
  .node--missing circle {{ fill: #cccccc; }}
  .node text {{ font-size: 11px; pointer-events: none; }}
  .link {{ fill: none; stroke: #ccc; stroke-width: 1.4; }}
  #tooltip {{ position: absolute; pointer-events: none; background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; max-width: 320px; box-shadow: 0 4px 12px rgba(0,0,0,0.18); opacity: 0; transition: opacity 0.15s; }}
</style></head>
<body>
<header><h1>Course tree &middot; {course['course_name']} ({course_code}) {year}</h1>
<p>Top-down D3 hierarchy. Click any blue / purple node to expand. Scroll to zoom, drag to pan.</p>
<div class="legend">
  <span><i style="background:#2c3e50"></i>course</span>
  <span><i style="background:#3498db"></i>block</span>
  <span><i style="background:#9b59b6"></i>sub-major</span>
  <span><i style="background:#1abc9c"></i>subject</span>
  <span><i style="background:#cccccc"></i>scraper data missing</span>
</div>
<div class="controls">
  <button id="exp">Expand all</button>
  <button id="col">Collapse to depth 2</button>
  <button id="rst">Reset view</button>
</div>
</header>
<div id="tree-container"></div><div id="tooltip"></div>
<script>
const data = {tree_json};
const container = document.getElementById('tree-container');
const tooltip = document.getElementById('tooltip');
const svg = d3.select('#tree-container').append('svg').attr('width', container.clientWidth).attr('height', container.clientHeight);
const zoomG = svg.append('g');
const zb = d3.zoom().scaleExtent([0.2, 3]).on('zoom', ev => zoomG.attr('transform', ev.transform));
svg.call(zb);
let root = d3.hierarchy(data);
let i = 0;
function collapseTo(d, max) {{ if (d.depth >= max && d.children) {{ d._children = d.children; d.children = null; }} (d.children || d._children || []).forEach(c => collapseTo(c, max)); }}
function expandAll(d) {{ if (d._children) {{ d.children = d._children; d._children = null; }} (d.children || []).forEach(expandAll); }}
collapseTo(root, 2);
const tree = d3.tree().nodeSize([170, 140]);
function update(source) {{
  tree(root);
  const nodes = root.descendants();
  const links = root.links();
  let xMin=Infinity, xMax=-Infinity;
  nodes.forEach(d => {{ if(d.x<xMin)xMin=d.x; if(d.x>xMax)xMax=d.x; }});
  const xOff = -((xMin+xMax)/2) + container.clientWidth/2;
  nodes.forEach(d => {{ d.x += xOff; d.y += 30; }});
  const link = zoomG.selectAll('path.link').data(links, d => d.target.__id || (d.target.__id = ++i));
  link.enter().append('path').attr('class','link').attr('d', d3.linkVertical().x(d=>d.x).y(d=>d.y))
    .merge(link).transition().duration(300).attr('d', d3.linkVertical().x(d=>d.x).y(d=>d.y));
  link.exit().remove();
  const node = zoomG.selectAll('g.node').data(nodes, d => d.__id || (d.__id = ++i));
  const nE = node.enter().append('g')
    .attr('class', d => 'node node--' + d.data.level)
    .attr('transform', d => `translate(${{d.x}},${{d.y}})`)
    .on('click', (ev,d) => {{ if(d.data.level==='subject'||d.data.level==='missing')return; if(d.children){{d._children=d.children;d.children=null;}}else if(d._children){{d.children=d._children;d._children=null;}} update(d); }})
    .on('mouseover', (ev,d) => {{
      const lines = [`<strong>${{d.data.name}}</strong>`, `Type: ${{d.data.level}}`];
      if (d.data.cp) lines.push(`CP: ${{d.data.cp}}`);
      if (d.data.code) lines.push(`Code: ${{d.data.code}}`);
      if (d.data.faculty) lines.push(`Faculty: ${{d.data.faculty}}`);
      if (d._children) lines.push(`<span style="color:#9ca3af;">[${{d._children.length}} hidden - click to expand]</span>`);
      tooltip.innerHTML = lines.join('<br>'); tooltip.style.opacity = 1;
    }})
    .on('mousemove', ev => {{ tooltip.style.left=(ev.pageX+14)+'px'; tooltip.style.top=(ev.pageY+14)+'px'; }})
    .on('mouseout', () => tooltip.style.opacity=0);
  nE.append('circle').attr('r', d => d.depth===0 ? 11 : (d.data.level==='subject'||d.data.level==='missing' ? 5 : 8));
  nE.append('text')
    .attr('y', d => d.children || d._children ? -14 : 18)
    .attr('text-anchor', d => d.data.level==='subject'||d.data.level==='missing' ? 'end' : 'middle')
    .attr('transform', d => d.data.level==='subject'||d.data.level==='missing' ? 'rotate(-35)' : null)
    .attr('fill','#222')
    .text(d => {{
      if (d.data.level==='subject') return d.data.code || (d.data.name || '').split(' ')[0];
      if (d.data.level==='missing') return '(no data)';
      const n = d.data.name || '';
      return n.length > 32 ? n.slice(0, 30) + '...' : n;
    }});
  nE.filter(d => d._children).append('text').attr('y',4).attr('text-anchor','middle').attr('fill','#fff').attr('font-weight',700).attr('font-size',10).text('+');
  node.merge(nE).transition().duration(300).attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  node.exit().remove();
}}
update(root);
setTimeout(() => {{
  const bb = zoomG.node().getBBox();
  const sc = Math.min(container.clientWidth/(bb.width+80), container.clientHeight/(bb.height+80), 1.2);
  const tx = container.clientWidth/2 - sc*(bb.x+bb.width/2);
  const ty = 60 - sc*bb.y;
  svg.transition().duration(400).call(zb.transform, d3.zoomIdentity.translate(tx,ty).scale(sc));
}}, 350);
document.getElementById('exp').onclick = () => {{ expandAll(root); update(root); }};
document.getElementById('col').onclick = () => {{ collapseTo(root, 2); update(root); }};
document.getElementById('rst').onclick = () => document.getElementById('col').click();
</script></body></html>"""
