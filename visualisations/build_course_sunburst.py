"""
build_course_sunburst.py
------------------------
Renders a UTS course's structure as an interactive Plotly sunburst.

Inner ring  = course
Mid ring(s) = structure blocks (Core, Options, Sub-Majors, Project Stream...)
Outer ring  = individual subjects, sized by credit points

Output: course_structure_sunburst_{COURSE_CODE}_{YEAR}.html
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import plotly.express as px
import pandas as pd

REPO = Path("/sessions/epic-affectionate-davinci/mnt/UTS-handbook-portfolio-management-main")

# --- Pick which course/year to render ---------------------------------------
COURSE_FOLDER = "C04443_Master of Artificial Intelligence"
YEAR = "2026"
COURSE_CODE = COURSE_FOLDER.split("_")[0]

JSON_PATH = REPO / "dataset" / COURSE_FOLDER / f"{YEAR}.json"
OUT_PATH = REPO / f"course_structure_sunburst_{COURSE_CODE}_{YEAR}.html"


def parse_cp(value):
    """Pull the integer out of strings like '6 CPs' or '30 Credit Points'."""
    if not value:
        return 0
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else 0


def walk(node, parent_label, rows, depth=0, max_depth=4):
    """Recursively flatten the nested course structure into (id, parent, label, value, level) rows.

    Only LEAVES (subjects) get a value. Parents are 0 and Plotly auto-sums them
    via branchvalues='remainder'. Mixing parent + child values causes silent
    render failures.
    """
    if depth > max_depth:
        return

    # --- Top-level structure block --------------------------------------------
    if "structure_name" in node:
        label = node["structure_name"]
        my_id = f"{parent_label} / {label}"
        rows.append(dict(id=my_id, parent=parent_label, label=label, value=0, level="block"))

        for subj in node.get("has_subject", []) or []:
            walk(subj, my_id, rows, depth + 1, max_depth)
        for aos in node.get("has_area_of_study", []) or []:
            walk(aos, my_id, rows, depth + 1, max_depth)
        for sub in node.get("have_sub_structures", []) or []:
            walk(sub, my_id, rows, depth + 1, max_depth)
        for cb in node.get("has_choice_block", []) or []:
            walk(cb, my_id, rows, depth + 1, max_depth)

    # --- Area of study (sub-major / major) ------------------------------------
    elif node.get("type") in ("Sub-Major", "Major", "Specialisation") or "have_structure" in node:
        label = node.get("name") or node.get("code", "AOS")
        my_id = f"{parent_label} / {label}"
        rows.append(dict(id=my_id, parent=parent_label, label=label, value=0, level="aos"))
        for sub in node.get("have_structure", []) or []:
            walk(sub, my_id, rows, depth + 1, max_depth)

    # --- Leaf subject ---------------------------------------------------------
    else:
        label = f"{node.get('code', '?')} {node.get('name', '')}".strip()
        cp = parse_cp(node.get("credit_points")) or 6
        my_id = f"{parent_label} / {label}"
        rows.append(dict(id=my_id, parent=parent_label, label=label, value=cp, level="subject"))


# --- Load + flatten ---------------------------------------------------------
with open(JSON_PATH, encoding="utf-8") as f:
    course = json.load(f)

course_label = course["course_name"]
rows = [dict(id=course_label, parent="", label=course_label, value=0, level="course")]
for block in course["structure"]:
    walk(block, course_label, rows)

df = pd.DataFrame(rows).drop_duplicates(subset=["id"])
print(f"{len(df)} nodes flattened from {COURSE_FOLDER}/{YEAR}")

# --- Patch: branches with no subject leaves (scraper missed them) -----------
# Plotly sunburst auto-sizes wedges from leaf values; branches with zero
# subject descendants would otherwise vanish. We inject a phantom "missing"
# leaf so the structure stays visible and is honestly labelled.
children_of = defaultdict(list)
for _, r in df.iterrows():
    if r["parent"]:
        children_of[r["parent"]].append(r["id"])
node_level = dict(zip(df["id"], df["level"]))


def has_subject_descendant(node_id):
    for c in children_of.get(node_id, []):
        if node_level.get(c) == "subject":
            return True
        if has_subject_descendant(c):
            return True
    return False


phantom_rows = []
for _, r in df.iterrows():
    if r["level"] in ("block", "aos") and not has_subject_descendant(r["id"]):
        phantom_rows.append(dict(
            id=f"{r['id']} / __missing__",
            parent=r["id"],
            label="(scraper data missing)",
            value=1,
            level="missing",
        ))

if phantom_rows:
    df = pd.concat([df, pd.DataFrame(phantom_rows)], ignore_index=True)
    print(f"  + injected {len(phantom_rows)} placeholder wedges for empty branches")

print(df["level"].value_counts())

# --- Plot -------------------------------------------------------------------
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
            f"<b>{course_label}</b> ({COURSE_CODE}) - {YEAR}<br>"
            f"<span style='font-size:13px;color:#666;'>"
            f"Course structure as a sunburst. Segment size = credit points. "
            f"Click any wedge to zoom in. Grey = branch present in handbook but not captured by the scraper."
            f"</span>"
        ),
        x=0.02,
        xanchor="left",
    ),
    margin=dict(t=90, l=20, r=20, b=20),
    font=dict(family="Inter, Arial, sans-serif", size=12),
    height=850,
)

fig.update_traces(
    hovertemplate="<b>%{label}</b><br>%{value} CP<br>type: %{customdata[0]}<extra></extra>",
    insidetextorientation="radial",
)

fig.write_html(OUT_PATH, include_plotlyjs=True)
print(f"\nWrote {OUT_PATH}")
