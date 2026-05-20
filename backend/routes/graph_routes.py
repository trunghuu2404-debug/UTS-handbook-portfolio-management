from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from models.schemas import GraphResponse
from services import graph_service

router = APIRouter(prefix="/graph", tags=["Graph"])


@router.get("/subject/{subject_code}/version/{year}", response_model=GraphResponse)
def get_subject_requisite_graph(subject_code: str, year: int):
    graph = graph_service.get_subject_requisite_graph(subject_code, year)
    if not graph.nodes:
        raise HTTPException(
            status_code=404, detail=f"SubjectVersion '{subject_code}_{year}' not found."
        )
    return graph


@router.get("/aos/{aos_code}", response_model=GraphResponse)
def get_aos_graph(
    aos_code: str,
    year: Optional[int] = Query(default=None),
):
    graph = graph_service.get_aos_graph(aos_code, year)
    if not graph.nodes:
        raise HTTPException(
            status_code=404, detail=f"AreaOfStudy '{aos_code}' not found."
        )
    return graph
