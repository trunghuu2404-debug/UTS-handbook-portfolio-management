"""
backend/visualizations/dynamic_viz.py
---------------------------------------
Builds visualization HTML for subjects and courses.
Data is sourced from Neo4j via viz_service — no file reading here.

Public API (identical signatures to the original dynamic_viz.py):
    build_evolution_html(subject_code, years=(2023,2024,2025,2026)) -> str
    build_prereq_tree_html(subject_code, year=2026, max_depth=4) -> str
    build_sunburst_html(course_code, year=2026) -> str
    build_course_tree_html(course_code, year=2026) -> str
"""

from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict
from functools import lru_cache

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from services.viz_service import (
    build_prereq_tree_dict,
    get_course_data,
    get_subject_versions_all,
)

# ============================================================================
# Internal helpers
# ============================================================================


def _parse_cp(value) -> int:
    if not value:
        return 0
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else 0


def _patch_missing_df(df: pd.DataFrame) -> pd.DataFrame:
    """Inject placeholder wedges for structure blocks that have no subject leaves."""
    children_of: dict = defaultdict(list)
    for _, r in df.iterrows():
        if r["parent"]:
            children_of[r["parent"]].append(r["id"])
    node_level = dict(zip(df["id"], df["level"]))

    def has_subj_desc(nid: str) -> bool:
        for c in children_of.get(nid, []):
            if node_level.get(c) == "subject" or has_subj_desc(c):
                return True
        return False

    extras = []
    for _, r in df.iterrows():
        if r["level"] in ("block", "aos") and not has_subj_desc(r["id"]):
            extras.append(
                dict(
                    id=f"{r['id']} / __missing__",
                    parent=r["id"],
                    label="(no data in graph)",
                    value=1,
                    level="missing",
                )
            )
    if extras:
        df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    return df


def _patch_missing_tree(node: dict) -> None:
    """Inject placeholder leaf for any tree block with no subject descendants."""

    def _has_subj(n: dict) -> bool:
        if n.get("level") == "subject":
            return True
        return any(_has_subj(c) for c in (n.get("children") or []))

    if node.get("level") in ("block", "aos") and not _has_subj(node):
        node["children"] = (node.get("children") or []) + [
            {"name": "(no data in graph)", "level": "missing"}
        ]
        return
    for c in node.get("children") or []:
        _patch_missing_tree(c)


# ============================================================================
# 1. Subject evolution timeline
# ============================================================================


@lru_cache(maxsize=128)
def build_evolution_html(
    subject_code: str,
    years: tuple = (2023, 2024, 2025, 2026),
) -> str:
    """Return a self-contained HTML page showing how a subject changed across years."""
    all_versions = get_subject_versions_all(subject_code)
    versions = {y: all_versions[y] for y in sorted(years) if y in all_versions}

    if not versions:
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"No data for subject {subject_code} in years {list(years)}.</div>"
        )

    subject_name = next(iter(versions.values())).get("name", subject_code)

    # Build metrics dataframe
    rows = []
    for year, v in versions.items():
        rows.append(
            dict(
                year=year,
                credit_points=_parse_cp(v.get("credit_points")),
                learning_outcomes=len(v.get("learning_outcomes") or []),
                description_chars=len(v.get("description") or ""),
                prerequisites=v.get("prereq_count", 0),
                anti_requisites=v.get("anti_count", 0),
            )
        )
    df = pd.DataFrame(rows)

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Credit points",
            "# of learning outcomes",
            "Description length (characters)",
            "Pre / anti-requisite count",
        ),
        vertical_spacing=0.18,
        horizontal_spacing=0.12,
    )
    fig.add_trace(
        go.Bar(x=df["year"], y=df["credit_points"], marker_color="#1abc9c", name="CP"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df["year"], y=df["learning_outcomes"], marker_color="#3498db", name="LOs"
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            x=df["year"], y=df["description_chars"], marker_color="#9b59b6", name="Desc"
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df["year"], y=df["prerequisites"], marker_color="#e67e22", name="Prereqs"
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            x=df["year"], y=df["anti_requisites"], marker_color="#c0392b", name="Anti"
        ),
        row=2,
        col=2,
    )
    fig.update_layout(
        showlegend=False,
        height=560,
        barmode="group",
        font=dict(family="Inter, Arial, sans-serif", size=12),
        margin=dict(t=60, l=40, r=40, b=40),
    )
    for r in (1, 2):
        for c in (1, 2):
            fig.update_xaxes(row=r, col=c, tickmode="array", tickvals=df["year"])

    chart_html = fig.to_html(include_plotlyjs=True, full_html=False)

    # Text diff panel
    def diff_block(text_a: str, text_b: str, label_a: str, label_b: str) -> str:
        if not text_a and not text_b:
            return ""
        diff = list(
            difflib.unified_diff(
                (text_a or "").splitlines(),
                (text_b or "").splitlines(),
                fromfile=label_a,
                tofile=label_b,
                n=1,
                lineterm="",
            )
        )
        if not diff:
            return (
                f"<div style='color:#999;font-style:italic;'>"
                f"No changes between {label_a} and {label_b}</div>"
            )
        out = []
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                out.append(
                    f"<div style='color:#666;font-weight:600;margin-top:6px;'>{line}</div>"
                )
            elif line.startswith("+"):
                out.append(
                    f"<div style='background:#e8f5e9;color:#1b5e20;'>{line}</div>"
                )
            elif line.startswith("-"):
                out.append(
                    f"<div style='background:#ffebee;color:#b71c1c;'>{line}</div>"
                )
            else:
                out.append(f"<div style='color:#444;'>{line}</div>")
        return "".join(out)

    sorted_years = sorted(versions.keys())
    diff_parts = []
    for ya, yb in zip(sorted_years, sorted_years[1:]):
        a, b = versions[ya], versions[yb]
        desc_diff = diff_block(
            a.get("description") or "",
            b.get("description") or "",
            f"{ya} description",
            f"{yb} description",
        )
        los_a = "\n".join(a.get("learning_outcomes") or [])
        los_b = "\n".join(b.get("learning_outcomes") or [])
        los_diff = diff_block(
            los_a, los_b, f"{ya} learning outcomes", f"{yb} learning outcomes"
        )
        diff_parts.append(f"""
        <details {'open' if ya == sorted_years[0] else ''} style="margin-top:14px;">
          <summary style="cursor:pointer;font-size:14px;font-weight:600;padding:6px 10px;background:#f1f3f5;border-radius:6px;">
            {ya} &rarr; {yb}
          </summary>
          <div style="padding:10px 14px;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;
                      line-height:1.5;background:#fff;border:1px solid #eee;border-radius:6px;margin-top:6px;">
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
  h2   {{ font-size: 19px; margin: 0 0 4px 0; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 14px; }}
  .card {{ background: #fff; border-radius: 8px; padding: 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 16px; }}
</style></head><body>
<h2>Subject evolution &middot; {subject_name} ({subject_code})</h2>
<div class="meta">Tracking how this subject changed across {sorted_years[0]}&ndash;{sorted_years[-1]}.</div>
<div class="card">{chart_html}</div>
<div class="card">
  <h3 style="font-size:16px;margin:0 0 4px 0;">What actually changed</h3>
  <div style="color:#666;font-size:13px;margin-bottom:6px;">Red = removed, green = added. Click a year pair to expand.</div>
  {"".join(diff_parts)}
</div>
</body></html>"""


# ============================================================================
# 2. Prerequisite tree (D3)
# ============================================================================


def build_prereq_tree_html(
    subject_code: str,
    year: int = 2026,
    max_depth: int = 4,
) -> str:
    """Return a D3 vertical prereq-tree HTML page for the given subject."""
    tree_data = build_prereq_tree_dict(subject_code, year, max_depth)
    if tree_data is None:
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"Subject {subject_code} not found for year {year}.</div>"
        )

    name = tree_data.get("subject_name", subject_code)
    tree_json = json.dumps(tree_data)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>if(typeof d3==='undefined')document.write('<script src="https://unpkg.com/d3@7/dist/d3.min.js"><\\/script>');</script>
<style>
  body {{ font-family: Inter, Arial, sans-serif; margin: 0; padding: 0; background: #fafafa; color: #222; }}
  header {{ padding: 12px 18px; background: #fff; border-bottom: 1px solid #e5e5e5; }}
  header h1 {{ margin: 0 0 3px 0; font-size: 17px; }}
  header p  {{ margin: 0; color: #666; font-size: 12px; }}
  #tree-container {{ width: 100vw; height: calc(100vh - 60px); overflow: hidden; }}
  .node circle {{ stroke: #fff; stroke-width: 2px; }}
  .node--root circle     {{ fill: #2c3e50; }}
  .node--internal circle {{ fill: #3498db; cursor: pointer; }}
  .node--leaf circle     {{ fill: #27ae60; }}
  .node text {{ font-size: 12px; pointer-events: none; }}
  .link {{ fill: none; stroke: #bbb; stroke-width: 1.6; }}
  #tooltip {{
    position: absolute; pointer-events: none;
    background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 6px;
    font-size: 12px; line-height: 1.5; max-width: 320px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18); opacity: 0; transition: opacity 0.15s;
  }}
</style></head>
<body>
<header>
  <h1>Prerequisite tree &middot; {name} ({subject_code}) &middot; {year}</h1>
  <p>Target subject at top, prerequisites branch downward. Click a blue node to collapse / expand.</p>
</header>
<div id="tree-container"></div>
<div id="tooltip"></div>
<script>
const data = {tree_json};
const container = document.getElementById('tree-container');
const tooltip  = document.getElementById('tooltip');
const margin = {{top:50,right:40,bottom:50,left:40}};
let width = container.clientWidth - margin.left - margin.right;
const svg = d3.select('#tree-container').append('svg')
  .attr('width', container.clientWidth).attr('height', container.clientHeight);
const zoomG = svg.append('g').attr('transform',`translate(${{margin.left}},${{margin.top}})`);
svg.call(d3.zoom().scaleExtent([0.3,3]).on('zoom', ev => zoomG.attr('transform', ev.transform)));
let root = d3.hierarchy(data);
let i = 0;
root.descendants().forEach(d => {{ if (d.depth > 1 && d.children) {{ d._children = d.children; d.children = null; }} }});
const tree = d3.tree().nodeSize([200,110]);
function update(source) {{
  tree(root);
  const nodes = root.descendants();
  const links = root.links();
  let xMin=Infinity, xMax=-Infinity;
  nodes.forEach(d => {{ if(d.x<xMin)xMin=d.x; if(d.x>xMax)xMax=d.x; }});
  const xOff = -((xMin+xMax)/2) + width/2;
  nodes.forEach(d => d.x += xOff);
  const link = zoomG.selectAll('path.link').data(links, d => d.target.data.code);
  link.enter().append('path').attr('class','link')
    .attr('d', d3.linkVertical().x(d=>d.x).y(d=>d.y))
    .merge(link).transition().duration(300)
    .attr('d', d3.linkVertical().x(d=>d.x).y(d=>d.y));
  link.exit().remove();
  const node = zoomG.selectAll('g.node').data(nodes, d => d.data.code || (d.id = ++i));
  const nE = node.enter().append('g')
    .attr('class', d => 'node ' + (d.depth===0 ? 'node--root' : (d._children||d.children ? 'node--internal' : 'node--leaf')))
    .attr('transform', d => `translate(${{d.x}},${{d.y}})`)
    .on('click', (ev,d) => {{
      if (d.children) {{ d._children=d.children; d.children=null; }}
      else if (d._children) {{ d.children=d._children; d._children=null; }}
      update(d);
    }})
    .on('mouseover', (ev,d) => {{
      const a = d.data.antis && d.data.antis.length
        ? `<div style="color:#fbbf24;margin-top:4px;">Anti-reqs: ${{d.data.antis.join(', ')}}</div>` : '';
      tooltip.innerHTML = `<strong>${{d.data.subject_name}}</strong><br>Code: ${{d.data.code}}<br>Faculty: ${{d.data.faculty}}<br>CP: ${{d.data.cp}}${{a}}`;
      tooltip.style.opacity = 1;
    }})
    .on('mousemove', ev => {{ tooltip.style.left=(ev.pageX+14)+'px'; tooltip.style.top=(ev.pageY+14)+'px'; }})
    .on('mouseout', () => tooltip.style.opacity=0);
  nE.append('circle').attr('r', 9);
  nE.append('text').attr('y',26).attr('text-anchor','middle').attr('font-weight',600).attr('fill','#222')
    .text(d => d.data.code);
  nE.append('text').attr('y',42).attr('text-anchor','middle').attr('fill','#555')
    .text(d => {{ const n=d.data.subject_name||''; return n.length>28 ? n.slice(0,26)+'...' : n; }});
  nE.filter(d => d._children).append('text').attr('y',4).attr('text-anchor','middle')
    .attr('fill','#fff').attr('font-weight',700).attr('font-size',10).text('+');
  node.merge(nE).transition().duration(300).attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  node.exit().remove();
}}
update(root);
window.addEventListener('resize', () => {{
  width = container.clientWidth - margin.left - margin.right;
  svg.attr('width', container.clientWidth).attr('height', container.clientHeight);
  update(root);
}});
</script></body></html>"""


# ============================================================================
# 3. Course sunburst (Plotly)
# ============================================================================


def _walk_course(
    node: dict, parent_label: str, rows: list, depth: int = 0, max_depth: int = 12
) -> None:
    if depth > max_depth:
        return
    if "structure_name" in node:
        label = node["structure_name"]
        my_id = f"{parent_label} / {label}"
        rows.append(
            dict(id=my_id, parent=parent_label, label=label, value=0, level="block")
        )
        for k in (
            "has_subject",
            "has_area_of_study",
            "have_sub_structures",
            "has_choice_block",
        ):
            for child in node.get(k) or []:
                _walk_course(child, my_id, rows, depth + 1, max_depth)
    elif (
        node.get("type") in ("Sub-Major", "Major", "Specialisation")
        or "have_structure" in node
    ):
        label = node.get("name") or node.get("code", "AOS")
        my_id = f"{parent_label} / {label}"
        rows.append(
            dict(id=my_id, parent=parent_label, label=label, value=0, level="aos")
        )
        for child in node.get("have_structure") or []:
            _walk_course(child, my_id, rows, depth + 1, max_depth)
    else:
        label = f"{node.get('code','?')} {node.get('name','')}".strip()
        cp = _parse_cp(node.get("credit_points")) or 6
        my_id = f"{parent_label} / {label}"
        rows.append(
            dict(id=my_id, parent=parent_label, label=label, value=cp, level="subject")
        )


@lru_cache(maxsize=32)
def build_sunburst_html(course_code: str, year: int = 2026) -> str:
    """Return a self-contained Plotly sunburst HTML page for the given course."""
    course = get_course_data(course_code, year)
    if course is None:
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"Course {course_code} ({year}) not found.</div>"
        )

    course_label = course["course_name"]
    rows = [
        dict(id=course_label, parent="", label=course_label, value=0, level="course")
    ]
    for block in course["structure"]:
        _walk_course(block, course_label, rows, max_depth=12)

    df = pd.DataFrame(rows).drop_duplicates(subset=["id"])
    df = _patch_missing_df(df)

    fig = px.sunburst(
        df,
        ids="id",
        names="label",
        parents="parent",
        values="value",
        color="level",
        color_discrete_map={
            "course": "#2c3e50",
            "block": "#3498db",
            "aos": "#9b59b6",
            "subject": "#1abc9c",
            "missing": "#cccccc",
        },
        branchvalues="remainder",
        hover_data={"id": False, "parent": False, "level": True, "value": ":.0f"},
    )
    fig.update_layout(
        title=dict(
            text=(
                f"<b>{course_label}</b> ({course_code}) - {year}<br>"
                f"<span style='font-size:12px;color:#666;'>"
                f"Segment size = credit points. Click to zoom in. Grey = no data in graph.</span>"
            ),
            x=0.02,
            xanchor="left",
        ),
        margin=dict(t=80, l=20, r=20, b=20),
        font=dict(family="Inter, Arial, sans-serif", size=12),
        height=820,
    )
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>%{value} CP<br>type: %{customdata[0]}<extra></extra>",
        insidetextorientation="radial",
    )
    return fig.to_html(include_plotlyjs=True, full_html=True)


# ============================================================================
# 4. Course tree (D3)
# ============================================================================


def _build_course_tree_node(node: dict) -> dict:
    if "structure_name" in node:
        children = []
        for k in (
            "has_subject",
            "has_area_of_study",
            "have_sub_structures",
            "has_choice_block",
        ):
            for c in node.get(k) or []:
                children.append(_build_course_tree_node(c))
        return {
            "name": node["structure_name"],
            "level": "block",
            "cp": node.get("structure_cp", ""),
            "children": children,
        }
    if (
        node.get("type") in ("Sub-Major", "Major", "Specialisation")
        or "have_structure" in node
    ):
        children = [
            _build_course_tree_node(s) for s in (node.get("have_structure") or [])
        ]
        return {
            "name": node.get("name") or node.get("code", "AOS"),
            "level": "aos",
            "code": node.get("code"),
            "cp": node.get("credit_points", ""),
            "children": children,
        }
    return {
        "name": f"{node.get('code','?')} {node.get('name','')}".strip(),
        "level": "subject",
        "code": node.get("code"),
        "cp": node.get("credit_points", ""),
        "faculty": node.get("faculty"),
        "study_level": node.get("study_level"),
    }


@lru_cache(maxsize=32)
def build_course_tree_html(course_code: str, year: int = 2026) -> str:
    """Return a self-contained D3 course-tree HTML page for the given course."""
    course = get_course_data(course_code, year)
    if course is None:
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"Course {course_code} ({year}) not found.</div>"
        )

    root = {
        "name": course["course_name"],
        "level": "course",
        "code": course["course_code"],
        "children": [_build_course_tree_node(b) for b in course["structure"]],
    }
    _patch_missing_tree(root)
    tree_json = json.dumps(root)
    course_name = course["course_name"]

    return f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>if(typeof d3==='undefined')document.write('<script src="https://unpkg.com/d3@7/dist/d3.min.js"><\\/script>');</script>
<style>
  body {{ font-family: Inter, Arial, sans-serif; margin: 0; padding: 0; background: #fafafa; color: #222; }}
  header {{ padding: 12px 18px; background: #fff; border-bottom: 1px solid #e5e5e5; }}
  header h1 {{ margin: 0 0 3px 0; font-size: 17px; }}
  header p  {{ margin: 0; color: #666; font-size: 12px; }}
  .legend {{ margin-top: 6px; font-size: 11px; color: #666; }}
  .legend span {{ margin-right: 14px; }}
  .legend i {{ display:inline-block; width:11px; height:11px; border-radius:50%; vertical-align:middle; margin-right:4px; }}
  .controls {{ margin-top: 6px; }}
  .controls button {{
    padding: 5px 10px; margin-right: 6px; border: 1px solid #ddd;
    background: #fff; border-radius: 4px; font-size: 11px; cursor: pointer; font-family: inherit;
  }}
  .controls button:hover {{ background: #f5f5f5; }}
  #tree-container {{ width: 100vw; height: calc(100vh - 100px); overflow: hidden; }}
  .node circle {{ stroke: #fff; stroke-width: 2px; }}
  .node--course  circle {{ fill: #2c3e50; }}
  .node--block   circle {{ fill: #3498db; cursor: pointer; }}
  .node--aos     circle {{ fill: #9b59b6; cursor: pointer; }}
  .node--subject circle {{ fill: #1abc9c; }}
  .node--missing circle {{ fill: #cccccc; }}
  .node text {{ font-size: 11px; pointer-events: none; }}
  .link {{ fill: none; stroke: #ccc; stroke-width: 1.4; }}
  #tooltip {{
    position: absolute; pointer-events: none;
    background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 6px;
    font-size: 12px; line-height: 1.5; max-width: 320px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18); opacity: 0; transition: opacity 0.15s;
  }}
</style></head>
<body>
<header>
  <h1>Course tree &middot; {course_name} ({course_code}) {year}</h1>
  <p>Top-down D3 hierarchy. Click any blue / purple node to expand. Scroll to zoom, drag to pan.</p>
  <div class="legend">
    <span><i style="background:#2c3e50"></i>course</span>
    <span><i style="background:#3498db"></i>block</span>
    <span><i style="background:#9b59b6"></i>sub-major</span>
    <span><i style="background:#1abc9c"></i>subject</span>
    <span><i style="background:#cccccc"></i>no data</span>
  </div>
  <div class="controls">
    <button id="exp">Expand all</button>
    <button id="col">Collapse to depth 2</button>
    <button id="rst">Reset view</button>
  </div>
</header>
<div id="tree-container"></div>
<div id="tooltip"></div>
<script>
const data = {tree_json};
const container = document.getElementById('tree-container');
const tooltip   = document.getElementById('tooltip');
const svg  = d3.select('#tree-container').append('svg')
  .attr('width', container.clientWidth).attr('height', container.clientHeight);
const zoomG = svg.append('g');
const zb = d3.zoom().scaleExtent([0.2,3]).on('zoom', ev => zoomG.attr('transform', ev.transform));
svg.call(zb);
let root = d3.hierarchy(data);
let i = 0;
function collapseTo(d, max) {{
  if (d.depth >= max && d.children) {{ d._children = d.children; d.children = null; }}
  (d.children || d._children || []).forEach(c => collapseTo(c, max));
}}
function expandAll(d) {{
  if (d._children) {{ d.children = d._children; d._children = null; }}
  (d.children || []).forEach(expandAll);
}}
collapseTo(root, 2);
const tree = d3.tree().nodeSize([170,140]);
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
    .on('click', (ev,d) => {{
      if (d.data.level==='subject' || d.data.level==='missing') return;
      if (d.children) {{ d._children=d.children; d.children=null; }}
      else if (d._children) {{ d.children=d._children; d._children=null; }}
      update(d);
    }})
    .on('mouseover', (ev,d) => {{
      const lines = [`<strong>${{d.data.name}}</strong>`, `Type: ${{d.data.level}}`];
      if (d.data.cp) lines.push(`CP: ${{d.data.cp}}`);
      if (d.data.code) lines.push(`Code: ${{d.data.code}}`);
      if (d.data.faculty) lines.push(`Faculty: ${{d.data.faculty}}`);
      if (d._children) lines.push(`<span style="color:#9ca3af;">[${{d._children.length}} hidden]</span>`);
      tooltip.innerHTML = lines.join('<br>'); tooltip.style.opacity = 1;
    }})
    .on('mousemove', ev => {{ tooltip.style.left=(ev.pageX+14)+'px'; tooltip.style.top=(ev.pageY+14)+'px'; }})
    .on('mouseout', () => tooltip.style.opacity=0);
  nE.append('circle').attr('r', d => d.depth===0 ? 11 : (d.data.level==='subject'||d.data.level==='missing' ? 5 : 8));
  nE.append('text')
    .attr('y', d => d.children||d._children ? -14 : 18)
    .attr('text-anchor', d => d.data.level==='subject'||d.data.level==='missing' ? 'end' : 'middle')
    .attr('transform', d => d.data.level==='subject'||d.data.level==='missing' ? 'rotate(-35)' : null)
    .attr('fill','#222')
    .text(d => {{
      if (d.data.level==='subject') return d.data.code || (d.data.name||'').split(' ')[0];
      if (d.data.level==='missing') return '(no data)';
      const n = d.data.name||''; return n.length>32 ? n.slice(0,30)+'...' : n;
    }});
  nE.filter(d => d._children).append('text').attr('y',4).attr('text-anchor','middle')
    .attr('fill','#fff').attr('font-weight',700).attr('font-size',10).text('+');
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
window.addEventListener('resize', () => {{
  svg.attr('width', container.clientWidth).attr('height', container.clientHeight);
}});
</script></body></html>"""
