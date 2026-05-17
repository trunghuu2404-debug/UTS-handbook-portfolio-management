"""
backend/visualizations/shared_subjects.py
-------------------------------------------
Bipartite pyvis graph: courses (large nodes) connected to subjects they contain.
Subjects appearing in 2+ courses float to the centre (shared subjects).
Data is sourced from Neo4j via viz_service.

Public API:
    build_shared_subjects_html(year=2026) -> str
"""

from __future__ import annotations

from pyvis.network import Network

from services.viz_service import get_shared_subjects_data

_COURSE_COLOURS = [
    "#e74c3c",
    "#3498db",
    "#2ecc71",
    "#f39c12",
    "#9b59b6",
    "#1abc9c",
]


def build_shared_subjects_html(year: int = 2026) -> str:
    """
    Return a self-contained pyvis bipartite HTML page.
    Gold nodes = subjects shared across 2+ programs.
    Grey nodes = subjects unique to one program.
    """
    courses = get_shared_subjects_data(year)

    if not courses:
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"No course data found for year {year}.</div>"
        )

    # Reverse-index: subject_code -> {name, courses: [course_code, ...]}
    subject_to_courses: dict = {}
    for ccode, cinfo in courses.items():
        for scode, sname in cinfo["subjects"].items():
            if scode not in subject_to_courses:
                subject_to_courses[scode] = {"name": sname, "courses": []}
            subject_to_courses[scode]["courses"].append(ccode)

    shared = {
        sc: info for sc, info in subject_to_courses.items() if len(info["courses"]) >= 2
    }

    net = Network(
        height="800px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222",
        directed=False,
        cdn_resources="in_line",
    )

    # Course nodes
    for idx, (ccode, cinfo) in enumerate(courses.items()):
        colour = _COURSE_COLOURS[idx % len(_COURSE_COLOURS)]
        title = (
            f"<b>{cinfo['name']}</b><br>"
            f"Code: {ccode}<br>"
            f"Subjects: {len(cinfo['subjects'])}"
        )
        net.add_node(
            ccode,
            label=cinfo["name"],
            title=title,
            color=colour,
            size=50,
            shape="dot",
            font={"size": 22, "face": "Inter, Arial, sans-serif", "color": "#000"},
        )

    # Subject nodes
    for scode, info in subject_to_courses.items():
        n = len(info["courses"])
        colour = "#f1c40f" if n >= 2 else "#bdc3c7"
        size = 16 if n >= 2 else 7
        title = (
            f"<b>{info['name']}</b><br>"
            f"Code: {scode}<br>"
            f"Appears in: {', '.join(info['courses'])}"
        )
        net.add_node(
            scode,
            label=scode,
            title=title,
            color=colour,
            size=size,
            font={"size": 10},
        )

    # Edges
    for scode, info in subject_to_courses.items():
        width = 2 if len(info["courses"]) >= 2 else 0.5
        for ccode in info["courses"]:
            net.add_edge(scode, ccode, color="#cccccc", width=width)

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -3500, "centralGravity": 0.3,
          "springLength": 130, "springConstant": 0.05, "damping": 0.5
        },
        "stabilization": {"iterations": 250}
      },
      "interaction": {
        "hover": true, "tooltipDelay": 100,
        "navigationButtons": true, "keyboard": true
      },
      "nodes": {"font": {"size": 12, "face": "Inter, Arial, sans-serif"}}
    }
    """)

    html = net.generate_html()

    # Build shared-subjects list for the header
    shared_items = sorted(shared.items(), key=lambda kv: -len(kv[1]["courses"]))[:30]
    shared_list = "".join(
        f"<li style='margin:2px 0;'><code>{sc}</code> {info['name']} "
        f"<span style='color:#888;'>({', '.join(info['courses'])})</span></li>"
        for sc, info in shared_items
    )

    header = (
        f"<div style='font-family:Inter,Arial,sans-serif;padding:14px 24px;"
        f"border-bottom:1px solid #eee;background:#fafafa;'>"
        f"<div style='font-size:20px;font-weight:600;'>"
        f"Subjects shared across UTS programs &middot; {year}</div>"
        f"<div style='font-size:13px;color:#666;margin-top:4px;'>"
        f"Coloured nodes = programs. "
        f"<strong style='color:#f1c40f;'>Gold</strong> = shared across 2+ programs. "
        f"Grey = unique to one program.</div>"
        f"<div style='margin-top:6px;font-size:12px;color:#444;'>"
        f"{len(courses)} programs &nbsp;&bull;&nbsp; "
        f"{len(subject_to_courses)} unique subjects &nbsp;&bull;&nbsp; "
        f"<strong>{len(shared)}</strong> shared across 2+ programs</div>"
        f"<details style='margin-top:6px;font-size:12px;'>"
        f"<summary style='cursor:pointer;color:#3498db;'>List of shared subjects</summary>"
        f"<ul style='margin:6px 0 0 16px;padding:0;'>{shared_list}</ul>"
        f"</details></div>"
    )
    return html.replace("<body>", "<body>" + header, 1)
