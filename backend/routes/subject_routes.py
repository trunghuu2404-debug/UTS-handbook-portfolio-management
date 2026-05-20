from fastapi import APIRouter, HTTPException, Query
from models.schemas import SubjectDetailOut, SubjectVersionOut, SubjectRequisitesOut
from services import subject_service

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get("/search")
def search_subjects(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, le=100),
):
    return subject_service.search_subjects(q, limit)


@router.get("/{subject_code}", response_model=SubjectDetailOut)
def get_subject_detail(subject_code: str):
    detail = subject_service.get_subject_detail(subject_code)
    if not detail:
        raise HTTPException(
            status_code=404, detail=f"Subject '{subject_code}' not found."
        )
    return detail


@router.get("/{subject_code}/version/{year}", response_model=SubjectVersionOut)
def get_subject_version(subject_code: str, year: int):
    sv = subject_service.get_subject_version(subject_code, year)
    if not sv:
        raise HTTPException(
            status_code=404, detail=f"SubjectVersion '{subject_code}_{year}' not found."
        )
    return sv


@router.get(
    "/{subject_code}/version/{year}/requisites", response_model=SubjectRequisitesOut
)
def get_subject_requisites(subject_code: str, year: int):
    reqs = subject_service.get_subject_requisites(subject_code, year)
    if not reqs:
        raise HTTPException(
            status_code=404, detail=f"SubjectVersion '{subject_code}_{year}' not found."
        )
    return reqs
