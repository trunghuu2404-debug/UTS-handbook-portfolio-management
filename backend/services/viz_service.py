"""
backend/services/viz_service.py
--------------------------------
All Neo4j queries that feed the visualization layer.

Every function returns plain Python dicts/lists so the visualization
modules need no knowledge of Neo4j or Cypher.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Optional

from database.neo4j import run_query

# Dataset folder: backend/services/ → backend/ → project root → dataset/
_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "dataset"


# ============================================================================
# Course data  (read from JSON — Neo4j cannot traverse AoS sub-structures)
# ============================================================================


@lru_cache(maxsize=16)
def get_course_data(course_code: str, year: int) -> Optional[dict]:
    """
    Return course data from the source JSON file.
    Reading from JSON is the reliable way to get the full AoS hierarchy
    (Sub-Majors, Choice Blocks, etc.) since those sub-structures require
    traversing AreaOfStudy nodes not captured by simple HAS_CHILD queries.
    """
    for course_dir in _DATASET_DIR.iterdir():
        if course_dir.is_dir() and course_dir.name.startswith(course_code):
            json_path = course_dir / f"{year}.json"
            if json_path.exists():
                return json.loads(json_path.read_text(encoding="utf-8"))
    return None


# ============================================================================
# Subject evolution data
# ============================================================================


@lru_cache(maxsize=32)
def get_subject_versions_all(subject_code: str) -> dict:
    """
    Return all yearly versions of a subject:
        {year: {name, description, learning_outcomes, credit_points, faculty,
                prereq_count, anti_count}}
    """
    version_rows = run_query(
        """
        MATCH (s:Subject {code: $code})-[:HAS_VERSION]->(sv:SubjectVersion)
        RETURN sv.year AS year,
               sv.name AS name,
               sv.credit_points AS credit_points,
               sv.description AS description,
               sv.learning_outcomes AS learning_outcomes,
               sv.faculty AS faculty
        ORDER BY sv.year
        """,
        {"code": subject_code},
    )

    versions = {}
    for r in version_rows:
        year = r["year"]
        if year is None:
            continue
        versions[int(year)] = {
            "name": r["name"] or subject_code,
            "credit_points": r["credit_points"] or "6",
            "description": r["description"] or "",
            "learning_outcomes": r["learning_outcomes"] or [],
            "faculty": r["faculty"] or "",
            "prereq_count": 0,
            "anti_count": 0,
        }

    # Prerequisite counts per year
    prereq_rows = run_query(
        """
        MATCH (s:Subject {code: $code})-[:HAS_VERSION]->(sv:SubjectVersion)
        OPTIONAL MATCH (sv)-[:PREREQUISITE]->(pv:SubjectVersion)
        RETURN sv.year AS year, count(pv) AS cnt
        """,
        {"code": subject_code},
    )
    for r in prereq_rows:
        if r["year"] in versions:
            versions[int(r["year"])]["prereq_count"] = r["cnt"] or 0

    # Anti-requisite counts per year
    anti_rows = run_query(
        """
        MATCH (s:Subject {code: $code})-[:HAS_VERSION]->(sv:SubjectVersion)
        OPTIONAL MATCH (sv)-[:ANTI_REQUISITE]->(av:SubjectVersion)
        RETURN sv.year AS year, count(av) AS cnt
        """,
        {"code": subject_code},
    )
    for r in anti_rows:
        if r["year"] in versions:
            versions[int(r["year"])]["anti_count"] = r["cnt"] or 0

    return versions


# ============================================================================
# Prerequisite tree and graph data
# ============================================================================


def get_prereq_subgraph(subject_code: str, year: int, max_depth: int = 4) -> dict:
    """
    Return the full prerequisite subgraph for a subject:
        {
            nodes: {code: {name, faculty, cp}},
            prereq_edges: [(prereq_code, target_code), ...],
            anti_edges:   [(code, anti_code), ...],
            admission_reqs: {code: [text, ...]},   # per subject
            other_reqs:     {code: [text, ...]},   # per subject
        }

    Note: Cypher does not allow parameters in variable-length relationship
    patterns ([:REL*1..$n] is invalid). We use a fixed max depth of 6 in
    Cypher and control the displayed depth in Python via build_prereq_tree_dict.
    """
    rows = run_query(
        """
        MATCH (root:Subject {code: $code})-[:HAS_VERSION]->(sv:SubjectVersion {year: $year})
        OPTIONAL MATCH (sv)-[:PREREQUISITE*1..6]->(prereq_sv:SubjectVersion {year: $year})
        WITH sv, collect(DISTINCT prereq_sv) AS prereq_svs
        UNWIND [sv] + prereq_svs AS any_sv
        WITH any_sv WHERE any_sv IS NOT NULL
        OPTIONAL MATCH (any_sv)-[:PREREQUISITE]->(direct_pre:SubjectVersion {year: $year})
        OPTIONAL MATCH (any_sv)-[:ANTI_REQUISITE]->(anti_sv:SubjectVersion {year: $year})
        RETURN DISTINCT
            any_sv.code AS code,
            any_sv.name AS name,
            any_sv.faculty AS faculty,
            any_sv.credit_points AS cp,
            collect(DISTINCT direct_pre.code) AS prereq_codes,
            collect(DISTINCT anti_sv.code) AS anti_codes
        """,
        {"code": subject_code, "year": year},
    )

    nodes: dict = {}
    prereq_edges: list = []
    anti_edges: list = []

    for r in rows:
        code = r["code"]
        if not code:
            continue
        nodes[code] = {
            "name": r["name"] or code,
            "faculty": r["faculty"] or "—",
            "cp": r["cp"] or "—",
        }
        for pre in r["prereq_codes"] or []:
            if pre:
                prereq_edges.append((pre, code))
        for anti in r["anti_codes"] or []:
            if anti:
                anti_edges.append((code, anti))

    # Admission and other requisite nodes exist as separate labelled nodes
    # connected via HAS_ADMISSION_REQUISITE / HAS_OTHER_REQUISITE relationships.
    admission_reqs: dict = {}
    other_reqs: dict = {}
    if nodes:
        codes_list = list(nodes.keys())
        req_rows = run_query(
            """
            UNWIND $codes AS code
            MATCH (s:Subject {code: code})-[:HAS_VERSION]->(sv:SubjectVersion {year: $year})
            OPTIONAL MATCH (sv)-[:HAS_ADMISSION_REQUISITE]->(ar:AdmissionRequisite)
            OPTIONAL MATCH (sv)-[:HAS_OTHER_REQUISITE]->(or:OtherRequisite)
            RETURN code,
                   collect(DISTINCT ar.detail) AS admissions,
                   collect(DISTINCT or.detail) AS others
            """,
            {"codes": codes_list, "year": year},
        )
        for r in req_rows:
            code = r["code"]
            adms = [a for a in (r.get("admissions") or []) if a]
            othrs = [o for o in (r.get("others") or []) if o]
            if adms:
                admission_reqs[code] = adms
            if othrs:
                other_reqs[code] = othrs

    return {
        "nodes": nodes,
        "prereq_edges": prereq_edges,
        "anti_edges": anti_edges,
        "admission_reqs": admission_reqs,
        "other_reqs": other_reqs,
    }


def build_prereq_tree_dict(
    subject_code: str, year: int, max_depth: int = 4
) -> Optional[dict]:
    """
    Return a nested tree dict suitable for the D3 prereq-tree visualization.
    Root = subject_code, children = its prerequisites (recursively).
    Depth is controlled here in Python (not in Cypher).
    """
    data = get_prereq_subgraph(subject_code, year, max_depth)
    if subject_code not in data["nodes"]:
        return None

    prereqs_of: dict = defaultdict(list)
    for pre, tgt in data["prereq_edges"]:
        prereqs_of[tgt].append(pre)

    anti_of: dict = defaultdict(list)
    for src, anti in data["anti_edges"]:
        anti_of[src].append(anti)

    def build_node(code: str, depth: int, visited: frozenset) -> Optional[dict]:
        if code in visited:
            return None
        nd = data["nodes"].get(code)
        if not nd:
            return None
        children = []
        if depth < max_depth:
            vis2 = visited | {code}
            for pre in prereqs_of.get(code, []):
                child = build_node(pre, depth + 1, vis2)
                if child:
                    children.append(child)
        return {
            "name": f"{code}  {nd['name']}",
            "code": code,
            "subject_name": nd["name"],
            "faculty": nd["faculty"],
            "cp": nd["cp"],
            "antis": anti_of.get(code, []),
            "children": children,
        }

    return build_node(subject_code, 0, frozenset())


# ============================================================================
# Shared subjects data
# ============================================================================


@lru_cache(maxsize=8)
def get_shared_subjects_data(year: int) -> dict:
    """
    Return all courses for a year with the subjects they contain:
        {course_code: {name: str, subjects: {subj_code: subj_name}}}
    """
    rows = run_query(
        """
        MATCH (c:Course)-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        MATCH (cv)-[:HAS_STRUCTURE]->(root:Structure)
        OPTIONAL MATCH (root)-[:HAS_CHILD*0..10]->(s:Structure)-[:CONTAINS]->(subj:Subject)
        WHERE subj IS NOT NULL
        RETURN c.code AS course_code, cv.course_name AS course_name,
               subj.code AS subj_code, subj.name AS subj_name
        """,
        {"year": year},
    )

    courses: dict = {}
    for r in rows:
        ccode = r["course_code"]
        if not ccode:
            continue
        if ccode not in courses:
            courses[ccode] = {"name": r["course_name"] or ccode, "subjects": {}}
        if r["subj_code"]:
            courses[ccode]["subjects"][r["subj_code"]] = (
                r["subj_name"] or r["subj_code"]
            )

    return courses


# ============================================================================
# Subject metadata bulk (for similarity network node labels)
# ============================================================================


@lru_cache(maxsize=8)
def get_subjects_metadata(year: int) -> dict:
    """
    Return lightweight metadata for all subjects in a year:
        {code: {name, faculty, credit_points, study_level}}
    """
    rows = run_query(
        """
        MATCH (s:Subject)-[:HAS_VERSION]->(sv:SubjectVersion {year: $year})
        RETURN s.code AS code, sv.name AS name, sv.faculty AS faculty,
               sv.credit_points AS credit_points, sv.study_level AS study_level
        """,
        {"year": year},
    )
    return {
        r["code"]: {
            "name": r["name"] or r["code"],
            "faculty": r["faculty"] or "Unknown",
            "credit_points": r["credit_points"] or "—",
            "study_level": r["study_level"] or "—",
        }
        for r in rows
        if r["code"]
    }
