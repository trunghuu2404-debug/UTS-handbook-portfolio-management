"""
build_d3_prereq_tree.py
-----------------------
Builds a vertical D3.js prerequisite tree for a chosen subject.

Output: prereq_tree_d3_{CODE}_{YEAR}.html

Layout: target subject at the top (root), prereqs branching downward as children.
Click any node to collapse/expand its subtree. Hover for details.
"""

import json
import re
from pathlib import Path

REPO = Path("/sessions/epic-affectionate-davinci/mnt/UTS-handbook-portfolio-management-main")

# --- Pick subjects to render ------------------------------------------------
TARGETS = ["41001", "41043"]   # Cloud Computing, Natural Language Processing
YEAR = 2026
MAX_DEPTH = 4

with open(REPO / "dataset" / "subjects_archive" / f"{YEAR}_subjects.json", encoding="utf-8") as f:
    SUBJECTS = json.load(f)

SUBJECT_CODE_RE = re.compile(r"\b(\d{5}|[A-Z]{3,4}\d{4,5})\b")


def get_prereq_codes(subject):
    """Return the list of subject codes that are real academic prerequisites."""
    rl = subject.get("requisite_list") or {}
    pre = []
    for item in (rl.get("requisite") or {}).get("items") or []:
        item_type = (item.get("type") or "").lower()
        if "academic" in item_type or "subject" in item_type or not item_type:
            for code in SUBJECT_CODE_RE.findall(item.get("details") or ""):
                if code in SUBJECTS:
                    pre.append(code)
    return list(dict.fromkeys(pre))  # dedupe, preserve order


def get_anti_codes(subject):
    rl = subject.get("requisite_list") or {}
    anti = []
    for item in (rl.get("anti_requisite") or {}).get("items") or []:
        for code in SUBJECT_CODE_RE.findall(item.get("details") or ""):
            if code in SUBJECTS and code != subject.get("code"):
                anti.append(code)
    return list(dict.fromkeys(anti))


def build_tree(code, depth=0, visited=None):
    """Recursive descent into the prereq chain. Each node has the D3 hierarchy shape."""
    if visited is None:
        visited = set()
    s = SUBJECTS.get(code, {})
    name = s.get("name", code)
    faculty = s.get("faculty", "—")
    cp = s.get("credit_points", "—")
    anti = get_anti_codes(s)

    node = {
        "name": f"{code}  {name}",
        "code": code,
        "subject_name": name,
        "faculty": faculty,
        "cp": cp,
        "antis": anti,
        "children": [],
    }

    if depth >= MAX_DEPTH or code in visited:
        return node

    visited = visited | {code}
    for prereq in get_prereq_codes(s):
        node["children"].append(build_tree(prereq, depth + 1, visited))

    return node


HTML_TEMPLATE = r"""<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Prereq tree · {{ROOT_NAME}} ({{ROOT_CODE}})</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
  // Fallback: if D3 didn't load from jsdelivr, try unpkg
  if (typeof d3 === 'undefined') {
    document.write('<script src="https://unpkg.com/d3@7/dist/d3.min.js"><\/script>');
  }
</script>
<style>
  body { font-family: 'Inter', Arial, sans-serif; margin: 0; padding: 0; background: #fafafa; color: #222; }
  header { padding: 16px 24px; background: #fff; border-bottom: 1px solid #e5e5e5; }
  header h1 { margin: 0 0 4px 0; font-size: 20px; }
  header p { margin: 0; color: #666; font-size: 13px; }
  #tree-container { width: 100vw; height: calc(100vh - 78px); overflow: hidden; background: #fafafa; }
  .node circle { stroke: #fff; stroke-width: 2px; }
  .node--root circle { fill: #2c3e50; }
  .node--internal circle { fill: #3498db; cursor: pointer; }
  .node--leaf circle { fill: #27ae60; }
  .node text { font-size: 12px; pointer-events: none; }
  .node-label-bg { fill: #fff; stroke: #ddd; stroke-width: 1; }
  .link { fill: none; stroke: #bbb; stroke-width: 1.6; }
  .link-anti { stroke: #c0392b; stroke-dasharray: 4 3; }
  #tooltip {
    position: absolute; pointer-events: none;
    background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 6px;
    font-size: 12px; line-height: 1.5; max-width: 320px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
    opacity: 0; transition: opacity 0.15s;
  }
  .legend { margin-top: 6px; font-size: 12px; color: #666; }
  .legend span { margin-right: 16px; }
  .legend i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; vertical-align: middle; margin-right: 4px; }
</style>
</head>
<body>
<header>
  <h1>Prerequisite tree · {{ROOT_NAME}} ({{ROOT_CODE}}) · {{YEAR}}</h1>
  <p>Vertical D3 tree. Target subject at the top, prerequisites branching downward. Click any blue node to collapse / expand its subtree.</p>
  <div class="legend">
    <span><i style="background:#2c3e50"></i>target subject</span>
    <span><i style="background:#3498db"></i>prerequisite (has its own prereqs)</span>
    <span><i style="background:#27ae60"></i>prerequisite (no further prereqs)</span>
  </div>
</header>
<div id="tree-container"></div>
<div id="tooltip"></div>

<script>
const data = {{TREE_JSON}};

const container = document.getElementById('tree-container');
const tooltip = document.getElementById('tooltip');

const margin = { top: 60, right: 40, bottom: 60, left: 40 };
let width = container.clientWidth - margin.left - margin.right;
let height = container.clientHeight - margin.top - margin.bottom;

const svg = d3.select('#tree-container')
  .append('svg')
  .attr('width', container.clientWidth)
  .attr('height', container.clientHeight);

// Pan + zoom
const zoomG = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);
svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', ev => zoomG.attr('transform', ev.transform)));

let root = d3.hierarchy(data);
let i = 0;

// Collapse nodes deeper than 2 by default
root.descendants().forEach(d => {
  if (d.depth > 1 && d.children) {
    d._children = d.children;
    d.children = null;
  }
});

const tree = d3.tree().nodeSize([200, 110]);

function update(source) {
  tree(root);

  const nodes = root.descendants();
  const links = root.links();

  // Centre horizontally
  let xMin = Infinity, xMax = -Infinity;
  nodes.forEach(d => { if (d.x < xMin) xMin = d.x; if (d.x > xMax) xMax = d.x; });
  const xOffset = -((xMin + xMax) / 2) + (width / 2);
  nodes.forEach(d => d.x += xOffset);

  // --- Links ---------------------------------------------------------------
  const link = zoomG.selectAll('path.link').data(links, d => d.target.data.code);

  const linkEnter = link.enter().append('path')
    .attr('class', 'link')
    .attr('d', d3.linkVertical().x(d => d.x).y(d => d.y));

  link.merge(linkEnter)
    .transition().duration(350)
    .attr('d', d3.linkVertical().x(d => d.x).y(d => d.y));

  link.exit().remove();

  // --- Nodes ---------------------------------------------------------------
  const node = zoomG.selectAll('g.node').data(nodes, d => d.data.code || (d.id = ++i));

  const nodeEnter = node.enter().append('g')
    .attr('class', d => 'node ' + (d.depth === 0 ? 'node--root' : (d._children || d.children ? 'node--internal' : 'node--leaf')))
    .attr('transform', d => `translate(${source.x0 ?? d.x},${source.y0 ?? d.y})`)
    .on('click', (ev, d) => {
      if (d.children) { d._children = d.children; d.children = null; }
      else if (d._children) { d.children = d._children; d._children = null; }
      update(d);
    })
    .on('mouseover', (ev, d) => {
      const a = d.data.antis && d.data.antis.length
        ? `<div style="margin-top:4px;color:#fbbf24;">Anti-requisites: ${d.data.antis.join(', ')}</div>` : '';
      const collapsed = d._children ? `<div style="margin-top:4px;color:#9ca3af;">[click to expand]</div>` : '';
      tooltip.innerHTML = `
        <div><strong>${d.data.subject_name}</strong></div>
        <div>Code: ${d.data.code}</div>
        <div>Faculty: ${d.data.faculty}</div>
        <div>Credit points: ${d.data.cp}</div>
        ${a}${collapsed}`;
      tooltip.style.opacity = 1;
    })
    .on('mousemove', ev => {
      tooltip.style.left = (ev.pageX + 14) + 'px';
      tooltip.style.top = (ev.pageY + 14) + 'px';
    })
    .on('mouseout', () => { tooltip.style.opacity = 0; });

  nodeEnter.append('circle').attr('r', 9);

  // Two-line label: code on top, subject name on bottom
  nodeEnter.append('text')
    .attr('y', 26)
    .attr('text-anchor', 'middle')
    .attr('font-weight', 600)
    .attr('fill', '#222')
    .text(d => d.data.code);

  nodeEnter.append('text')
    .attr('y', 42)
    .attr('text-anchor', 'middle')
    .attr('fill', '#555')
    .text(d => {
      const n = d.data.subject_name || '';
      return n.length > 28 ? n.slice(0, 26) + '…' : n;
    });

  // Cue that there are hidden children
  nodeEnter.filter(d => d._children)
    .append('text')
    .attr('y', 4).attr('x', 0)
    .attr('text-anchor', 'middle')
    .attr('fill', '#fff')
    .attr('font-weight', 700)
    .attr('font-size', 10)
    .text('+');

  node.merge(nodeEnter)
    .transition().duration(350)
    .attr('transform', d => `translate(${d.x},${d.y})`);

  node.exit().remove();

  nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
}

update(root);

window.addEventListener('resize', () => {
  width = container.clientWidth - margin.left - margin.right;
  height = container.clientHeight - margin.top - margin.bottom;
  svg.attr('width', container.clientWidth).attr('height', container.clientHeight);
  update(root);
});
</script>
</body></html>
"""


for code in TARGETS:
    if code not in SUBJECTS:
        print(f"Skipping {code}: not in {YEAR} subjects archive")
        continue
    tree_data = build_tree(code)
    name = SUBJECTS[code].get("name", code)
    out = REPO / f"prereq_tree_d3_{code}_{YEAR}.html"
    html = (HTML_TEMPLATE
            .replace("{{ROOT_NAME}}", name)
            .replace("{{ROOT_CODE}}", code)
            .replace("{{YEAR}}", str(YEAR))
            .replace("{{TREE_JSON}}", json.dumps(tree_data)))
    out.write_text(html, encoding="utf-8")
    n_nodes = len(json.dumps(tree_data).split('"code"')) - 1
    print(f"✅ Wrote {out.name}  (~{n_nodes} nodes)")
