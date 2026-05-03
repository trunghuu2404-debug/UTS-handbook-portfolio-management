import json
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

YEARS = ["2023", "2024", "2025", "2026"]

BASE_DIR = Path(__file__).resolve().parent.parent
SUBJECTS_DIR = BASE_DIR / "dataset" / "subjects_archive"

def build_subject_text(subject):
    name = subject.get("name", "")
    description = subject.get("description", "")

    learning_outcomes = subject.get("learning_outcomes", [])
    if isinstance(learning_outcomes, list):
        learning_outcomes = " ".join(learning_outcomes)
    else:
        learning_outcomes = str(learning_outcomes)

    learning_activities = subject.get(
        "learning_and_teaching_activities",
        ""
    )

    return (
        f"{name}\n"
        f"{description}\n"
        f"{learning_outcomes}\n"
        f"{learning_activities}"
    ).strip()

rows = []

for year in YEARS:
    file_path = SUBJECTS_DIR / f"{year}_subjects.json"

    with open(file_path, "r", encoding="utf-8") as f:
        subjects = json.load(f)

    for subject_code, subject in subjects.items():
        rows.append({
            "year": year,
            "subject_code": subject_code,
            "subject_name": subject.get("name", ""),
            "combined_text": build_subject_text(subject)
        })


df = pd.DataFrame(rows)
df["combined_text"] = df["combined_text"].fillna("").astype(str)

print(f"Loaded {len(df)} subject records across {len(YEARS)} years.")


vectorizer = TfidfVectorizer(
    stop_words="english",
    lowercase=True,
    max_features=5000
)

tfidf_matrix = vectorizer.fit_transform(df["combined_text"])

def compare_subjects(subject_code_1, subject_code_2, year_1="2026", year_2="2026"):
    match_1 = df[
        (df["subject_code"] == subject_code_1)
        & (df["year"] == year_1)
    ]

    match_2 = df[
        (df["subject_code"] == subject_code_2)
        & (df["year"] == year_2)
    ]

    if match_1.empty:
        return f"Error: {subject_code_1} not found in {year_1}"

    if match_2.empty:
        return f"Error: {subject_code_2} not found in {year_2}"

    index_1 = match_1.index[0]
    index_2 = match_2.index[0]

    similarity_score = cosine_similarity(
        tfidf_matrix[index_1],
        tfidf_matrix[index_2]
    )[0][0]

    similarity_score = float(similarity_score)

    if similarity_score >= 0.85:
        classification = "Likely subject twin / very strong overlap"
    elif similarity_score >= 0.70:
        classification = "Strong subject sibling / related content"
    elif similarity_score >= 0.60:
        classification = "Moderate similarity / possible relationship"
    else:
        classification = "Weak similarity / likely unrelated"

    return {
        "subject_1_year": year_1,
        "subject_1_code": subject_code_1,
        "subject_1_name": match_1.iloc[0]["subject_name"],
        "subject_2_year": year_2,
        "subject_2_code": subject_code_2,
        "subject_2_name": match_2.iloc[0]["subject_name"],
        "similarity_score": round(similarity_score, 4),
        "classification": classification
    }

print(compare_subjects("41040", "42172", "2026", "2026"))
print(compare_subjects("41001", "42904", "2025", "2025"))
print(compare_subjects("41025", "32555", "2024", "2024"))

print(compare_subjects("41040", "41040", "2023", "2024"))
print(compare_subjects("41040", "41040", "2024", "2025"))
print(compare_subjects("41040", "41040", "2025", "2026"))

print(compare_subjects("41001", "41001", "2023", "2026"))
print(compare_subjects("31256", "31256", "2023", "2026"))