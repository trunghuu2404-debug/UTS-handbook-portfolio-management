"""
Build interactive HTML network visualisations for subject similarity.
Generates 2023, 2024, 2025 and 2026 networks.
"""

import json
from pathlib import Path

import pandas as pd
from pyvis.network import Network

YEARS = ["2023", "2024", "2025", "2026"]
REPO = Path(__file__).resolve().parent.parent
VIZ_DIR = REPO / "visualisations"

FACULTY_COLOURS = {
    "Engineering and Information Technology": "#1f77b4",
    "Business": "#2ca02c",
    "Arts and Social Sciences": "#9467bd",
    "Design, Architecture and Building": "#ff7f0e",
    "Health": "#d62728",
    "Law": "#8c564b",
    "Science": "#17becf",
    "Transdisciplinary Innovation": "#e377c2",
    "Graduate Research School": "#7f7f7f",
}
DEFAULT_COLOUR = "#bbbbbb"

for YEAR in YEARS:
    edges_csv = REPO / "similarity_analysis" / f"{YEAR}_strong_subject_similarity_matches.csv"
    subjects_json = REPO / "dataset" / "subjects_archive" / f"{YEAR}_subjects.json"
    out = VIZ_DIR / f"subject_similarity_network_{YEAR}.html"

    if not edges_csv.exists():
        print(f"Skipping {YEAR}: missing {edges_csv}")
        continue

    if not subjects_json.exists():
        print(f"Skipping {YEAR}: missing {subjects_json}")
        continue

    edges = pd.read_csv(edges_csv)
    print(f"Loaded {len(edges)} similarity matches from {edges_csv.name}")

    with open(subjects_json, encoding="utf-8") as f:
        subjects = json.load(f)

    print(f"Loaded {len(subjects)} subjects from {subjects_json.name}")

    net = Network(
        height="850px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222",
        notebook=False,
        directed=False,
        cdn_resources="in_line",
    )

    codes_in_edges = set(edges["subject_1_code"].astype(str)) | set(edges["subject_2_code"].astype(str))

    for code in codes_in_edges:
        s = subjects.get(code, {})
        name = s.get("name", code)
        faculty = s.get("faculty", "Unknown")
        colour = FACULTY_COLOURS.get(faculty, DEFAULT_COLOUR)

        title = (
            f"<b>{name}</b><br>"
            f"Code: {code}<br>"
            f"Faculty: {faculty}<br>"
            f"Credit points: {s.get('credit_points', '—')}<br>"
            f"Level: {s.get('study_level', '—')}"
        )

        net.add_node(code, label=code, title=title, color=colour, size=14)

    for _, row in edges.iterrows():
        score = float(row["similarity_score"])
        width = max(1, 1 + (score - 0.7) * 12)

        if score >= 0.9:
            colour = "#d62728"
        elif score >= 0.8:
            colour = "#ff7f0e"
        else:
            colour = "#f1c40f"

        title = (
            f"{row['subject_1_name']} ({row['subject_1_code']})<br>"
            f"↔<br>"
            f"{row['subject_2_name']} ({row['subject_2_code']})<br>"
            f"Similarity: {score:.3f}"
        )

        net.add_edge(
            str(row["subject_1_code"]),
            str(row["subject_2_code"]),
            value=score,
            width=width,
            color=colour,
            title=title,
        )

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -8000,
          "centralGravity": 0.2,
          "springLength": 120,
          "springConstant": 0.04,
          "damping": 0.4
        },
        "minVelocity": 0.75,
        "stabilization": {"iterations": 200}
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "navigationButtons": true,
        "keyboard": true
      },
      "nodes": {
        "font": {"size": 14, "face": "Inter, Arial, sans-serif"}
      }
    }
    """)

    net.write_html(str(out), notebook=False, open_browser=False)

    html = out.read_text(encoding="utf-8")
    header = f"""
    <div style="font-family:Inter,Arial,sans-serif;padding:14px 24px;border-bottom:1px solid #eee;background:#fafafa;">
      <div style="font-size:20px;font-weight:600;">UTS Subject Similarity Network · {YEAR}</div>
      <div style="font-size:13px;color:#666;margin-top:4px;">
        Each node = a UTS subject. An edge connects two subjects whose descriptions and learning outcomes
        are textually similar. Hover for details, drag to move, scroll to zoom.
      </div>
      <div style="margin-top:8px;font-size:12px;display:flex;gap:18px;flex-wrap:wrap;">
        <span><span style="display:inline-block;width:24px;height:3px;background:#d62728;vertical-align:middle;"></span> ≥ 0.90 likely twin</span>
        <span><span style="display:inline-block;width:24px;height:3px;background:#ff7f0e;vertical-align:middle;"></span> 0.80–0.90 strong sibling</span>
        <span><span style="display:inline-block;width:24px;height:3px;background:#f1c40f;vertical-align:middle;"></span> 0.70–0.80 related</span>
        <span style="margin-left:18px;color:#888;">Node colour = faculty</span>
      </div>
    </div>
    """

    html = html.replace("<body>", "<body>" + header, 1)
    out.write_text(html, encoding="utf-8")

    print(f"✅ Wrote {out}")
    print(f"   nodes: {len(codes_in_edges)}   edges: {len(edges)}")
