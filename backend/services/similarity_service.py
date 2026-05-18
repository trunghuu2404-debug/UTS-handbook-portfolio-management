import json
from pathlib import Path
from functools import lru_cache

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parents[2]
SUBJECTS_DIR = BASE_DIR / "dataset" / "subjects_archive"
YEARS = ["2023", "2024", "2025", "2026"]


def list_to_text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value if v)
    return str(value or "")


def build_subject_text(subject: dict) -> str:
    return " ".join(
        [
            str(subject.get("name", "") or ""),
            str(subject.get("description", "") or ""),
            list_to_text(subject.get("learning_outcomes", [])),
            str(subject.get("learning_and_teaching_activities", "") or ""),
        ]
    ).strip()


@lru_cache(maxsize=1)
def load_subject_dataframe():
    rows = []

    for year in YEARS:
        file_path = SUBJECTS_DIR / f"{year}_subjects.json"

        if not file_path.exists():
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            subjects = json.load(f)

        for subject_code, subject in subjects.items():
            rows.append(
                {
                    "year": str(year),
                    "subject_code": str(subject_code),
                    "subject_name": subject.get("name", ""),
                    "study_level": subject.get("study_level", ""),
                    "faculty": subject.get("faculty", ""),
                    "credit_points": subject.get("credit_points", ""),
                    "total_workload_hours": subject.get("total_workload_hours", ""),
                    "description": str(subject.get("description", "") or ""),
                    "learning_outcomes": list_to_text(
                        subject.get("learning_outcomes", [])
                    ),
                    "learning_activities": str(
                        subject.get("learning_and_teaching_activities", "") or ""
                    ),
                    "combined_text": build_subject_text(subject),
                }
            )

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError("No subject data found in dataset/subjects_archive.")

    return df


def tfidf_similarity(text_1: str, text_2: str) -> float:
    text_1 = str(text_1 or "").strip()
    text_2 = str(text_2 or "").strip()

    if not text_1 or not text_2:
        return 0.0

    vectorizer = TfidfVectorizer(
        stop_words="english",
        lowercase=True,
        max_features=5000,
    )

    matrix = vectorizer.fit_transform([text_1, text_2])
    return float(cosine_similarity(matrix[0], matrix[1])[0][0])


def classify_similarity(score: float) -> str:
    if score >= 0.85:
        return "Likely subject twin / very strong overlap"
    if score >= 0.70:
        return "Strong subject sibling / related content"
    if score >= 0.60:
        return "Moderate similarity / possible relationship"
    return "Weak similarity / likely unrelated"


def compare_subjects(
    subject_code_1: str, subject_code_2: str, year_1: str, year_2: str
):
    df = load_subject_dataframe()

    match_1 = df[
        (df["subject_code"] == str(subject_code_1)) & (df["year"] == str(year_1))
    ]

    match_2 = df[
        (df["subject_code"] == str(subject_code_2)) & (df["year"] == str(year_2))
    ]

    if match_1.empty:
        return None, f"{subject_code_1} not found in {year_1}"

    if match_2.empty:
        return None, f"{subject_code_2} not found in {year_2}"

    s1 = match_1.iloc[0]
    s2 = match_2.iloc[0]

    overall_score = tfidf_similarity(s1["combined_text"], s2["combined_text"])
    description_score = tfidf_similarity(s1["description"], s2["description"])
    outcomes_score = tfidf_similarity(s1["learning_outcomes"], s2["learning_outcomes"])
    activities_score = tfidf_similarity(
        s1["learning_activities"], s2["learning_activities"]
    )

    result = {
        "subject_1": {
            "code": subject_code_1,
            "name": s1["subject_name"],
            "year": year_1,
            "study_level": s1.get("study_level", ""),
            "faculty": s1.get("faculty", ""),
            "credit_points": s1.get("credit_points", ""),
            "workload_hours": s1.get("total_workload_hours", ""),
            "description": s1.get("description", ""),
            "learning_outcomes": s1.get("learning_outcomes", ""),
            "learning_activities": s1.get("learning_activities", ""),
        },
        "subject_2": {
            "code": subject_code_2,
            "name": s2["subject_name"],
            "year": year_2,
            "study_level": s2.get("study_level", ""),
            "faculty": s2.get("faculty", ""),
            "credit_points": s2.get("credit_points", ""),
            "workload_hours": s2.get("total_workload_hours", ""),
            "description": s2.get("description", ""),
            "learning_outcomes": s2.get("learning_outcomes", ""),
            "learning_activities": s2.get("learning_activities", ""),
        },
        "similarity_score": round(overall_score, 4),
        "similarity_percentage": round(overall_score * 100, 2),
        "classification": classify_similarity(overall_score),
        "field_scores": {
            "description": {
                "score": round(description_score, 4),
                "percentage": round(description_score * 100, 2),
            },
            "learning_outcomes": {
                "score": round(outcomes_score, 4),
                "percentage": round(outcomes_score * 100, 2),
            },
            "learning_activities": {
                "score": round(activities_score, 4),
                "percentage": round(activities_score * 100, 2),
            },
        },
        "method": "TF-IDF vectorisation with cosine similarity",
    }

    return result, None


def get_top_similar_subjects(subject_code: str, year: str, limit: int = 5):
    df = load_subject_dataframe()

    target_match = df[
        (df["subject_code"] == str(subject_code)) & (df["year"] == str(year))
    ]

    if target_match.empty:
        return None, f"{subject_code} not found in {year}"

    target = target_match.iloc[0]
    results = []

    for _, candidate in df.iterrows():
        same_subject = candidate["subject_code"] == str(subject_code) and candidate[
            "year"
        ] == str(year)

        if same_subject:
            continue

        score = tfidf_similarity(target["combined_text"], candidate["combined_text"])

        results.append(
            {
                "code": candidate["subject_code"],
                "name": candidate["subject_name"],
                "year": candidate["year"],
                "similarity_score": round(score, 4),
                "similarity_percentage": round(score * 100, 2),
                "classification": classify_similarity(score),
            }
        )

    results = sorted(
        results,
        key=lambda item: item["similarity_score"],
        reverse=True,
    )[:limit]

    response = {
        "target_subject": {
            "code": str(subject_code),
            "name": target["subject_name"],
            "year": str(year),
        },
        "top_matches": results,
        "method": "TF-IDF vectorisation with cosine similarity",
    }

    return response, None
