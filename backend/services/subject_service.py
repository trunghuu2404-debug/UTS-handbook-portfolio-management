"""
services/subject_service.py
---------------------------
All Cypher queries and data transformation for Subject endpoints.
"""

from database.neo4j import run_query
from models.schemas import (
    SubjectDetailOut,
    SubjectVersionOut,
    SubjectRequisitesOut,
    RequisiteRelOut,
    AdmissionReqOut,
    OtherReqOut,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_list(val) -> list:
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def _sv_row_to_model(r: dict) -> SubjectVersionOut:
    """Convert a raw Neo4j row into a SubjectVersionOut model."""
    return SubjectVersionOut(
        id=r["id"],
        code=r["code"],
        name=r.get("name") or "",
        year=r["year"],
        url=r.get("url"),
        credit_points=r.get("credit_points"),
        type=r.get("type"),
        faculty=r.get("faculty"),
        study_level=r.get("study_level"),
        result_type=r.get("result_type"),
        total_workload_hours=r.get("total_workload_hours"),
        description=r.get("description"),
        learning_outcomes=_to_list(r.get("learning_outcomes")),
        teaching_and_learning_activities=r.get("teaching_and_learning_activities"),
        requisite_rule=r.get("requisite_rule"),
        anti_requisite_rule=r.get("anti_requisite_rule"),
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def get_subject_detail(subject_code: str):
    """
    Return the Subject identity node plus all of its SubjectVersion nodes,
    each carrying full metadata (description, learning outcomes, workload, etc.).
    """
    cypher = """
    MATCH (s:Subject {code: $code})-[:HAS_VERSION]->(sv:SubjectVersion)
    RETURN
        s.code                                  AS subject_code,
        s.name                                  AS subject_name,
        sv.id                                   AS id,
        sv.code                                 AS code,
        sv.name                                 AS name,
        sv.year                                 AS year,
        sv.url                                  AS url,
        sv.credit_points                        AS credit_points,
        sv.type                                 AS type,
        sv.faculty                              AS faculty,
        sv.study_level                          AS study_level,
        sv.result_type                          AS result_type,
        sv.total_workload_hours                 AS total_workload_hours,
        sv.description                          AS description,
        sv.learning_outcomes                    AS learning_outcomes,
        sv.teaching_and_learning_activities     AS teaching_and_learning_activities,
        sv.requisite_rule                       AS requisite_rule,
        sv.anti_requisite_rule                  AS anti_requisite_rule
    ORDER BY sv.year DESC
    """
    rows = run_query(cypher, {"code": subject_code})

    if not rows:
        return None

    versions = [_sv_row_to_model(r) for r in rows]
    return SubjectDetailOut(
        code=rows[0]["subject_code"],
        name=rows[0]["subject_name"],
        versions=versions,
    )


def get_subject_version(subject_code: str, year: int):
    """Return one specific SubjectVersion by code + year."""
    cypher = """
    MATCH (sv:SubjectVersion {id: $vid})
    RETURN
        sv.id                                   AS id,
        sv.code                                 AS code,
        sv.name                                 AS name,
        sv.year                                 AS year,
        sv.url                                  AS url,
        sv.credit_points                        AS credit_points,
        sv.type                                 AS type,
        sv.faculty                              AS faculty,
        sv.study_level                          AS study_level,
        sv.result_type                          AS result_type,
        sv.total_workload_hours                 AS total_workload_hours,
        sv.description                          AS description,
        sv.learning_outcomes                    AS learning_outcomes,
        sv.teaching_and_learning_activities     AS teaching_and_learning_activities,
        sv.requisite_rule                       AS requisite_rule,
        sv.anti_requisite_rule                  AS anti_requisite_rule
    """
    rows = run_query(cypher, {"vid": f"{subject_code}_{year}"})
    return _sv_row_to_model(rows[0]) if rows else None


def get_subject_requisites(subject_code: str, year: int):
    """
    Return the full requisite picture for one SubjectVersion:
      - PREREQUISITE edges   (carry item_id, rule, item_type)
      - ANTI_REQUISITE edges (carry item_id, rule)
      - AdmissionRequisite nodes
      - OtherRequisite nodes
    """
    vid = f"{subject_code}_{year}"

    # ── Header row (the subject version itself) ──────────────────────────────
    header_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})
    RETURN sv.id                    AS id,
           sv.code                  AS code,
           sv.name                  AS name,
           sv.year                  AS year,
           sv.requisite_rule        AS requisite_rule,
           sv.anti_requisite_rule   AS anti_requisite_rule
    """
    header_rows = run_query(header_cypher, {"vid": vid})
    if not header_rows:
        return None
    h = header_rows[0]

    # ── Prerequisites ────────────────────────────────────────────────────────
    prereq_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[r:PREREQUISITE]->(pre:SubjectVersion)
    OPTIONAL MATCH (pre)-[:OF_SUBJECT]->(s:Subject)
    RETURN pre.id       AS subject_version_id,
           pre.code     AS code,
           coalesce(s.name, pre.name)  AS name,
           pre.year     AS year,
           r.item_id    AS item_id,
           r.item_type  AS item_type,
           r.rule       AS rule
    ORDER BY r.item_id
    """
    prereq_rows = run_query(prereq_cypher, {"vid": vid})
    prerequisites = [
        RequisiteRelOut(
            subject_version_id=r["subject_version_id"],
            code=r["code"],
            name=r.get("name") or r["code"],
            year=r["year"],
            item_id=r.get("item_id") or "",
            item_type=r.get("item_type"),
            rule=r.get("rule") or "",
        )
        for r in prereq_rows
    ]

    # ── Anti-requisites ──────────────────────────────────────────────────────
    anti_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[r:ANTI_REQUISITE]->(anti:SubjectVersion)
    OPTIONAL MATCH (anti)-[:OF_SUBJECT]->(s:Subject)
    RETURN anti.id      AS subject_version_id,
           anti.code    AS code,
           coalesce(s.name, anti.name) AS name,
           anti.year    AS year,
           r.item_id    AS item_id,
           r.rule       AS rule
    ORDER BY r.item_id
    """
    anti_rows = run_query(anti_cypher, {"vid": vid})
    anti_requisites = [
        RequisiteRelOut(
            subject_version_id=r["subject_version_id"],
            code=r["code"],
            name=r.get("name") or r["code"],
            year=r["year"],
            item_id=r.get("item_id") or "",
            item_type=None,
            rule=r.get("rule") or "",
        )
        for r in anti_rows
    ]

    # ── Admission requisites ─────────────────────────────────────────────────
    adm_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[:HAS_ADMISSION_REQUISITE]->(ar:AdmissionRequisite)
    RETURN ar.detail    AS detail,
           ar.item_id   AS item_id,
           ar.item_type AS item_type,
           ar.rule      AS rule
    ORDER BY ar.item_id
    """
    adm_rows = run_query(adm_cypher, {"vid": vid})
    admission_requisites = [
        AdmissionReqOut(
            detail=r.get("detail") or "",
            item_id=r.get("item_id") or "",
            item_type=r.get("item_type") or "",
            rule=r.get("rule") or "",
        )
        for r in adm_rows
    ]

    # ── Other requisites ─────────────────────────────────────────────────────
    other_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[:HAS_OTHER_REQUISITE]->(or:OtherRequisite)
    RETURN or.note AS note,
           or.rule AS rule
    """
    other_rows = run_query(other_cypher, {"vid": vid})
    other_requisites = [
        OtherReqOut(note=r.get("note") or "", rule=r.get("rule") or "")
        for r in other_rows
    ]

    return SubjectRequisitesOut(
        subject_version_id=h["id"],
        code=h["code"],
        name=h.get("name") or "",
        year=h["year"],
        requisite_rule=h.get("requisite_rule"),
        anti_requisite_rule=h.get("anti_requisite_rule"),
        prerequisites=prerequisites,
        anti_requisites=anti_requisites,
        admission_requisites=admission_requisites,
        other_requisites=other_requisites,
    )


def search_subjects(query: str, limit: int = 20) -> list[dict]:
    """
    Full-text search on Subject name and code.
    Used to power the Streamlit subject selector.
    """
    cypher = """
    MATCH (s:Subject)
    WHERE toLower(s.name) CONTAINS toLower($q)
       OR s.code CONTAINS $q
    RETURN s.code AS code,
           s.name AS name
    ORDER BY s.name
    LIMIT $limit
    """
    return run_query(cypher, {"q": query, "limit": limit})
