# UTS Curriculum Digital Twin
 
A graph-powered platform for exploring UTS course structures, subject details, requisite relationships, and subject similarity — built on Neo4j, FastAPI, and a Streamlit testing frontend.
 
---
 
## Project Overview
 
The UTS Curriculum Digital Twin ingests UTS handbook data into a Neo4j graph database and exposes it through a REST API with interactive visualizations. It enables curriculum analysts to explore how courses are structured, how subjects relate to each other across programs, and how individual subjects have evolved over time.
 
---
 
## Tech Stack
 
| Layer | Technology |
|---|---|
| Graph database | Neo4j |
| Backend API | FastAPI + Uvicorn |
| Visualizations | Plotly, D3.js, vis.js, pyvis |
| Similarity engine | scikit-learn (TF-IDF + cosine similarity) |
| Testing frontend | Streamlit |
| Future frontend | HTML / CSS / JavaScript |
 
---
 
## Project Structure
 
```
UTS-HANDBOOK-PORTFOLIO-MANAGEMENT/
│
├── dataset/                                   # Source JSON files from UTS handbook scraper
│   ├── C04443_Master of Artificial Intelligence/
│   │   └── 2023.json / 2024.json / 2025.json / 2026.json
│   ├── C10474_Bachelor of Artificial Intelligence/
│   │   └── 2023.json / 2024.json / 2025.json / 2026.json
│   └── subjects_archive/
│       └── 2023_subjects.json ... 2026_subjects.json
│
├── similarity_analysis/                       # Pre-computed similarity edge CSV files
│   └── {YEAR}_strong_subject_similarity_matches.csv
│
├── backend/
│   ├── main.py                                # FastAPI entry point + cache warmer on startup
│   │
│   ├── database/
│   │   ├── neo4j.py                           # Neo4j driver and run_query helper
│   │   └── create_indexes.py                  # One-time index creation script
│   │
│   ├── models/
│   │   └── schemas.py                         # Pydantic response models
│   │
│   ├── services/
│   │   ├── course_service.py                  # Course data queries
│   │   ├── subject_service.py                 # Subject data queries
│   │   ├── graph_service.py                   # Graph traversal queries
│   │   ├── similarity_service.py              # TF-IDF similarity engine
│   │   ├── viz_service.py                     # Neo4j queries for visualizations
│   │   └── cache_warmer.py                    # Pre-warms all viz HTML caches on startup
│   │
│   ├── routes/
│   │   ├── course_routes.py                   # /courses endpoints
│   │   ├── subject_routes.py                  # /subjects endpoints
│   │   ├── graph_routes.py                    # /graph endpoints
│   │   ├── similarity_routes.py               # /similarity endpoints
│   │   └── viz_routes.py                      # /viz endpoints (return HTML pages)
│   │
│   └── visualizations/
│       ├── dynamic_viz.py                     # Sunburst, D3 course tree, subject evolution
│       ├── prereq_graph.py                    # vis.js click-to-expand prerequisite graph
│       ├── shared_subjects.py                 # pyvis bipartite shared subjects network
│       └── similarity_network.py              # pyvis subject similarity network
│
├── frontend/
│   └── app.py                                 # Streamlit testing frontend
│
├──post_2025_scrapping.py                      # Post-2025 Handbook scrapper 
│
├──pre_2025_scrapping.py                       # Pre-2025 Handbook scrapper
│
└── database_importer.py                       # Imports dataset JSON files into Neo4j
```
 
---
 
## Getting Started
 
### Prerequisites
 
- Python 3.10+
- Neo4j 5.x running locally on `bolt://localhost:7687`
- Dataset JSON files in the `dataset/` folder
- Similarity CSV files in `similarity_analysis/`
### Installation
 
```bash
# Clone the repository
git clone <repo-url>
cd uts-digital-twin
 
# Install dependencies
pip install requirement.txt
```
 
### 1. Import data into Neo4j (run once)
 
```bash
python database_importer.py
```
 
### 2. Create Neo4j indexes (run once)
 
```bash
cd backend
python -m database.create_indexes
```
 
This creates range indexes on `Subject.code`, `SubjectVersion.year`, `Course.code`, and other hot properties. Safe to re-run.
 
### 3. Start the backend
 
```bash
cd backend
uvicorn main:app --reload --port 8000
```
 
The server starts immediately. A background thread pre-warms all visualization caches
 
API docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
### 4. Start the Streamlit frontend
 
```bash
cd frontend
streamlit run app.py
```
 
Open http://localhost:8501 in your browser.
 
---
 
## API Endpoints
 
### Courses
| Method | Endpoint | Description |
|---|---|---|
| GET | `/courses` | List all courses |
| GET | `/courses/{code}/versions` | List all versions of a course |
| GET | `/courses/{code}/graph` | Course graph nodes and relationships |
 
### Subjects
| Method | Endpoint | Description |
|---|---|---|
| GET | `/subjects/search?q=` | Search subjects by code or name |
| GET | `/subjects/{code}` | Subject detail with all versions |
| GET | `/subjects/{code}/version/{year}/requisites` | Requisites for a subject version |
 
### Similarity
| Method | Endpoint | Description |
|---|---|---|
| GET | `/similarity/compare` | Compare two subjects with TF-IDF |
| GET | `/similarity/top` | Top N most similar subjects |
 
### Visualizations (return self-contained HTML)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/viz/course/{code}/{year}/sunburst` | Plotly radial course structure |
| GET | `/viz/course/{code}/{year}/tree` | D3 hierarchical course tree |
| GET | `/viz/subject/{code}/evolution` | Subject evolution across years |
| GET | `/viz/subject/{code}/{year}/prereq-graph` | vis.js click-to-expand prerequisite graph |
| GET | `/viz/shared-subjects/{year}` | Bipartite shared subjects network |
| GET | `/viz/similarity/{year}` | Subject similarity network |
 
---
 
## Visualizations
 
**Course Sunburst** — Plotly radial chart where segment size represents credit points. Click any wedge to zoom into that branch. Built from JSON source files to preserve the full AoS hierarchy.
 
**Course Tree (D3)** — Top-down hierarchical tree of a course's block structure. Collapsed to depth 2 by default; click blue/purple nodes to expand. Supports zoom and pan.
 
**Prerequisite Graph (vis.js)** — Starts with only the root subject visible. Click any subject node to expand its direct prerequisites. Includes admission requisite (orange diamond) and other requisite (grey square) nodes. Click an expanded node again to collapse it.
 
**Subject Evolution** — Plotly charts tracking credit points, learning outcome count, description length, and requisite count across 2023–2026, plus a colour-coded text diff panel showing exactly what changed between adjacent years.
 
**Subject Twin Network** — pyvis graph of subjects connected by textual similarity (cosine ≥ 0.70). Node colour represents faculty. Edge colour represents similarity strength: red ≥ 0.90, orange 0.80–0.89, yellow 0.70–0.79.
 
**Shared Subjects** — Bipartite pyvis graph: large coloured nodes are programs, small nodes are subjects. Gold nodes appear in 2+ programs and float to the centre.
 
---
 
## Performance
 
All visualization HTML is cached in memory using `functools.lru_cache`:
- First request builds and caches the HTML
- Subsequent requests for the same course/subject/year are served instantly
- The cache warmer pre-fills all known courses and popular subjects on server startup
- Neo4j indexes on hot properties ensure fast query execution
---
 
## Frontend (Streamlit — Testing Only)
 
The Streamlit app is a temporary testing interface. It will be replaced by a proper HTML/CSS/JavaScript frontend that calls the same FastAPI endpoints directly. When that happens, `frontend/app.py` is deleted entirely — no backend changes are required.
 
The app is organized into four sections:
 
| Section | Features |
|---|---|
| Course Structure | Overview metrics, Sunburst, D3 Tree |
| Subject Details | Details, Requisites, Requisite Graph, Evolution |
| Subject Twin | Similarity Network, Shared Subjects |
| Subject Similarity | TF-IDF pairwise comparison, Top N similar |
 
---
 
## Notes
 
- Similarity CSV files (`similarity_analysis/`) are pre-computed externally and are not generated by this application
- The `create_indexes.py` script only needs to be run once per Neo4j database
- The cache warmer runs automatically on every server start — no manual action needed
- Course structure is read from JSON source files (not Neo4j) to preserve the full Area of Study nesting which Neo4j's HAS_CHILD traversal cannot fully reconstruct