"""
build_prerequisite_graph.py
---------------------------
Renders a subject's prerequisite + anti-requisite network as an interactive HTML graph.
Walks the prerequisite chain recursively (with depth limit), pulling subject metadata
from subjects_archive.

Output: prerequisite_graph_{CODE}_{YEAR}.html
"""

import json
import re
from pathlib import Path

from pyvis.network import Network

REPO = Path("/sessions/epic-affectionate-davinci/mnt/UTS-handbook-portfolio-management-main")

# --- Pick subject + year ----------------------------------------------------
ROOT_CODE = "32513"   # Advanced Data Analytics Algorithms — usually has stacked prereqs
YEAR = 2026
MAX_DEPTH = 3
OUT = REPO / f"prerequisite_graph_{ROOT_CODE}_{YEAR}.html"

with open(REPO / "dataset" / "subjects_archive" / f"{YEAR}_subjects.json", encoding="utf-8") as f:
    SUBJECTS = json.load(f)


# --- Helpers ----------------------------------------------------------------
SUBJECT_CODE_RE = re.compile(r"\b(\d{5}|[A-Z]{3,4}\d{4,5})\b")


def extract_codes_from_detail(detail):
    """Pull out subject codes from a free-text detail string."""
    if not detail:
        return []
    return SUBJECT_CODE_RE.findall(detail)


def get_requisite_subject_codes(subject):
    """Return (prereq_codes, anti_codes, admission_notes) for a subject."""
    rl = subject.get("requisite_list") or {}
    pre, anti, admin_notes = [], [], []

    pre_block = rl.get("requisite") or {}
    for item in pre_block.get("items") or []:
        item_type = (item.get("type") or "").lower()
        detail = item.get("details") or ""
        if "academic" in item_type or "subject" in item_type or not item_type:
            for code in extract_codes_from_detail(detail):
                if code in SUBJECTS:
                    pre.append(code)
        else:
            admin_notes.append(detail)

    anti_block = rl.get("anti_requisite") or {}
    for item in anti_block.get("items") or []:
        for code in extract_codes_from_detail(item.get("details") or ""):
            if code in SUBJECTS and code != subject.get("code"):
                anti.append(code)

    return pre, anti, admin_notes


# --- Walk the prerequisite tree --------------------------------------------
visited = set()
edges = []        # (parent_code, child_code, kind) where kind in {prereq, anti}
admission_for = {}


def walk(code, depth):
    if depth > MAX_DEPTH or code in visited:
        return
    visited.add(code)
    subj = SUBJECTS.get(code)
    if not subj:
        return
    pre, anti, admins = get_requisite_subject_codes(subj)
    admission_for[code] = admins
    for p in pre:
        edges.append((p, code, "prereq"))
        walk(p, depth + 1)
    for a in anti:
        edges.append((code, a, "anti"))
        # don't recurse anti-requisites; they're not part of the chain


walk(ROOT_CODE, 0)

# Always include any nodes that ended up in edges
for u, v, _ in edges:
    visited.add(u)
    visited.add(v)


# --- Render -----------------------------------------------------------------
net = Network(
    height="800px", width="100%", bgcolor="#ffffff", font_color="#222",
    directed=True, cdn_resources="in_line",
)

for code in visited:
    s = SUBJECTS.get(code, {})
    name = s.get("name", code)
    is_root = code == ROOT_CODE
    colour = "#2c3e50" if is_root else "#3498db"
    size = 28 if is_root else 16
    title = (
        f"<b>{name}</b><br>"
        f"Code: {code}<br>"
        f"Faculty: {s.get('faculty','—')}<br>"
        f"CP: {s.get('credit_points','—')}"
    )
    if admission_for.get(code):
        title += "<br><br><b>Admission notes:</b><br>" + "<br>".join(
            "• " + a for a in admission_for[code][:5]
        )
    net.add_node(code, label=f"{code}\n{name[:24]}", title=title, color=colour, size=size, shape="dot")

for u, v, kind in edges:
    if kind == "prereq":
        net.add_edge(u, v, color="#27ae60", arrows="to", title=f"{u} is a prereq of {v}", width=2)
    else:
        net.add_edge(u, v, color="#c0392b", arrows="to", dashes=True, title=f"{v} is an anti-requisite of {u}", width=2)

net.set_options("""
{
  "physics": {
    "hierarchicalRepulsion": {"nodeDistance": 180, "centralGravity": 0.0, "springLength": 150},
    "solver": "hierarchicalRepulsion",
    "stabilization": {"iterations": 200}
  },
  "layout": {
    "hierarchical": {
      "enabled": true,
      "direction": "LR",
      "sortMethod": "directed",
      "levelSeparation": 220,
      "nodeSpacing": 120
    }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 80,
    "navigationButtons": true
  }
}
""")

net.write_html(str(OUT), notebook=False, open_browser=False)

# Add a header
root_subj = SUBJECTS.get(ROOT_CODE, {})
root_name = root_subj.get("name", ROOT_CODE)
header = f"""
<div style="font-family:Inter,Arial,sans-serif;padding:14px 24px;border-bottom:1px solid #eee;background:#fafafa;">
  <div style="font-size:20px;font-weight:600;">Prerequisite graph · {root_name} ({ROOT_CODE}) · {YEAR}</div>
  <div style="font-size:13px;color:#666;margin-top:4px;">
    Walks the prerequisite chain {MAX_DEPTH} levels back. Green arrows = prerequisites (must complete first),
    red dashed = anti-requisites (cannot take both). Hover for details.
  </div>
</div>
"""
html = OUT.read_text(encoding="utf-8")
html = html.replace("<body>", "<body>" + header, 1)
OUT.write_text(html, encoding="utf-8")

print(f"✅ Wrote {OUT}")
print(f"   nodes: {len(visited)}   edges: {len(edges)}")
