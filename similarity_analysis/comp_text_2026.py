import json
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

YEAR = "2026"

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIR = BASE_DIR / "similarity_analysis"
OUTPUT_DIR.mkdir(exist_ok=True)

SUBJECTS_FILE = (
    BASE_DIR
    / "dataset"
    / "subjects_archive"
    / f"{YEAR}_subjects.json"
)

with open(SUBJECTS_FILE, "r", encoding="utf-8") as f:
    subjects = json.load(f)

rows = []

for subject_code, subject in subjects.items():

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

    combined_text = (
        f"{name}\n"
        f"{description}\n"
        f"{learning_outcomes}\n"
        f"{learning_activities}"
    )

    rows.append({
        "subject_code": subject_code,
        "subject_name": name,
        "combined_text": combined_text
    })


df = pd.DataFrame(rows)

df["combined_text"] = (
    df["combined_text"]
    .fillna("")
    .astype(str)
)

print(f"\nLoaded {YEAR} subjects:")
print(df.head())

print("\nStarting TF-IDF...\n")

vectorizer = TfidfVectorizer(
    stop_words="english",
    lowercase=True,
    max_features=5000
)

tfidf_matrix = vectorizer.fit_transform(
    df["combined_text"]
)

print("TF-IDF complete")
print(tfidf_matrix.shape)


similarity_matrix = cosine_similarity(
    tfidf_matrix
)

similarity_pairs = []

for i in range(len(df)):
    for j in range(i + 1, len(df)):

        similarity_pairs.append({
            "subject_1_code": df.iloc[i]["subject_code"],
            "subject_1_name": df.iloc[i]["subject_name"],
            "subject_2_code": df.iloc[j]["subject_code"],
            "subject_2_name": df.iloc[j]["subject_name"],
            "similarity_score": similarity_matrix[i][j]
        })


similarity_df = pd.DataFrame(similarity_pairs)

similarity_df = similarity_df.sort_values(
    by="similarity_score",
    ascending=False
)

print(f"\nTop 20 most similar {YEAR} subject pairs:\n")

print(
    similarity_df.head(20).to_string(index=False)
)

strong_matches = similarity_df[
    similarity_df["similarity_score"] >= 0.60
]

exclude_keywords = [
    "Language and Culture"
]

filtered_matches = strong_matches[
    ~strong_matches["subject_1_name"].str.contains(
        "|".join(exclude_keywords),
        case=False,
        na=False
    )
    &
    ~strong_matches["subject_2_name"].str.contains(
        "|".join(exclude_keywords),
        case=False,
        na=False
    )
]

similarity_df.to_csv(
    OUTPUT_DIR / f"{YEAR}_subject_similarity_results.csv",
    index=False
)

strong_matches.to_csv(
    OUTPUT_DIR / f"{YEAR}_strong_subject_similarity_matches.csv",
    index=False
)

filtered_matches.to_csv(
    OUTPUT_DIR / f"{YEAR}_filtered_subject_similarity_matches.csv",
    index=False
)

print(f"\nSaved {YEAR} similarity CSV files:")
print(f"{YEAR}_subject_similarity_results.csv")
print(f"{YEAR}_strong_subject_similarity_matches.csv")
print(f"{YEAR}_filtered_subject_similarity_matches.csv")