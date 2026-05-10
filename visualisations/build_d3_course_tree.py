"""
build_d3_course_tree.py
-----------------------
Renders a UTS course's full structure as an interactive D3.js vertical tree.

Same data the sunburst uses (the course JSON) but laid out as a top-down tree:
Course (root) -> Core / Options / Sub-Majors / Project Stream -> ... -> Subjects.

Output: course_tree_d3_{COURSE_CODE}_{YEAR}.html
"""

import json
import re
from pathlib import Path

REPO = Path("/sessions/epic-affectionate-davinci/mnt/UTS-handbook-portfolio-management-main")

COURSES = [
    "C04443_Master of Artificial Intelligence",
    "C10474_Bachelor of Artificial Intelligence",
]
YEAR = "2026"


def parse_cp(value):
    if not value:
        return 0
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else 0


def build_node(node):
    """Recursively turn a structure JSON node into a D3 hierarchy dict."""

    if "structure_name" in node:
        children = []
        for subj in node.get("has_subject") or []:
            children.append(build_node(subj))
        for aos in node.get("has_area_of_study") or []:
            children.append(build_node(aos))
        for sub in node.get("have_sub_structures") or []:
            children.append(build_node(sub))
        for cb in node.get("has_choice_block") or []:
            children.append(build_node(cb))
        return {
            "name": node["structure_name"],
            "level": "block",
            "cp": node.get("structure_cp", ""),
            "children": children,
        }

    if node.get("type") in ("Sub-Major", "Major", "Specialisation") or "have_structure" in node:
        children = [build_node(s) for s in (node.get("have_structure") or [])]
        return {
            "name": node.get("name") or node.get("code", "AOS"),
            "level": "aos",
            "code": node.get("code"),
            "cp": node.get("credit_points", ""),
            "children": children,
        }

    # Leaf subject
    return {
        "name": f"{node.get('code', '?')} {node.get('name', '')}".strip(),
        "level": "subject",
        "code": node.get("code"),
        "cp": node.get("credit_points", ""),
        "faculty": node.get("faculty"),
        "study_level": node.get("study_level"),
    }


def has_subject_descendant(node):
    if node.get("level") == "subject":
        return True
    for c in node.get("children") or []:
        if has_subject_descendant(c):
            return True
    return False


def patch_missing(node):
    """Inject a grey placeholder leaf for any block/aos with no subject descendants."""
    if node.get("level") in ("block", "aos"):
        if not has_subject_descendant(node):
            node["children"] = (node.get("children") or []) + [{
                "name": "(scraper data missing)",
                "level": "missing",
            }]
            return
    for c in node.get("children") or []:
        patch_missing(c)


HTML_TEMPLATE = r"""<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Course tree (D3) - {{COURSE_NAME}} ({{COURSE_CODE}}) {{YEAR}}</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
  if (typeof d3 === 'undefined') {
    document.write('<script src="https://unpkg.com/d3@7/dist/d3.min.js"><\/script>');
  }
</script>
<style>
  body { font-family: 'Inter', Arial, sans-serif; margin: 0; padding: 0; background: #fafafa; color: #222; }
  header { padding: 14px 24px; background: #fff; border-bottom: 1px solid #e5e5e5; }
  header h1 { margin: 0 0 4px 0; font-size: 19px; }
  header p { margin: 0; color: #666; font-size: 13px; }
  .legend { margin-top: 6px; font-size: 12px; color: #666; }
  .legend span { margin-right: 16px; }
  .legend i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; vertical-align: middle; margin-right: 4px; }
  .controls { margin-top: 8px; }
  .controls button {
    padding: 6px 12px; margin-right: 8px; border: 1px solid #ddd; background: #fff;
    border-radius: 4px; font-size: 12px; cursor: pointer; font-family: inherit;
  }
  .controls button:hover { background: #f5f5f5; }
  #tree-container { width: 100vw; height: calc(100vh - 110px); overflow: hidden; background: #fafafa; }
  .node circle { stroke: #fff; stroke-width: 2px; }
  .node--course circle { fill: #2c3e50; }
  .node--block circle   { fill: #3498db; cursor: pointer; }
  .node--aos circle     { fill: #9b59b6; cursor: pointer; }
  .node--subject circle { fill: #1abc9c; }
  .node--missing circle { fill: #cccccc; }
  .node text { font-size: 11px; pointer-events: none; }
  .link { fill: none; stroke: #ccc; stroke-width: 1.4; }
  #tooltip {
    position: absolute; pointer-events: none;
    background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 6px;
    font-size: 12px; line-height: 1.5; max-width: 320px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
    opacity: 0; transition: opacity 0.15s;
  }
</style>
</head>
<body>
<header>
  <h1>Course structure tree - {{COURSE_NAME}} ({{COURSE_CODE}}) {{YEAR}}</h1>
  <p>Top-down D3 hierarchical tree. Click any blue or purple node to collapse / expand. Scroll to zoom, drag empty space to pan.</p>
  <div class="legend">
    <span><i style="background:#2c3e50"></i>course</span>
    <span><i style="background:#3498db"></i>structure block</span>
    <span><i style="background:#9b59b6"></i>sub-major / area of study</span>
    <span><i style="background:#1abc9c"></i>subject</span>
    <span><i style="background:#cccccc"></i>scraper data missing</span>
  </div>
  <div class="controls">
    <button id="expand-all">Expand all</button>
    <button id="collapse-all">Collapse to depth 2</button>
    <button id="reset-zoom">Reset view</button>
  </div>
</header>
<div id="tree-container"></div>
<div id="tooltip"></div>

<script>
const data = {{TREE_JSON}};
const container = document.getElementById('tree-container');
const tooltip = document.getElementById('tooltip');

const svg = d3.select('#tree-container').append('svg')
  .attr('width', container.clientWidth)
  .attr('height', container.clientHeight);
const zoomG = svg.append('g');

const zoomBehaviour = d3.zoom().scaleExtent([0.2, 3]).on('zoom', ev => zoomG.attr('transform', ev.transform));
svg.call(zoomBehaviour);

let root = d3.hierarchy(data);
let i = 0;

function collapseToDepth(d, maxDepth) {
  if (d.depth >= maxDepth && d.children) {
    d._children = d.children;
    d.children = null;
  }
  (d.children || d._children || []).forEach(c => collapseToDepth(c, maxDepth));
}

function expandAll(d) {
  if (d._children) { d.children = d._children; d._children = null; }
  (d.children || []).forEach(expandAll);
}

collapseToDepth(root, 2);

const tree = d3.tree().nodeSize([110, 130]);

function update(source) {
  tree(root);
  const nodes = root.descendants();
  const links = root.links();

  // Center horizontally
  let xMin = Infinity, xMax = -Infinity;
  nodes.forEach(d => { if (d.x < xMin) xMin = d.x; if (d.x > xMax) xMax = d.x; });
  const xOffset = -((xMin + xMax) / 2) + (container.clientWidth / 2);
  nodes.forEach(d => d.x += xOffset);
  nodes.forEach(d => d.y += 30);

  // Links
  const link = zoomG.selectAll('path.link').data(links, d => d.target.__id || (d.target.__id = ++i));
  const linkEnter = link.enter().append('path').attr('class', 'link')
    .attr('d', d3.linkVertical().x(d => d.x).y(d => d.y));
  link.merge(linkEnter).transition().duration(300)
    .attr('d', d3.linkVertical().x(d => d.x).y(d => d.y));
  link.exit().remove();

  // Nodes
  const node = zoomG.selectAll('g.node').data(nodes, d => d.__id || (d.__id = ++i));
  const nodeEnter = node.enter().append('g')
    .attr('class', d => 'node node--' + d.data.level)
    .attr('transform', d => `translate(${source.x0 ?? d.x},${source.y0 ?? d.y})`)
    .on('click', (ev, d) => {
      if (d.data.level === 'subject' || d.data.level === 'missing') return;
      if (d.children) { d._children = d.children; d.children = null; }
      else if (d._children) { d.children = d._children; d._children = null; }
      update(d);
    })
    .on('mouseover', (ev, d) => {
      const lines = [`<strong>${d.data.name}</strong>`, `Type: ${d.data.level}`];
      if (d.data.cp) lines.push(`Credit points: ${d.data.cp}`);
      if (d.data.code) lines.push(`Code: ${d.data.code}`);
      if (d.data.faculty) lines.push(`Faculty: ${d.data.faculty}`);
      if (d._children) lines.push(`<span style="color:#9ca3af;">[${d._children.length} hidden child(ren) - click to expand]</span>`);
      tooltip.innerHTML = lines.join('<br>');
      tooltip.style.opacity = 1;
    })
    .on('mousemove', ev => {
      tooltip.style.left = (ev.pageX + 14) + 'px';
      tooltip.style.top = (ev.pageY + 14) + 'px';
    })
    .on('mouseout', () => { tooltip.style.opacity = 0; });

  nodeEnter.append('circle').attr('r', d => d.depth === 0 ? 11 : (d.data.level === 'subject' || d.data.level === 'missing' ? 5 : 8));

  nodeEnter.append('text')
    .attr('y', d => d.children || d._children ? -14 : 18)
    .attr('text-anchor', 'middle')
    .attr('fill', '#222')
    .text(d => {
      const n = d.data.name || '';
      return n.length > 32 ? n.slice(0, 30) + '...' : n;
    });

  // "+" badge for collapsed
  nodeEnter.filter(d => d._children).append('text')
    .attr('y', 4).attr('text-anchor', 'middle')
    .attr('fill', '#fff').attr('font-weight', 700).attr('font-size', 10)
    .text('+');

  node.merge(nodeEnter).transition().duration(300)
    .attr('transform', d => `translate(${d.x},${d.y})`);
  node.exit().remove();

  nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
}

update(root);

// Auto-fit on load
setTimeout(() => {
  const bbox = zoomG.node().getBBox();
  const scale = Math.min(
    container.clientWidth / (bbox.width + 80),
    container.clientHeight / (bbox.height + 80),
    1.2
  );
  const tx = container.clientWidth / 2 - scale * (bbox.x + bbox.width / 2);
  const ty = 60 - scale * bbox.y;
  svg.transition().duration(400).call(zoomBehaviour.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}, 350);

// Controls
document.getElementById('expand-all').onclick = () => { expandAll(root); update(root); };
document.getElementById('collapse-all').onclick = () => { collapseToDepth(root, 2); update(root); };
document.getElementById('reset-zoom').onclick = () => {
  const bbox = zoomG.node().getBBox();
  const scale = Math.min(container.clientWidth / (bbox.width + 80), container.clientHeight / (bbox.height + 80), 1.2);
  const tx = container.clientWidth / 2 - scale * (bbox.x + bbox.width / 2);
  const ty = 60 - scale * bbox.y;
  svg.transition().duration(400).call(zoomBehaviour.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
};

window.addEventListener('resize', () => {
  svg.attr('width', container.clientWidth).attr('height', container.clientHeight);
});
</script>
</body></html>
"""


for course_folder in COURSES:
    json_path = REPO / "dataset" / course_folder / f"{YEAR}.json"
    if not json_path.exists():
        print(f"Skipping {course_folder}: no {YEAR}.json")
        continue

    with open(json_path, encoding="utf-8") as f:
        course = json.load(f)

    root_node = {
        "name": course["course_name"],
        "level": "course",
        "code": course["course_code"],
        "children": [build_node(b) for b in course["structure"]],
    }
    patch_missing(root_node)

    out_path = REPO / f"course_tree_d3_{course['course_code']}_{YEAR}.html"
    html = (HTML_TEMPLATE
            .replace("{{COURSE_NAME}}", course["course_name"])
            .replace("{{COURSE_CODE}}", course["course_code"])
            .replace("{{YEAR}}", YEAR)
            .replace("{{TREE_JSON}}", json.dumps(root_node)))
    out_path.write_text(html, encoding="utf-8")

    # Quick stats
    def count(node):
        n = 1
        for c in node.get("children") or []:
            n += count(c)
        return n
    print(f"Wrote {out_path.name}  ({count(root_node)} total nodes)")
