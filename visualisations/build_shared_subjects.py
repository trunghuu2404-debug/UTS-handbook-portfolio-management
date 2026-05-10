"""
build_shared_subjects.py
------------------------
Renders which subjects appear across multiple UTS programs.

Bipartite graph:
  - Big course nodes (one per program)
  - Subject nodes connected to the courses they appear in
  - Subjects appearing in 2+ courses naturally float to the centre

Output: shared_subjects_across_programs_{YEAR}.html
"""

import json
import re
from pathlib import Path

from pyvis.network import Network

REPO = Path(__file__).resolve().parent.parent
DATASET = REPO / "dataset"
YEAR = "2026"

OUT = REPO / "visualisations" / f"shared_subjects_across_programs_{YEAR}.html"


def collect_subjects(node, found):
    """Recursively pull every subject leaf from a course structure."""
    if isinstance(node, dict):
        if node.get("type") == "Subject" or ("code" in node and "name" in node and "credit_points" in node and "type" not in node):
            code = node.get("code")
            if code and re.match(r"^\d{5}$|^[A-Z]{3,4}\d{4,5}$", str(code)):
                found[code] = node.get("name", code)
                return
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                collect_subjects(v, found)
    elif isinstance(node, list):
        for item in node:
            collect_subjects(item, found)


# Collect subjects per course
courses = {}
for course_dir in sorted(DATASET.iterdir()):
    if not course_dir.is_dir() or not course_dir.name.startswith("C"):
        continue
    json_path = course_dir / f"{YEAR}.json"
    if not json_path.exists():
        continue
    data = json.loads(json_path.read_text(encoding="utf-8"))
    subj = {}
    collect_subjects(data.get("structure", []), subj)
    courses[data["course_code"]] = {
        "name": data["course_name"],
        "subjects": subj,
    }
    print(f"{data['course_code']} {data['course_name']}: {len(subj)} subjects")

# Reverse-index: subject -> list of courses it appears in
subject_to_courses = {}
for ccode, cinfo in courses.items():
    for scode, sname in cinfo["subjects"].items():
        subject_to_courses.setdefault(scode, {"name": sname, "courses": []})["courses"].append(ccode)

# How many shared?
shared = {sc: info for sc, info in subject_to_courses.items() if len(info["courses"]) >= 2}
print(f"Total unique subjects: {len(subject_to_courses)}   shared in 2+ programs: {len(shared)}")

# --- Build bipartite network -----------------------------------------------
net = Network(
    height="800px", width="100%", bgcolor="#ffffff", font_color="#222",
    directed=False, cdn_resources="in_line",
)

COURSE_COLOURS = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]

# Course nodes (big, with degree label)
for i, (ccode, cinfo) in enumerate(courses.items()):
    colour = COURSE_COLOURS[i % len(COURSE_COLOURS)]
    title = (
        f"<b>{cinfo['name']}</b><br>"
        f"Code: {ccode}<br>"
        f"Subjects in this program: {len(cinfo['subjects'])}"
    )
    net.add_node(
        ccode, label=cinfo["name"], title=title,
        color=colour, size=50, shape="dot",
        font={"size": 22, "face": "Inter, Arial, sans-serif", "color": "#000"},
    )

# Subject nodes
for scode, info in subject_to_courses.items():
    n_courses = len(info["courses"])
    if n_courses >= 2:
        # Shared - bigger, gold
        colour = "#f1c40f"
        size = 16
    else:
        # Unique to one program - smaller, grey
        colour = "#bdc3c7"
        size = 7
    title = (
        f"<b>{info['name']}</b><br>"
        f"Code: {scode}<br>"
        f"Appears in: {', '.join(info['courses'])}"
    )
    net.add_node(scode, label=scode, title=title, color=colour, size=size, font={"size": 10})

# Edges: subject -> each course it appears in
for scode, info in subject_to_courses.items():
    for ccode in info["courses"]:
        # Heavier edge if subject is shared
        width = 2 if len(info["courses"]) >= 2 else 0.5
        net.add_edge(scode, ccode, color="#cccccc", width=width)

net.set_options("""
{
  "physics": {
    "enabled": true,
    "barnesHut": {
      "gravitationalConstant": -3500,
      "centralGravity": 0.3,
      "springLength": 130,
      "springConstant": 0.05,
      "damping": 0.5
    },
    "stabilization": {"iterations": 250}
  },
  "interaction": {"hover": true, "tooltipDelay": 100, "navigationButtons": true, "keyboard": true},
  "nodes": {"font": {"size": 12, "face": "Inter, Arial, sans-serif"}}
}
""")

net.write_html(str(OUT), notebook=False, open_browser=False)

# Inject a header listing the shared subjects
shared_list_html = "".join(
    f"<li style='margin:2px 0;'><code>{sc}</code> {info['name']} <span style='color:#888;'>({', '.join(info['courses'])})</span></li>"
    for sc, info in sorted(shared.items(), key=lambda kv: -len(kv[1]['courses']))[:30]
)
header = f"""
<div style='font-family:Inter,Arial,sans-serif;padding:14px 24px;border-bottom:1px solid #eee;background:#fafafa;'>
  <div style='font-size:20px;font-weight:600;'>Subjects shared across UTS programs - {YEAR}</div>
  <div style='font-size:13px;color:#666;margin-top:4px;'>
    Big coloured nodes = degree programs. Small nodes = subjects within them.
    <strong>Gold subjects</strong> appear in 2+ programs and naturally settle in the middle of the layout
    (they are "shared subjects").
    Grey subjects appear in only one program.
  </div>
  <div style='margin-top:8px;font-size:12px;color:#444;'>
    {len(courses)} programs analysed. {len(subject_to_courses)} unique subjects total.
    <strong>{len(shared)}</strong> subjects shared across 2+ programs.
  </div>
  <details style='margin-top:8px;font-size:12px;'>
    <summary style='cursor:pointer;color:#3498db;'>List of shared subjects</summary>
    <ul style='margin:6px 0 0 16px;padding:0;'>{shared_list_html}</ul>
  </details>
</div>
"""
html = OUT.read_text(encoding="utf-8")
html = html.replace("<body>", "<body>" + header, 1)
OUT.write_text(html, encoding="utf-8")

print(f"\nWrote {OUT.name}")
