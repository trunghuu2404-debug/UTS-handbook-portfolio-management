from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from models.schemas import CourseOut, CourseVersionOut, GraphResponse
from services import course_service

router = APIRouter(prefix="/courses", tags=["Courses"])


@router.get("", response_model=list[CourseOut])
def list_courses():
    return course_service.get_all_courses()


@router.get("/{course_code}/versions", response_model=list[CourseVersionOut])
def get_course_versions(course_code: str):
    versions = course_service.get_course_versions(course_code)
    if not versions:
        raise HTTPException(
            status_code=404, detail=f"Course '{course_code}' not found."
        )
    return versions


@router.get("/{course_code}/graph", response_model=GraphResponse)
def get_course_graph(
    course_code: str,
    year: Optional[int] = Query(default=None, description="Filter to a specific year"),
):
    graph = course_service.get_course_graph(course_code, year)
    if not graph.nodes:
        raise HTTPException(
            status_code=404, detail=f"No graph data for '{course_code}'."
        )
    return graph
