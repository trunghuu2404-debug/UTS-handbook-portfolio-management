# UTS Curriculum Digital Twin
 
A graph-powered platform for exploring UTS course structures, subject details,
requisite relationships, and subject similarity — built on Neo4j, FastAPI, and
two frontend options: a production HTML/CSS/JS frontend (SPI) and a Streamlit
testing app.
 
---
 
## Project Overview
 
The UTS Curriculum Digital Twin ingests UTS handbook data into a Neo4j graph
database and exposes it through a REST API with interactive visualizations. It
enables curriculum analysts to explore how courses are structured, how subjects
relate to each other across programs, and how individual subjects have evolved
over time.
 
---
 
## Tech Stack
 
| Layer | Technology |
|---|---|
| Graph database | Neo4j |
| Backend API | FastAPI + Uvicorn |
| Visualizations | Plotly, D3.js, vis.js, pyvis |
| Similarity engine | scikit-learn (TF-IDF + cosine similarity) |
| Main frontend | HTML / CSS / JavaScript (`SPI.html`) |
| Testing frontend | Streamlit (`app.py`) |
 
---
 
## Project Structure
 
```
uts-digital-twin/
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
│   └── {YEAR}_{type}_subject_similarity_matches.csv
│
├── backend/
│   ├── main.py                                # FastAPI entry point
│   │
│   ├── database/
│   │   ├── neo4j.py                           # Neo4j driver and run_query helper
│   │   └── create_indexes.py                  # Run automatically on startup
│   │
│   ├── models/
│   │   └── schemas.py                         # Pydantic response models
│   │
│   ├── services/
│   │   ├── course_service.py
│   │   ├── subject_service.py
│   │   ├── graph_service.py
│   │   ├── similarity_service.py              # TF-IDF similarity engine
│   │   ├── viz_service.py                     # Neo4j queries for visualizations
│   │   └── cache_warmer.py                    # Pre-warms all viz HTML on startup
│   │
│   ├── routes/
│   │   ├── course_routes.py
│   │   ├── subject_routes.py
│   │   ├── graph_routes.py
│   │   ├── similarity_routes.py
│   │   └── viz_routes.py                      # /viz endpoints (return HTML pages)
│   │
│   └── visualizations/
│       ├── dynamic_viz.py                     # Sunburst, D3 course tree, subject evolution
│       ├── prereq_graph.py                    # vis.js prerequisite graph
│       ├── shared_subjects.py                 # pyvis shared subjects network
│       └── similarity_network.py              # pyvis similarity network
│
├── frontend/
│   ├── SPI.html                               # Main HTML/CSS/JS frontend
│   ├── styles.css                             # Stylesheet for SPI.html
│   └── app.py                                 # Streamlit testing frontend
│
│
├── post_2025_scrapping.py                      # Post-2025 Handbook scrapper 
│
├── pre_2025_scrapping.py                       # Pre-2025 Handbook scrapper
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
- [VS Code Live Server extension](https://marketplace.visualstudio.com/items?itemName=ritwickdey.LiveServer)
  (required for running `SPI.html`)
### Installation
 
```bash
# Clone the repository
git clone <repo-url>
cd uts-digital-twin
 
# Install Python dependencies
pip install requirment.txt
```
 
### 1. Import data into Neo4j
 
```bash
python database_importer.py
```
 
### 2. Set up Neo4j

1. Download and install [Neo4j Desktop](https://neo4j.com/download/)
2. Open Neo4j Desktop, then create a new project and add a local DBMS
3. Set a password when prompted, then start the DBMS
4. Open `backend/database/neo4j.py` and update the credentials to match:

```python
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "your_password_here"   # ← change this
```

The URI and username can stay as defaults unless you changed them during setup.

### 3. Start the backend
 
```bash
cd backend
uvicorn main:app --reload --port 8000
```
 
On startup the server automatically:
- Creates and verifies all Neo4j indexes
- Pre-warms all visualization caches in a background thread (~8 seconds, ~224 items)
API docs available at http://localhost:8000/docs
 
---
 
## 4. Running the Frontend
 
### Option A — Main frontend (SPI.html)
 
`SPI.html` uses `fetch()` to read local JSON and CSV files from `dataset/` and
`similarity_analysis/`. Browsers block `fetch()` on `file://` URLs for security
reasons, so the file must be served over HTTP using VS Code Live Server:
 
1. Install the **Live Server** extension in VS Code
   (`ritwickdey.LiveServer` from the Extensions marketplace)
2. Open the **project root folder** in VS Code (not just the `frontend/` subfolder —
   the paths `../dataset` and `../similarity_analysis` resolve relative to the root)
3. Right-click `frontend/SPI.html` → **Open with Live Server**
4. The app opens at `http://127.0.0.1:5500/frontend/SPI.html`
The FastAPI backend must be running at `http://localhost:8000` for the
following features to work: course sunburst, course tree, prerequisite graph,
subject evolution, subject twins network, shared subjects, and subject
similarity comparison. Course and subject browsing work offline from local
files without the backend.
 
### Option B — Streamlit testing app
 
```bash
cd frontend
streamlit run app.py
```
 
Open http://localhost:8501. All features in the Streamlit app require the
FastAPI backend to be running.
 
---
 
## Feature Comparison
 
| Feature | SPI.html | Streamlit |
|---|---|---|
| Course browsing | Local JSON | FastAPI `/courses` |
| Course sunburst | FastAPI viz endpoint | FastAPI viz endpoint |
| Course tree (D3) | FastAPI viz endpoint | FastAPI viz endpoint |
| Subject browsing | Local JSON | FastAPI `/subjects` |
| Subject requisites | ✅ Yes | ✅ Yes |
| Prerequisite graph | FastAPI viz endpoint | FastAPI viz endpoint |
| Subject evolution | FastAPI viz endpoint | FastAPI viz endpoint |
| Subject twins network | FastAPI viz endpoint | FastAPI viz endpoint |
| Shared subjects | FastAPI viz endpoint | FastAPI viz endpoint |
| Subject similarity compare | FastAPI `/similarity/compare` + `/similarity/top` | FastAPI `/similarity/compare` + `/similarity/top` |
| Course structure metrics | ✅ Yes | ✅ Yes |
| UTS Handbook link | ✅ Sidebar shortcut | ❌ Not available |
| Requires Live Server | ✅ Yes | ❌ No |
| Works partially offline | ✅ Yes (browsing only) | ❌ No |
 
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
| GET | `/viz/subject/{code}/{year}/prereq-graph` | vis.js prerequisite graph |
| GET | `/viz/shared-subjects/{year}` | Bipartite shared subjects network |
| GET | `/viz/similarity/{year}` | Subject similarity network |
 
---
 
## Visualizations
 
**Course Sunburst** — Plotly radial chart where segment size represents credit
points. Click any wedge to zoom into that branch.
 
**Course Tree (D3)** — Top-down hierarchical tree of a course's block
structure. Collapsed to depth 2 by default; click blue/purple nodes to expand.
 
**Prerequisite Graph (vis.js)** — Starts with only the root subject visible.
Click any subject node to expand its prerequisites, anti-requisites, admission
requisites, and other requisite conditions. Click again to collapse.
 
**Subject Evolution** — Plotly metrics chart tracking credit points, learning
outcome count, and description length across 2023–2026, plus a colour-coded
text diff panel showing exactly what changed between adjacent years.
 
**Subject Twins Network** — pyvis force-directed graph of subjects connected
by textual similarity. Node colour = faculty. Edge colour = similarity band:
red ≥ 0.85, orange 0.70–0.84, yellow 0.60–0.69.
 
**Shared Subjects** — pyvis bipartite graph: large coloured nodes are programs,
small nodes are subjects. Gold nodes appear in 2+ programs.
 
---
 
## Performance
 
All visualization HTML is cached in memory using `functools.lru_cache`. The
cache warmer pre-fills all known courses and popular subjects on server startup
so the first user request is served from memory. Neo4j indexes on hot
properties ensure fast query execution.
 
---
 
## Notes
 
- Similarity CSV files in `similarity_analysis/` are pre-computed externally
  and are not generated by this application
- When running `SPI.html` with Live Server, open the **project root** in
  VS Code — not the `frontend/` subfolder — so that relative paths to
  `../dataset` and `../similarity_analysis` resolve correctly
- The backend viz endpoints must be running for iframe-based visualizations
  to load in `SPI.html`