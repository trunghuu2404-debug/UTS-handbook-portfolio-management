# Project 13 — Visualisations

Eden's slice of the project: turning the team's scraped data + similarity analysis
into the actual visual mapping/dashboard pieces called out in the brief.

All four visualisations are built as **standalone HTML files** — open in any browser,
no server, no Neo4j, no setup. They read the team's existing CSVs / JSON files
directly.

## What's here

### 1. Subject similarity network (the "twins / siblings" story)
- Maps to brief: *"visual mapping tool that can trace similar or equivalent subjects across programs"*
- Files: `subject_similarity_network_2024.html`, `subject_similarity_network_2023.html`
- Built by: `build_similarity_network.py`
- Reads: `similarity_analysis/{YEAR}_strong_subject_similarity_matches.csv` + `dataset/subjects_archive/{YEAR}_subjects.json`
- What you see: every subject with at least one twin/sibling drawn as a node, with
  edges weighted by cosine similarity score. Faculty colour-coded. ~100 nodes, ~600
  edges per year. Clusters represent groups of related subjects (e.g. all the
  language subjects, all the cloud computing subjects, all the AI/ML subjects).

### 2. Course structure sunburst (the "what's in the degree" story)
- Maps to brief: *"dashboard or interactive interface enabling users to explore relationships and dependencies"*
- Files: `course_structure_sunburst_C04443_2026.html` (Master of AI), `course_structure_sunburst_C10474_2026.html` (Bachelor of AI)
- Built by: `build_course_sunburst.py`
- Reads: `dataset/{COURSE_FOLDER}/{YEAR}.json`
- What you see: the entire degree as nested rings — Course → Core/Options/Sub-Majors → Specialisations → Subjects. Segment size = credit points. Click any wedge to zoom in.

### 3. Subject evolution timeline (the "change tracking" story)
- Maps to brief: *"change-tracking mechanism that records and visualises how a subject evolves across years"*
- File: `subject_evolution_41040.html` (Introduction to AI, 2023→2026)
- Built by: `build_evolution_timeline.py`
- Reads: all four `dataset/subjects_archive/{YEAR}_subjects.json` files
- What you see: four bar charts (credit points, learning-outcome count, description length, requisite count) plus a unified diff of what literally changed in the description and learning outcomes between adjacent years. Real finding: faculty was renamed between 2024 and 2025.

### 4. Prerequisite graph (the "dependency network" story)
- Maps to brief: *"dependencies and prerequisite networks"*
- Files: `prerequisite_graph_{CODE}_{YEAR}.html`
- Built by: `build_prerequisite_graph.py`
- Reads: `dataset/subjects_archive/{YEAR}_subjects.json`
- Best demo subjects: **41001 (Cloud Computing)** and **41043 (Natural Language Processing)** — both have ~6 nodes / 7-9 edges. Walks the prerequisite chain up to 3 levels back. Green arrows = prerequisites, red dashed = anti-requisites.

## How to regenerate any of these

```bash
cd visualisations
pip install pandas plotly pyvis
python build_similarity_network.py
python build_course_sunburst.py
python build_evolution_timeline.py
python build_prerequisite_graph.py
```

Each script has the year/course/subject configurable at the top.

## How this fits the team's existing work

- The team's `frontend/app.py` (Streamlit) currently shows data as **lists and JSON**.
  The Tab 4 ("Requisite Graph") even has a comment that says *"pipe this into D3.js,
  Cytoscape, or vis-network on the frontend for visual rendering"*. These four HTML
  files are exactly that visual layer — they can either be linked from the Streamlit
  app (`st.components.v1.html(open("file.html").read(), height=900)`) or shown as
  standalone deliverables.
- The similarity network closes the loop on `similarity_analysis/nlp_comparison.py` —
  that script produced the CSVs, and this turns those CSVs into the picture the
  brief explicitly asks for.
- Nothing here depends on Neo4j or the FastAPI backend running. Means it works
  even if the backend host is offline during marking.

## Future / nice-to-have

- Year-over-year similarity diff (which twin pairs appeared/disappeared between 2023 and 2024)
- Cross-program overlap diagram (which subjects appear in BOTH the Bachelor and Master AI degrees)
- Embedding the four HTML files inside the Streamlit `app.py` as new tabs
