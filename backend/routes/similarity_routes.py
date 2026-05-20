from fastapi import APIRouter, HTTPException, Query

from services.similarity_service import compare_subjects, get_top_similar_subjects

router = APIRouter(prefix="/similarity", tags=["Similarity"])


@router.get("/compare")
def compare_two_subjects(
    subject_code_1: str = Query(..., description="First subject code"),
    subject_code_2: str = Query(..., description="Second subject code"),
    year_1: str = Query("2026", description="First subject year"),
    year_2: str = Query("2026", description="Second subject year"),
):
    result, error = compare_subjects(
        subject_code_1=subject_code_1,
        subject_code_2=subject_code_2,
        year_1=year_1,
        year_2=year_2,
    )

    if error:
        raise HTTPException(status_code=404, detail=error)

    return result


@router.get("/top")
def top_similar_subjects(
    subject_code: str = Query(..., description="Target subject code"),
    year: str = Query("2026", description="Target subject year"),
    limit: int = Query(5, description="Number of similar subjects to return"),
):
    result, error = get_top_similar_subjects(
        subject_code=subject_code,
        year=year,
        limit=limit,
    )

    if error:
        raise HTTPException(status_code=404, detail=error)

    return result
