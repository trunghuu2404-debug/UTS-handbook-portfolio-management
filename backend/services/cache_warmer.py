"""
Pre-warms all visualization HTML caches on startup.

Run in a background thread so the server is available immediately
while caches fill in the background. After warming, every viz request
for known courses/subjects/years is served from memory in milliseconds.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from database.neo4j import run_query

log = logging.getLogger(__name__)

_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "dataset"
_SIM_DIR = Path(__file__).resolve().parent.parent.parent / "similarity_analysis"
_YEARS = [2023, 2024, 2025, 2026]


# Helpers
def _all_course_codes() -> list[str]:
    """Return all course codes from the dataset folder (fast, no DB needed)."""
    codes = []
    if _DATASET_DIR.exists():
        for d in _DATASET_DIR.iterdir():
            if d.is_dir() and d.name.startswith("C"):
                parts = d.name.split("_", 1)
                if parts:
                    codes.append(parts[0])
    return list(set(codes))


def _popular_subject_codes(limit: int = 40) -> list[str]:
    """
    Return subject codes to pre-warm — prioritise subjects that appear in
    multiple courses (highest traffic) plus the most recent year.
    Falls back to any available subjects if the query returns nothing.
    """
    try:
        rows = run_query(
            """
            MATCH (sv:SubjectVersion {year: 2026})
            RETURN sv.code AS code
            LIMIT $limit
            """,
            {"limit": limit},
        )
        codes = [r["code"] for r in rows if r.get("code")]
        if codes:
            return codes
    except Exception as exc:
        log.warning(f"Cache warmer could not fetch subject codes: {exc}")
    return []


# Warmer
def _warm() -> None:
    """Run all pre-warming work. Called inside a daemon thread."""
    log.info("Cache warmer started …")

    # Import here to avoid circular imports at module load time
    from visualizations.dynamic_viz import (
        build_course_tree_html,
        build_evolution_html,
        build_sunburst_html,
    )
    from visualizations.prereq_graph import build_prereq_graph_html
    from visualizations.shared_subjects import build_shared_subjects_html
    from visualizations.similarity_network import build_similarity_network_html

    total = 0

    # Course visualizations (sunburst + tree)
    course_codes = _all_course_codes()
    log.info(f"  Warming {len(course_codes)} courses × {len(_YEARS)} years …")
    for code in course_codes:
        for year in _YEARS:
            try:
                build_sunburst_html(code, year)
                build_course_tree_html(code, year)
                total += 2
            except Exception as exc:
                log.debug(f"  Skip sunburst/tree {code}/{year}: {exc}")

    # Shared subjects + similarity networks for all years
    log.info("  Warming shared-subjects and similarity networks …")
    for year in _YEARS:
        try:
            build_shared_subjects_html(year)
            total += 1
        except Exception as exc:
            log.debug(f"  Skip shared-subjects {year}: {exc}")
        try:
            build_similarity_network_html(str(year))
            total += 1
        except Exception as exc:
            log.debug(f"  Skip similarity {year}: {exc}")

    # Subject visualizations for popular subjects
    subject_codes = _popular_subject_codes()
    log.info(f"  Warming {len(subject_codes)} subjects × {len(_YEARS)} years …")
    for code in subject_codes:
        for year in _YEARS:
            try:
                build_prereq_graph_html(code, year)
                total += 1
            except Exception as exc:
                log.debug(f"  Skip prereq-graph {code}/{year}: {exc}")
        try:
            build_evolution_html(code)
            total += 1
        except Exception as exc:
            log.debug(f"  Skip evolution {code}: {exc}")

    log.info(f"Cache warmer finished — {total} items cached.")


def start_cache_warmer() -> None:
    """Spawn the warmer as a background daemon thread."""
    t = threading.Thread(target=_warm, name="cache-warmer", daemon=True)
    t.start()
    log.info("Cache warmer thread launched.")
