# All Neo4j queries that feed the visualization layer.
# Every function returns plain Python dicts/lists so the visualization
# modules need no knowledge of Neo4j or Cypher.

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Optional

from database.neo4j import run_query


# Course data  (fully from Neo4j, traversing AoS sub-structures)
@lru_cache(maxsize=16)
def get_course_data(course_code: str, year: int) -> Optional[dict]:
    """
    Return course data from Neo4j, mirroring the JSON structure expected by
    the visualization walk functions.

    Traverses:
      CourseVersion
        -[:HAS_STRUCTURE]-> Structure
        -[:HAS_CHILD*]-> Structure
        -[:CONTAINS]-> Subject                   (direct subjects)
        -[:CONTAINS_AOS]-> AreaOfStudy
          -[:HAS_VERSION]-> AreaOfStudyVersion
          -[:HAS_STRUCTURE]-> Structure           (AoS inner blocks)
          -[:HAS_CHILD*]-> Structure
          -[:CONTAINS]-> Subject                  (subjects within AoS)
    """

    # Course metadata
    meta = run_query(
        """
        MATCH (c:Course {code: $code})-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        RETURN c.code AS course_code, cv.course_name AS course_name, cv.year AS year
        LIMIT 1
        """,
        {"code": course_code, "year": year},
    )
    if not meta:
        return None
    course_meta = meta[0]

    # Top-level structure IDs (direct children of CourseVersion)
    top_rows = run_query(
        """
        MATCH (c:Course {code: $code})-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        -[:HAS_STRUCTURE]->(st:Structure)
        RETURN st.id AS id, st.structure_name AS name, st.structure_cp AS cp
        """,
        {"code": course_code, "year": year},
    )
    top_ids = [r["id"] for r in top_rows]
    all_structs: dict = {r["id"]: {"name": r["name"], "cp": r["cp"]} for r in top_rows}

    # All HAS_CHILD edges within course structures
    child_rows = run_query(
        """
        MATCH (c:Course {code: $code})-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        -[:HAS_STRUCTURE]->(top:Structure)
        OPTIONAL MATCH (top)-[:HAS_CHILD*0..9]->(p:Structure)-[:HAS_CHILD]->(ch:Structure)
        WHERE p IS NOT NULL AND ch IS NOT NULL
        RETURN DISTINCT p.id AS parent_id,
               ch.id AS child_id, ch.structure_name AS child_name, ch.structure_cp AS child_cp
        """,
        {"code": course_code, "year": year},
    )
    struct_children: dict = defaultdict(list)  # parent_id -> [child_id, ...]
    for r in child_rows:
        pid, cid = r["parent_id"], r["child_id"]
        if pid and cid:
            struct_children[pid].append(cid)
            all_structs[cid] = {"name": r["child_name"], "cp": r["child_cp"]}

    # Subjects directly in course structures
    direct_subj_rows = run_query(
        """
        MATCH (c:Course {code: $code})-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        -[:HAS_STRUCTURE]->(top:Structure)
        OPTIONAL MATCH (top)-[:HAS_CHILD*0..10]->(st:Structure)-[:CONTAINS]->(s:Subject)
        OPTIONAL MATCH (s)-[:HAS_VERSION]->(sv:SubjectVersion {year: $year})
        WHERE s IS NOT NULL
        RETURN DISTINCT st.id AS struct_id, s.code AS code, s.name AS name,
               sv.credit_points AS cp, sv.faculty AS faculty,
               sv.study_level AS study_level, sv.type AS sub_type
        """,
        {"code": course_code, "year": year},
    )
    struct_subjects: dict = defaultdict(list)  # struct_id -> [subject_dict, ...]
    for r in direct_subj_rows:
        if r["struct_id"] and r["code"]:
            struct_subjects[r["struct_id"]].append(
                {
                    "code": r["code"],
                    "name": r["name"] or r["code"],
                    "credit_points": r["cp"] or "6",
                    "faculty": r["faculty"] or "",
                    "study_level": r["study_level"] or "",
                    "type": r["sub_type"] or "Subject",
                }
            )

    # AoS nodes in course structures
    aos_rows = run_query(
        """
        MATCH (c:Course {code: $code})-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        -[:HAS_STRUCTURE]->(top:Structure)
        OPTIONAL MATCH (top)-[:HAS_CHILD*0..10]->(st:Structure)
        -[:CONTAINS_AOS]->(aos:AreaOfStudy)
        -[:HAS_VERSION]->(aosv:AreaOfStudyVersion {year: $year})
        WHERE aos IS NOT NULL
        RETURN DISTINCT st.id AS struct_id, aos.code AS code, aosv.name AS name,
               aosv.credit_points AS cp, aosv.type AS type, aosv.id AS version_id
        """,
        {"code": course_code, "year": year},
    )
    struct_aos: dict = defaultdict(list)  # struct_id -> [aos_dict, ...]
    all_aosv_ids: list = []
    for r in aos_rows:
        if r["struct_id"] and r["code"]:
            struct_aos[r["struct_id"]].append(
                {
                    "code": r["code"],
                    "name": r["name"] or r["code"],
                    "credit_points": r["cp"] or "",
                    "type": r["type"] or "Sub-Major",
                    "version_id": r["version_id"],
                    "have_structure": [],  # filled below
                }
            )
            if r["version_id"]:
                all_aosv_ids.append(r["version_id"])

    # AoS inner top-level structures (AreaOfStudyVersion -[:HAS_STRUCTURE]->)
    if all_aosv_ids:
        aos_top_rows = run_query(
            """
            UNWIND $ids AS av_id
            MATCH (aosv:AreaOfStudyVersion {id: av_id})-[:HAS_STRUCTURE]->(ist:Structure)
            RETURN av_id, ist.id AS id, ist.structure_name AS name, ist.structure_cp AS cp
            """,
            {"ids": all_aosv_ids},
        )
        aosv_top_structs: dict = defaultdict(list)  # aosv_id -> [struct_id, ...]
        for r in aos_top_rows:
            aosv_top_structs[r["av_id"]].append(r["id"])
            all_structs[r["id"]] = {"name": r["name"], "cp": r["cp"]}

        # HAS_CHILD edges within AoS inner structures
        if aosv_top_structs:
            inner_ids = [sid for sids in aosv_top_structs.values() for sid in sids]
            inner_child_rows = run_query(
                """
                UNWIND $ids AS root_id
                MATCH (root:Structure {id: root_id})
                OPTIONAL MATCH (root)-[:HAS_CHILD*0..5]->(p:Structure)-[:HAS_CHILD]->(ch:Structure)
                WHERE p IS NOT NULL AND ch IS NOT NULL
                RETURN DISTINCT p.id AS parent_id,
                       ch.id AS child_id, ch.structure_name AS child_name, ch.structure_cp AS cp
                """,
                {"ids": inner_ids},
            )
            for r in inner_child_rows:
                if r["parent_id"] and r["child_id"]:
                    struct_children[r["parent_id"]].append(r["child_id"])
                    all_structs[r["child_id"]] = {
                        "name": r["child_name"],
                        "cp": r["cp"],
                    }

            # Subjects within AoS inner structure
            inner_subj_rows = run_query(
                """
                UNWIND $ids AS root_id
                MATCH (root:Structure {id: root_id})
                OPTIONAL MATCH (root)-[:HAS_CHILD*0..5]->(st:Structure)-[:CONTAINS]->(s:Subject)
                OPTIONAL MATCH (s)-[:HAS_VERSION]->(sv:SubjectVersion {year: $year})
                WHERE s IS NOT NULL
                RETURN DISTINCT st.id AS struct_id, s.code AS code, s.name AS name,
                       sv.credit_points AS cp, sv.faculty AS faculty,
                       sv.study_level AS study_level, sv.type AS sub_type

                UNION

                UNWIND $ids AS root_id
                MATCH (root:Structure {id: root_id})-[:CONTAINS]->(s:Subject)
                OPTIONAL MATCH (s)-[:HAS_VERSION]->(sv:SubjectVersion {year: $year})
                WHERE s IS NOT NULL
                RETURN DISTINCT root_id AS struct_id, s.code AS code, s.name AS name,
                       sv.credit_points AS cp, sv.faculty AS faculty,
                       sv.study_level AS study_level, sv.type AS sub_type
                """,
                {"ids": inner_ids, "year": year},
            )
            for r in inner_subj_rows:
                if r["struct_id"] and r["code"]:
                    struct_subjects[r["struct_id"]].append(
                        {
                            "code": r["code"],
                            "name": r["name"] or r["code"],
                            "credit_points": r["cp"] or "6",
                            "faculty": r["faculty"] or "",
                            "study_level": r["study_level"] or "",
                            "type": r["sub_type"] or "Subject",
                        }
                    )
    else:
        aosv_top_structs = {}

    # Reconstruct hierarchy in Python

    # Build aosv_id to AoS entry map so we can attach inner structures
    aosv_to_aos: dict = {}
    for sid, aos_list in struct_aos.items():
        for aos in aos_list:
            aosv_to_aos[aos["version_id"]] = aos

    # Attach inner structure trees to each AoS
    def build_inner_struct(struct_id: str, visited: frozenset = frozenset()) -> dict:
        if struct_id in visited:
            return {}  # break cycle
        visited = visited | {struct_id}
        s = all_structs.get(struct_id, {})
        return {
            "structure_name": s.get("name", ""),
            "structure_cp": s.get("cp", ""),
            "has_subject": struct_subjects.get(struct_id, []),
            "have_sub_structures": [
                build_inner_struct(cid, visited)
                for cid in struct_children.get(struct_id, [])
                if cid != struct_id  # skip self-loops
            ],
            "has_area_of_study": [],
        }

    for aosv_id, inner_top_ids in aosv_top_structs.items():
        aos_entry = aosv_to_aos.get(aosv_id)
        if aos_entry:
            aos_entry["have_structure"] = [
                build_inner_struct(sid) for sid in inner_top_ids
            ]

    # Build top-level structure tree
    def build_struct(struct_id: str, visited: frozenset = frozenset()) -> dict:
        if struct_id in visited:
            return {}  # break cycle
        visited = visited | {struct_id}
        s = all_structs.get(struct_id, {})
        return {
            "structure_name": s.get("name", ""),
            "structure_cp": s.get("cp", ""),
            "has_subject": struct_subjects.get(struct_id, []),
            "have_sub_structures": [
                build_struct(cid, visited)
                for cid in struct_children.get(struct_id, [])
                if cid != struct_id  # skip self-loops
            ],
            "has_area_of_study": struct_aos.get(struct_id, []),
        }

    return {
        "course_code": course_meta["course_code"],
        "course_name": course_meta["course_name"],
        "year": course_meta["year"],
        "structure": [build_struct(tid) for tid in top_ids],
    }


# Shared subjects data  (fully from Neo4j via IN_COURSE_VERSION)


@lru_cache(maxsize=8)
def get_shared_subjects_data(year: int) -> dict:
    """
    Return all courses for a year with the subjects they contain:
        {course_code: {name: str, subjects: {subj_code: subj_name}}}

    Uses IN_COURSE_VERSION which is explicitly set for every Subject that
    appears anywhere in a course version — including subjects nested inside
    AreaOfStudy inner structures — so this gives the complete subject list.
    """
    rows = run_query(
        """
        MATCH (c:Course)-[:HAS_VERSION]->(cv:CourseVersion {year: $year})
        MATCH (s:Subject)-[:IN_COURSE_VERSION]->(cv)
        RETURN c.code AS course_code, cv.course_name AS course_name,
               s.code AS subj_code, s.name AS subj_name
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


# Subject evolution data
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


# Prerequisite tree and graph data
@lru_cache(maxsize=64)
def get_prereq_subgraph(subject_code: str, year: int) -> dict:
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


# Subject metadata bulk (for similarity network node labels)
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
