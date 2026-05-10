"""
build_similarity_network.py
---------------------------
Builds an interactive HTML network visualisation of "subject twins / siblings".

Inputs:
  - similarity_analysis/{YEAR}_strong_subject_similarity_matches.csv  (edges)
  - dataset/subjects_archive/{YEAR}_subjects.json                     (node metadata: faculty)

Output:
  - subject_similarity_network_{YEAR}.html  (open in any browser)

Run:
  python build_similarity_network.py
"""

import json
from pathlib import Path

import pandas as pd
from pyvis.network import Network

# --- Config -----------------------------------------------------------------
YEAR = "2023"
REPO = Path("/sessions/epic-affectionate-davinci/mnt/UTS-handbook-portfolio-management-main")
EDGES_CSV = REPO / "similarity_analysis" / f"{YEAR}_strong_subject_similarity_matches.csv"
SUBJECTS_JSON = REPO / "dataset" / "subjects_archive" / f"{YEAR}_subjects.json"
OUT = Path("/sessions/epic-affectionate-davinci/mnt/UTS-handbook-portfolio-management-main") / f"subject_similarity_network_{YEAR}.html"

# --- Load -------------------------------------------------------------------
edges = pd.read_csv(EDGES_CSV)
print(f"Loaded {len(edges)} similarity matches from {EDGES_CSV.name}")

with open(SUBJECTS_JSON, encoding="utf-8") as f:
    subjects = json.load(f)
print(f"Loaded {len(subjects)} subjects from {SUBJECTS_JSON.name}")

# --- Build graph ------------------------------------------------------------
net = Network(
    height="850px",
    width="100%",
    bgcolor="#ffffff",
    font_color="#222",
    notebook=False,
    directed=False,
    cdn_resources="in_line",
)

# A friendly colour per faculty so clusters become visually obvious
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

# Collect every code that appears on any edge
codes_in_edges = set(edges["subject_1_code"].astype(str)) | set(edges["subject_2_code"].astype(str))

# Add nodes
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

# Add edges (thicker = more similar)
for _, row in edges.iterrows():
    score = float(row["similarity_score"])
    width = 1 + (score - 0.7) * 12  # 0.7 -> 1, 1.0 -> 4.6
    # red for very high (twin), orange for high, yellow for moderate
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

# --- Physics + interaction --------------------------------------------------
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

# Generate HTML
net.write_html(str(OUT), notebook=False, open_browser=False)

# Inject a header + legend so it doesn't look like just a blob of dots
html = OUT.read_text(encoding="utf-8")
header = f"""
<div style="font-family:Inter,Arial,sans-serif;padding:14px 24px;border-bottom:1px solid #eee;background:#fafafa;">
  <div style="font-size:20px;font-weight:600;">UTS Subject Similarity Network · {YEAR}</div>
  <div style="font-size:13px;color:#666;margin-top:4px;">
    Each node = a UTS subject. An edge connects two subjects whose descriptions + learning outcomes
    are textually similar (cosine similarity ≥ 0.70). Hover for details · drag to move · scroll to zoom.
  </div>
  <div style="margin-top:8px;font-size:12px;display:flex;gap:18px;flex-wrap:wrap;">
    <span><span style="display:inline-block;width:24px;height:3px;background:#d62728;vertical-align:middle;"></span> ≥ 0.90 (likely twin)</span>
    <span><span style="display:inline-block;width:24px;height:3px;background:#ff7f0e;vertical-align:middle;"></span> 0.80 – 0.90 (strong sibling)</span>
    <span><span style="display:inline-block;width:24px;height:3px;background:#f1c40f;vertical-align:middle;"></span> 0.70 – 0.80 (related)</span>
    <span style="margin-left:18px;color:#888;">Node colour = faculty</span>
  </div>
</div>
"""
html = html.replace("<body>", "<body>" + header, 1)
OUT.write_text(html, encoding="utf-8")

print(f"\n✅ Wrote {OUT}")
print(f"   nodes: {len(codes_in_edges)}   edges: {len(edges)}")
