"""
FastAPI endpoints that return visualization HTML pages.
Each endpoint calls the appropriate visualization builder and streams back HTML.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from visualizations.dynamic_viz import (
    build_course_tree_html,
    build_evolution_html,
    build_sunburst_html,
)
from visualizations.prereq_graph import build_prereq_graph_html
from visualizations.shared_subjects import build_shared_subjects_html
from visualizations.similarity_network import build_similarity_network_html

router = APIRouter(prefix="/viz", tags=["Visualizations"])


# Course visualizations
@router.get("/course/{course_code}/{year}/sunburst", response_class=HTMLResponse)
def viz_course_sunburst(course_code: str, year: int = 2026):
    """Plotly sunburst of a course's structure for a given year."""
    return HTMLResponse(content=build_sunburst_html(course_code, year))


@router.get("/course/{course_code}/{year}/tree", response_class=HTMLResponse)
def viz_course_tree(course_code: str, year: int = 2026):
    """D3 hierarchical tree of a course's structure for a given year."""
    return HTMLResponse(content=build_course_tree_html(course_code, year))


# Subject visualizations
@router.get("/subject/{subject_code}/evolution", response_class=HTMLResponse)
def viz_subject_evolution(subject_code: str):
    """Plotly evolution timeline + diff for a subject across all available years."""
    return HTMLResponse(content=build_evolution_html(subject_code))


@router.get("/subject/{subject_code}/{year}/prereq-graph", response_class=HTMLResponse)
def viz_prereq_graph(subject_code: str, year: int = 2026):
    """Interactive vis.js prerequisite + anti-requisite graph for a subject."""
    return HTMLResponse(content=build_prereq_graph_html(subject_code, year))


# Cross-course / similarity visualizations
@router.get("/shared-subjects/{year}", response_class=HTMLResponse)
def viz_shared_subjects(year: int = 2026):
    """Pyvis bipartite graph of subjects shared across programs."""
    return HTMLResponse(content=build_shared_subjects_html(year))


@router.get("/similarity/{year}", response_class=HTMLResponse)
def viz_similarity_network(year: str = "2026"):
    """Pyvis subject-similarity network for a given year."""
    return HTMLResponse(content=build_similarity_network_html(year))
