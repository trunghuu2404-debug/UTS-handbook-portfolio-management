"""
backend/visualizations/prereq_graph.py
----------------------------------------
Interactive prerequisite graph using vis.js.

Behaviour:
- Root node auto-expands on load (shows its direct prerequisites).
- Click any subject node to expand its prerequisites.
- Click an expanded node again to collapse it.
- Admission and other requisite items shown as distinct node shapes.
"""

from __future__ import annotations
import json
from functools import lru_cache
from services.viz_service import get_prereq_subgraph


@lru_cache(maxsize=128)
def build_prereq_graph_html(subject_code: str, year: int = 2026) -> str:
    data = get_prereq_subgraph(subject_code, year)

    if subject_code not in data["nodes"]:
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"Subject {subject_code} not found for year {year}.</div>"
        )

    nodes = data["nodes"]
    prereq_edges = data["prereq_edges"]
    anti_edges = data["anti_edges"]
    admission_reqs = data["admission_reqs"]
    other_reqs = data["other_reqs"]
    root_name = nodes[subject_code]["name"]

    # prereqs_of[target] = [list of prereq codes that feed into it]
    prereqs_of: dict = {}
    for pre, tgt in prereq_edges:
        prereqs_of.setdefault(tgt, []).append(pre)

    # Build node list

    vis_nodes = []

    def wrap(text: str, width: int = 20) -> str:
        """Wrap long text into multiple lines for vis.js labels."""
        words = text.split()
        lines, cur = [], []
        for w in words:
            if sum(len(x) for x in cur) + len(cur) + len(w) > width and cur:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            lines.append(" ".join(cur))
        return "\n".join(lines)

    for code, info in nodes.items():
        is_root = code == subject_code
        label = f"{code}\n{wrap(info['name'], 18)}"
        title = (
            f"<b>{info['name']}</b><br>"
            f"Code: {code}<br>"
            f"Faculty: {info['faculty']}<br>"
            f"CP: {info['cp']}"
        )
        vis_nodes.append(
            {
                "id": code,
                "label": label,
                "title": title,
                "color": {
                    "background": "#1a3a4a" if is_root else "#2980b9",
                    "border": "#0d1f27" if is_root else "#1a5f8a",
                    "highlight": {"background": "#2ecc71", "border": "#27ae60"},
                    "hover": {"background": "#3498db", "border": "#2176ae"},
                },
                "font": {
                    "color": "#171313",
                    "size": 14,
                    "face": "Inter, Arial, sans-serif",
                },
                "shape": "dot",
                "size": 30 if is_root else 22,
                "hidden": False if is_root else True,
                "expanded": False,
                "node_type": "subject",
            }
        )

    # Admission requisite nodes
    adm_links = []
    for code, texts in admission_reqs.items():
        for i, text in enumerate(texts):
            nid = f"adm__{code}__{i}"
            adm_links.append((nid, code))
            vis_nodes.append(
                {
                    "id": nid,
                    "label": f"Admission\n{wrap(text, 18)}",
                    "title": f"<b>Admission requisite</b><br>{text}",
                    "color": {
                        "background": "#d35400",
                        "border": "#a04000",
                        "highlight": {"background": "#e67e22", "border": "#d35400"},
                    },
                    "font": {
                        "color": "#171313",
                        "size": 12,
                        "face": "Inter, Arial, sans-serif",
                    },
                    "shape": "diamond",
                    "size": 18,
                    "hidden": True,
                    "node_type": "admission",
                }
            )

    # Other requisite nodes
    other_links = []
    for code, texts in other_reqs.items():
        for i, text in enumerate(texts):
            nid = f"oth__{code}__{i}"
            other_links.append((nid, code))
            vis_nodes.append(
                {
                    "id": nid,
                    "label": f"Other req\n{wrap(text, 18)}",
                    "title": f"<b>Other requisite</b><br>{text}",
                    "color": {
                        "background": "#616a6b",
                        "border": "#424949",
                        "highlight": {"background": "#808b96", "border": "#616a6b"},
                    },
                    "font": {
                        "color": "#171313",
                        "size": 12,
                        "face": "Inter, Arial, sans-serif",
                    },
                    "shape": "square",
                    "size": 16,
                    "hidden": True,
                    "node_type": "other",
                }
            )

    # Build edge list

    vis_edges = []

    for pre, tgt in prereq_edges:
        vis_edges.append(
            {
                "id": f"pre__{pre}__{tgt}",
                "from": pre,
                "to": tgt,
                "color": {"color": "#27ae60", "highlight": "#2ecc71"},
                "arrows": "to",
                "width": 2.5,
                "smooth": {"type": "cubicBezier"},
                "hidden": True,
                "edge_type": "prereq",
            }
        )

    for src, anti in anti_edges:
        if anti in nodes:
            vis_edges.append(
                {
                    "id": f"anti__{src}__{anti}",
                    "from": src,
                    "to": anti,
                    "color": {"color": "#c0392b", "highlight": "#e74c3c"},
                    "arrows": "to",
                    "dashes": True,
                    "width": 2,
                    "smooth": {"type": "cubicBezier"},
                    "hidden": True,
                    "edge_type": "anti",
                }
            )

    for nid, parent in adm_links:
        vis_edges.append(
            {
                "id": f"edge__{nid}",
                "from": nid,
                "to": parent,
                "color": {"color": "#d35400"},
                "arrows": "to",
                "dashes": True,
                "width": 1.5,
                "hidden": True,
                "edge_type": "admission",
            }
        )

    for nid, parent in other_links:
        vis_edges.append(
            {
                "id": f"edge__{nid}",
                "from": nid,
                "to": parent,
                "color": {"color": "#616a6b"},
                "arrows": "to",
                "dashes": True,
                "width": 1.5,
                "hidden": True,
                "edge_type": "other",
            }
        )

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/dist/vis-network.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/dist/dist/vis-network.min.css">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Inter, Arial, sans-serif; background: #f8f9fa; }}
  header {{ padding: 12px 18px; background: #fff; border-bottom: 1px solid #dee2e6; }}
  header h1 {{ font-size: 16px; font-weight: 600; color: #212529; margin-bottom: 6px; }}
  .legend {{ display: flex; gap: 18px; flex-wrap: wrap; font-size: 12px; color: #495057; align-items: center; }}
  .leg-item {{ display: flex; align-items: center; gap: 5px; }}
  .leg-dot   {{ width:14px;height:14px;border-radius:50%;display:inline-block; }}
  .leg-dia   {{ width:12px;height:12px;transform:rotate(45deg);display:inline-block; }}
  .leg-sq    {{ width:12px;height:12px;display:inline-block; }}
  .leg-line  {{ width:24px;height:0;border-top:2.5px solid;display:inline-block; }}
  .leg-dash  {{ width:24px;height:0;border-top:2px dashed;display:inline-block; }}
  #hint {{ padding: 6px 18px; background: #fff9e6; border-bottom: 1px solid #ffe58a;
           font-size: 12px; color: #7d6608; }}
  #graph {{ width: 100%; height: calc(100vh - 108px); background: #fff; }}
</style>
</head>
<body>
<header>
  <h1>Prerequisite graph &middot; {root_name} ({subject_code}) &middot; {year}</h1>
  <div class="legend">
    <div class="leg-item"><span class="leg-dot" style="background:#1a3a4a"></span>Root subject</div>
    <div class="leg-item"><span class="leg-dot" style="background:#2980b9"></span>Prerequisite subject</div>
    <div class="leg-item"><span class="leg-line" style="border-color:#27ae60"></span>Prerequisite</div>
    <div class="leg-item"><span class="leg-dash" style="border-color:#c0392b"></span>Anti-requisite</div>
    <div class="leg-item"><span class="leg-dia" style="background:#d35400"></span>Admission requisite</div>
    <div class="leg-item"><span class="leg-sq"  style="background:#616a6b"></span>Other requisite</div>
  </div>
</header>
<div id="hint">&#128161; Click any subject node to expand prerequisites. Click again to collapse.</div>
<div id="graph"></div>

<script>
const ROOT_ID   = {json.dumps(subject_code)};
const ALL_NODES = {nodes_json};
const ALL_EDGES = {edges_json};

const nodeMap = {{}};
ALL_NODES.forEach(n => nodeMap[n.id] = n);

const visNodes = new vis.DataSet(ALL_NODES.map(n => ({{...n}})));
const visEdges = new vis.DataSet(ALL_EDGES.map(e => ({{...e}})));

const options = {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -80,
      centralGravity: 0.008,
      springLength: 160,
      springConstant: 0.05,
      damping: 0.6,
    }},
    stabilization: {{ iterations: 300, updateInterval: 25 }},
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 80,
    navigationButtons: true,
    keyboard: true,
    zoomView: true,
  }},
  nodes: {{ borderWidth: 2, borderWidthSelected: 3 }},
  edges: {{ smooth: {{ type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.4 }} }},
}};

const network = new vis.Network(
  document.getElementById('graph'),
  {{ nodes: visNodes, edges: visEdges }},
  options
);

// ── Expand a subject node: show all edges/nodes connected to it ──────────────
function expandNode(clickedId) {{
  const node = nodeMap[clickedId];
  if (!node || node.node_type !== 'subject') return;

  const nodeUpdates = [];
  const edgeUpdates = [];

  ALL_EDGES.forEach(e => {{
    let revealNeighbour = null;

    if (e.edge_type === 'prereq' && e.to === clickedId) {{
      revealNeighbour = e.from;
    }}
    if (e.edge_type === 'anti' && (e.from === clickedId || e.to === clickedId)) {{
      revealNeighbour = e.from === clickedId ? e.to : e.from;
    }}
    if ((e.edge_type === 'admission' || e.edge_type === 'other') && e.to === clickedId) {{
      revealNeighbour = e.from;
    }}

    if (revealNeighbour !== null) {{
      const nb = nodeMap[revealNeighbour];
      if (nb && nb.hidden) {{
        nb.hidden = false;
        nodeUpdates.push({{ id: revealNeighbour, hidden: false }});
      }}
      if (e.hidden) {{
        e.hidden = false;
        edgeUpdates.push({{ id: e.id, hidden: false }});
      }}
    }}
  }});

  node.expanded = true;
  // Highlight expanded node with a teal border
  nodeUpdates.push({{ id: clickedId, color: {{
    background: '#117a8b', border: '#0c5460',
    highlight: {{ background: '#138496', border: '#0c5460' }}
  }} }});

  if (nodeUpdates.length) visNodes.update(nodeUpdates);
  if (edgeUpdates.length) visEdges.update(edgeUpdates);
}}

// ── Collapse: hide everything that was revealed by this node ─────────────────
function collapseNode(clickedId) {{
  const node = nodeMap[clickedId];
  if (!node || !node.expanded) return;
  node.expanded = false;

  // Determine which neighbours were revealed by this node
  const toHide = new Set();
  ALL_EDGES.forEach(e => {{
    if (e.edge_type === 'prereq' && e.to === clickedId) toHide.add(e.from);
    if (e.edge_type === 'anti' && e.from === clickedId) toHide.add(e.to);
    if (e.edge_type === 'anti' && e.to === clickedId)   toHide.add(e.from);
    if ((e.edge_type === 'admission' || e.edge_type === 'other') && e.to === clickedId) toHide.add(e.from);
  }});

  // Only hide nodes that aren't also connected to another expanded subject node
  const expandedNodes = new Set(
    ALL_NODES.filter(n => n.node_type === 'subject' && n.expanded && n.id !== clickedId).map(n => n.id)
  );

  const safeToHide = new Set();
  toHide.forEach(nid => {{
    let stillNeeded = false;
    ALL_EDGES.forEach(e => {{
      if (expandedNodes.has(e.to) || expandedNodes.has(e.from)) {{
        if (e.from === nid || e.to === nid) stillNeeded = true;
      }}
    }});
    if (!stillNeeded) safeToHide.add(nid);
  }});

  const nodeUpdates = [];
  const edgeUpdates = [];

  safeToHide.forEach(nid => {{
    const nb = nodeMap[nid];
    if (nb) {{ nb.hidden = true; nodeUpdates.push({{ id: nid, hidden: true }}); }}
  }});

  ALL_EDGES.forEach(e => {{
    const fromHidden = safeToHide.has(e.from) || (nodeMap[e.from] && nodeMap[e.from].hidden);
    const toHideCheck = safeToHide.has(e.to);
    if ((e.edge_type === 'prereq' && e.to === clickedId && safeToHide.has(e.from))
     || (toHideCheck && !e.hidden)) {{
      e.hidden = true;
      edgeUpdates.push({{ id: e.id, hidden: true }});
    }}
    // Also hide edges that connected the root to revealed nodes
    if (!e.hidden && (safeToHide.has(e.from) || safeToHide.has(e.to))) {{
      e.hidden = true;
      edgeUpdates.push({{ id: e.id, hidden: true }});
    }}
  }});

  // Restore original node colour
  nodeUpdates.push({{ id: clickedId,
    color: {{ background: '#1a3a4a', border: '#0d1f27',
              highlight: {{ background: '#2ecc71', border: '#27ae60' }} }} }});

  if (nodeUpdates.length) visNodes.update(nodeUpdates);
  if (edgeUpdates.length) visEdges.update(edgeUpdates);
}}

// Auto-expand root on load
network.once('stabilized', () => expandNode(ROOT_ID));

// Toggle on click
network.on('click', params => {{
  if (params.nodes.length !== 1) return;
  const id = params.nodes[0];
  const node = nodeMap[id];
  if (!node || node.node_type !== 'subject') return;
  if (node.expanded) collapseNode(id);
  else expandNode(id);
}});
</script>
</body></html>"""
