"""
Interactive pyvis subject-similarity network.
Edge weights come from pre-computed CSV files in similarity_analysis/.
Node metadata (faculty, CP, study level) comes from Neo4j via viz_service.

Public API:
    build_similarity_network_html(year="2026") -> str
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
from pyvis.network import Network

from services.viz_service import get_subjects_metadata

# Configurable: set SIMILARITY_ANALYSIS_DIR env var to override
_DEFAULT_SIM_DIR = Path(__file__).resolve().parent.parent.parent / "similarity_analysis"
SIMILARITY_DIR = Path(os.getenv("SIMILARITY_ANALYSIS_DIR", str(_DEFAULT_SIM_DIR)))

_FACULTY_COLOURS: dict = {
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
_DEFAULT_COLOUR = "#bbbbbb"


@lru_cache(maxsize=8)
def build_similarity_network_html(year: str = "2026") -> str:
    """
    Return a self-contained pyvis similarity-network HTML page.
    Edge colour:  red >= 0.90, orange 0.80–0.89, yellow 0.70–0.79.
    Node colour:  faculty colour from the Neo4j graph.
    """
    csv_path = SIMILARITY_DIR / f"{year}_strong_subject_similarity_matches.csv"
    if not csv_path.exists():
        return (
            f"<div style='padding:24px;color:#a00;'>"
            f"Similarity CSV not found: {csv_path}<br>"
            f"Set SIMILARITY_ANALYSIS_DIR env var if the folder is elsewhere.</div>"
        )

    edges = pd.read_csv(csv_path)
    subjects = get_subjects_metadata(int(year))

    net = Network(
        height="850px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222",
        directed=False,
        cdn_resources="in_line",
    )

    codes_in_edges = set(edges["subject_1_code"].astype(str)) | set(
        edges["subject_2_code"].astype(str)
    )

    # Nodes
    for code in codes_in_edges:
        s = subjects.get(code, {})
        name = s.get("name", code)
        faculty = s.get("faculty", "Unknown")
        colour = _FACULTY_COLOURS.get(faculty, _DEFAULT_COLOUR)
        title = (
            f"<b>{name}</b><br>"
            f"Code: {code}<br>"
            f"Faculty: {faculty}<br>"
            f"Credit points: {s.get('credit_points', '—')}<br>"
            f"Level: {s.get('study_level', '—')}"
        )
        net.add_node(code, label=code, title=title, color=colour, size=14)

    # Edges
    for _, row in edges.iterrows():
        score = float(row["similarity_score"])
        width = max(1.0, 1.0 + (score - 0.7) * 12)
        colour = (
            "#d62728" if score >= 0.9 else ("#ff7f0e" if score >= 0.8 else "#f1c40f")
        )
        title = (
            f"{row['subject_1_name']} ({row['subject_1_code']})<br>&harr;<br>"
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
          "gravitationalConstant": -8000, "centralGravity": 0.2,
          "springLength": 120, "springConstant": 0.04, "damping": 0.4
        },
        "minVelocity": 0.75,
        "stabilization": {"iterations": 200}
      },
      "interaction": {
        "hover": true, "tooltipDelay": 100,
        "navigationButtons": true, "keyboard": true
      },
      "nodes": {"font": {"size": 14, "face": "Inter, Arial, sans-serif"}}
    }
    """)

    html = net.generate_html()

    header = (
        f"<div style='font-family:Inter,Arial,sans-serif;padding:14px 24px;"
        f"border-bottom:1px solid #eee;background:#fafafa;'>"
        f"<div style='font-size:20px;font-weight:600;'>"
        f"UTS Subject Similarity Network &middot; {year}</div>"
        f"<div style='font-size:13px;color:#666;margin-top:4px;'>"
        f"Each node = a UTS subject. An edge connects two subjects whose descriptions "
        f"and learning outcomes are textually similar. "
        f"Hover for details &middot; drag to move &middot; scroll to zoom.</div>"
        f"<div style='margin-top:8px;font-size:12px;display:flex;gap:18px;flex-wrap:wrap;'>"
        f"<span><span style='display:inline-block;width:24px;height:3px;"
        f"background:#d62728;vertical-align:middle;'></span> &ge; 0.90 likely twin</span>"
        f"<span><span style='display:inline-block;width:24px;height:3px;"
        f"background:#ff7f0e;vertical-align:middle;'></span> 0.80&ndash;0.90 strong sibling</span>"
        f"<span><span style='display:inline-block;width:24px;height:3px;"
        f"background:#f1c40f;vertical-align:middle;'></span> 0.70&ndash;0.80 related</span>"
        f"<span style='margin-left:18px;color:#888;'>Node colour = faculty</span></div>"
        f"</div>"
    )
    return html.replace("<body>", "<body>" + header, 1)
