"""
neo4j_importer.py
=================
Imports the UTS Curriculum Digital Twin dataset into Neo4j.

Dataset layout (all under DATASET_PATH):
    dataset/
        C10474_Bachelor of Artificial Intelligent/
            2023.json  2024.json  2025.json  2026.json
        C10443_Master of Artificial Intelligent/
            2023.json  2024.json  2025.json  2026.json
        subject_archives/
            2023_subjects.json  ...

Key design decisions
--------------------
* SubjectVersion display name  : "{code}_{year}" stored as .id, plus .name for clarity
* Requisite relationships carry item_id and rule metadata as relationship properties
* Admission requisites stored as AdmissionRequisite nodes (not SubjectVersion links)
* Other requisites stored as OtherRequisite nodes
* Course learning outcomes stored on CourseVersion
* AreaOfStudy follows same versioning pattern as Subject

Graph schema
------------
Nodes:
    (:Course)              {code, name}
    (:CourseVersion)       {id="{code}_{year}", course_code, course_name, year,
                            course_details, course_learning_outcomes, course_url}
    (:Structure)           {id, structure_name, structure_cp}
    (:Subject)             {code, name}
    (:SubjectVersion)      {id="{code}_{year}", code, name, year, url,
                            credit_points, type, faculty, study_level,
                            result_type, total_workload_hours, description,
                            learning_outcomes, teaching_and_learning_activities,
                            requisite_rule, anti_requisite_rule}
    (:AdmissionRequisite)  {id, detail, item_id, item_type, rule}
    (:OtherRequisite)      {id, note, rule}
    (:AreaOfStudy)         {code, name}
    (:AreaOfStudyVersion)  {id="{code}_{year}", code, name, year, url,
                            credit_points, type, description}

Relationships:
    (Course)-[:HAS_VERSION]->(CourseVersion)
    (CourseVersion)-[:HAS_STRUCTURE]->(Structure)
    (Structure)-[:HAS_CHILD]->(Structure)
    (Structure)-[:CONTAINS]->(Subject)
    (Structure)-[:CONTAINS_AOS]->(AreaOfStudy)
    (Subject)-[:IN_COURSE_VERSION]->(CourseVersion)
    (AreaOfStudy)-[:IN_COURSE_VERSION]->(CourseVersion)
    (Subject)-[:HAS_VERSION]->(SubjectVersion)
    (SubjectVersion)-[:OF_SUBJECT]->(Subject)
    (SubjectVersion)-[:NEXT_VERSION]->(SubjectVersion)
    (AreaOfStudy)-[:HAS_VERSION]->(AreaOfStudyVersion)
    (AreaOfStudyVersion)-[:NEXT_VERSION]->(AreaOfStudyVersion)

    # Requisite relationships with item metadata
    (SubjectVersion)-[:PREREQUISITE    {item_id, rule, item_type}]->(SubjectVersion)
    (SubjectVersion)-[:ANTI_REQUISITE  {item_id, rule}]->(SubjectVersion)
    (SubjectVersion)-[:HAS_ADMISSION_REQUISITE]->(AdmissionRequisite)
    (SubjectVersion)-[:HAS_OTHER_REQUISITE    ]->(OtherRequisite)
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Driver

# Configuration

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Trungvip2404@")
DATASET_PATH = os.getenv("DATASET_PATH", "dataset")

BATCH_SIZE = 500

COURSE_DIR_RE = re.compile(r"^C\d+_", re.IGNORECASE)
SUBJECT_DIR_NAME = "subjects_archive"

# Matches a 5-digit UTS subject code: "31265 Subject Name" -> "31265", some subject code has more than 5
SUBJECT_CODE_RE = re.compile(r"\b(\d{5,})\b")


# Logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# SCHEMA
CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Course)             REQUIRE n.code IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:CourseVersion)      REQUIRE n.id   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Structure)          REQUIRE n.id   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Subject)            REQUIRE n.code IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:SubjectVersion)     REQUIRE n.id   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AreaOfStudy)        REQUIRE n.code IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AreaOfStudyVersion) REQUIRE n.id   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AdmissionRequisite) REQUIRE n.id   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:OtherRequisite)     REQUIRE n.id   IS UNIQUE",
]


def create_constraints(driver: Driver) -> None:
    with driver.session() as session:
        for cypher in CONSTRAINTS:
            session.run(cypher)
    log.info("Constraints ensured.")


# FOLDER DISCOVERY
def discover_folders(dataset_path: str) -> tuple:
    root = Path(dataset_path)
    if not root.exists():
        log.error("DATASET_PATH does not exist: %s", root)
        raise SystemExit(1)

    course_dirs = []
    subject_dir = None

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if COURSE_DIR_RE.match(entry.name):
            course_dirs.append(entry)
            log.info("  Found course dir : %s", entry.name)
        elif entry.name.lower() == SUBJECT_DIR_NAME:
            subject_dir = entry
            log.info("  Found subject dir: %s", entry.name)

    return course_dirs, subject_dir


# HELPERS
def _run_batches(driver: Driver, cypher: str, rows: list) -> None:
    """Execute cypher (UNWIND $rows) in chunks of BATCH_SIZE."""
    for start in range(0, len(rows), BATCH_SIZE):
        chunk = rows[start : start + BATCH_SIZE]
        with driver.session() as session:
            session.run(cypher, rows=chunk)


def _safe_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _normalise_lo(raw: Any) -> list:
    """Normalise learning outcomes field to a clean list of strings."""
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, str) and raw.strip().lower() != "no learning outcomes available":
        return [raw.strip()]
    return []


def _normalise_cp(raw: Any) -> str:
    return str(raw or "").replace("CPs", "").replace("CP", "").strip()


def _parse_requisites(requisite_list: Any) -> dict:
    """
    Parse a subject's full requisite_list into categorised buckets.

    Returns:
    {
      "prerequisite":  [{"code","item_id","item_type","rule","detail"}, ...],
      "anti_requisite":[{"code","item_id","rule","detail"}, ...],
      "admission":     [{"detail","item_id","item_type","rule"}, ...],
      "other":         [{"note","rule"}, ...],
      "requisite_rule":      str,   # raw rule string for prerequisite block
      "anti_requisite_rule": str,   # raw rule string for anti_requisite block
    }
    """
    out = {
        "prerequisite": [],
        "anti_requisite": [],
        "admission": [],
        "other": [],
        "requisite_rule": "",
        "anti_requisite_rule": "",
    }

    if not isinstance(requisite_list, dict):
        return out

    for block_key, block in requisite_list.items():
        if not isinstance(block, dict):
            continue

        rule_str = block.get("rule", "")
        items = _safe_list(block.get("items"))

        if block_key == "requisite":
            out["requisite_rule"] = rule_str
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id", "")
                item_type = item.get("type", "")
                detail = item.get("details", "")

                if "admission" in item_type.lower():
                    # Store as AdmissionRequisite node
                    out["admission"].append(
                        {
                            "detail": detail,
                            "item_id": item_id,
                            "item_type": item_type,
                            "rule": rule_str,
                        }
                    )
                else:
                    # Extract 5-digit subject code if present
                    codes = SUBJECT_CODE_RE.findall(detail)
                    if codes:
                        out["prerequisite"].append(
                            {
                                "code": codes[0],
                                "item_id": item_id,
                                "item_type": item_type,
                                "rule": rule_str,
                                "detail": detail,
                            }
                        )
                    else:
                        # No subject code but still a requisite detail — store as admission
                        out["admission"].append(
                            {
                                "detail": detail,
                                "item_id": item_id,
                                "item_type": item_type,
                                "rule": rule_str,
                            }
                        )

        elif block_key == "anti_requisite":
            out["anti_requisite_rule"] = rule_str
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id", "")
                detail = item.get("details", "")
                codes = SUBJECT_CODE_RE.findall(detail)
                if codes:
                    out["anti_requisite"].append(
                        {
                            "code": codes[0],
                            "item_id": item_id,
                            "rule": rule_str,
                            "detail": detail,
                        }
                    )

        elif block_key == "other_requisite":
            # Items have a "note" field instead of "details"
            for item in items:
                if not isinstance(item, dict):
                    continue
                out["other"].append(
                    {
                        "note": item.get("note", ""),
                        "rule": rule_str,
                    }
                )

    return out


# STEP 1 — COURSE FILES
def import_courses(driver: Driver, course_dirs: list) -> None:
    if not course_dirs:
        log.warning("No course directories found.")
        return

    for course_dir in course_dirs:
        dir_match = re.match(r"(C\d+)_", course_dir.name)
        dir_code = dir_match.group(1) if dir_match else None

        year_files = sorted(course_dir.glob("*.json"))
        if not year_files:
            log.warning("No JSON files in %s – skipping.", course_dir.name)
            continue

        log.info(
            "Processing course dir: %s  (%d version(s))",
            course_dir.name,
            len(year_files),
        )

        for filepath in year_files:
            year_match = re.fullmatch(r"(\d{4})", filepath.stem)
            if not year_match:
                log.warning("  Skipping non-year file: %s", filepath.name)
                continue
            year = int(year_match.group(1))

            try:
                with open(filepath, encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception as exc:
                log.error("  Failed to read %s: %s", filepath, exc)
                continue

            course_code = (data.get("course_code") or dir_code or "").strip()
            course_name = (data.get("course_name") or "").strip()
            course_url = (data.get("course_url") or "").strip()
            course_details = data.get("course_details") or ""

            raw_clo = data.get("course_learning_outcomes") or []
            course_lo = _normalise_lo(raw_clo)

            if not course_code:
                log.warning(
                    "  Cannot determine course_code for %s – skipping.", filepath
                )
                continue

            version_id = f"{course_code}_{year}"
            log.info("  Loading %s version %d …", course_code, year)

            with driver.session() as session:
                session.run(
                    """
                    MERGE (c:Course {code: $code})
                    SET   c.name = $name

                    MERGE (cv:CourseVersion {id: $vid})
                    SET   cv.course_code              = $code,
                          cv.course_name              = $name,
                          cv.year                     = $year,
                          cv.course_url               = $url,
                          cv.course_details           = $details,
                          cv.course_learning_outcomes = $clo

                    MERGE (c)-[:HAS_VERSION]->(cv)
                    """,
                    code=course_code,
                    name=course_name,
                    vid=version_id,
                    year=year,
                    url=course_url,
                    details=course_details,
                    clo=course_lo,
                )

                structure_items = _safe_list(data.get("structure"))
                for idx, struct_item in enumerate(structure_items):
                    if isinstance(struct_item, dict):
                        _import_structure(
                            session=session,
                            struct_data=struct_item,
                            parent_id=version_id,
                            parent_label="CourseVersion",
                            course_version_id=version_id,
                            year=year,
                            path=f"{version_id}_s{idx}",
                        )

            log.info("  -> CourseVersion %s imported.", version_id)

        log.info("Finished course dir: %s", course_dir.name)


def _import_structure(
    session,
    struct_data: dict,
    parent_id: str,
    parent_label: str,
    course_version_id: str,
    year: int,
    path: str,
) -> None:
    """Recursively create Structure nodes and their children."""
    struct_name = struct_data.get("structure_name") or "Unnamed"
    struct_cp = struct_data.get("structure_cp") or ""
    struct_id = path

    session.run(
        """
        MERGE (st:Structure {id: $id})
        SET   st.structure_name = $name,
              st.structure_cp   = $cp
        """,
        id=struct_id,
        name=struct_name,
        cp=struct_cp,
    )

    if parent_label == "CourseVersion":
        session.run(
            """
            MATCH (cv:CourseVersion {id: $pid})
            MATCH (st:Structure     {id: $cid})
            MERGE (cv)-[:HAS_STRUCTURE]->(st)
            """,
            pid=parent_id,
            cid=struct_id,
        )
    else:
        session.run(
            """
            MATCH (p:Structure {id: $pid})
            MATCH (c:Structure {id: $cid})
            MERGE (p)-[:HAS_CHILD]->(c)
            """,
            pid=parent_id,
            cid=struct_id,
        )

    # Leaf subjects
    for subj_data in _safe_list(struct_data.get("has_subject")):
        if isinstance(subj_data, dict):
            _import_inline_subject(
                session, subj_data, struct_id, course_version_id, year
            )

    # Areas of study
    for aos_idx, aos_data in enumerate(
        _safe_list(struct_data.get("has_area_of_study"))
    ):
        if isinstance(aos_data, dict):
            _import_area_of_study(
                session,
                aos_data,
                struct_id,
                course_version_id,
                year,
                path=f"{path}_aos{aos_idx}",
            )

    # Nested structure groups
    for sub_idx, sub_struct in enumerate(
        _safe_list(struct_data.get("have_sub_structures"))
    ):
        if isinstance(sub_struct, dict):
            _import_structure(
                session=session,
                struct_data=sub_struct,
                parent_id=struct_id,
                parent_label="Structure",
                course_version_id=course_version_id,
                year=year,
                path=f"{path}_sub{sub_idx}",
            )


def _import_inline_subject(
    session,
    subj_data: dict,
    struct_id: str,
    course_version_id: str,
    year: int,
) -> None:
    """
    Upsert Subject + SubjectVersion from inline course-file data.
    Subject archive (Step 2) will later overwrite/enrich SubjectVersion props.
    """
    code = str(subj_data.get("code") or "").strip()
    name = (subj_data.get("name") or "").strip()
    if not code:
        return

    raw_lo = subj_data.get("learning_outcomes")
    lo = _normalise_lo(raw_lo)
    cp = _normalise_cp(subj_data.get("credit_points"))

    req = _parse_requisites(subj_data.get("requisite_list"))

    version_id = f"{code}_{year}"

    session.run(
        """
        MERGE (s:Subject {code: $code})
        SET   s.name = $name
        """,
        code=code,
        name=name,
    )

    session.run(
        """
        MERGE (sv:SubjectVersion {id: $id})
        SET   sv.code                           = $code,
              sv.name                           = $name,
              sv.year                           = $year,
              sv.url                            = $url,
              sv.credit_points                  = $cp,
              sv.type                           = $type,
              sv.faculty                        = $faculty,
              sv.study_level                    = $study_level,
              sv.result_type                    = $result_type,
              sv.total_workload_hours           = $workload,
              sv.description                    = $description,
              sv.learning_outcomes              = $lo,
              sv.teaching_and_learning_activities = $tla,
              sv.requisite_rule                 = $req_rule,
              sv.anti_requisite_rule            = $anti_rule

        WITH sv
        MATCH (s:Subject {code: $code})
        MERGE (s)-[:HAS_VERSION]->(sv)
        MERGE (sv)-[:OF_SUBJECT]->(s)
        """,
        id=version_id,
        code=code,
        name=name,
        year=year,
        url=subj_data.get("url") or "",
        cp=cp,
        type=subj_data.get("type") or "",
        faculty=subj_data.get("faculty") or "",
        study_level=subj_data.get("study_level") or "",
        result_type=subj_data.get("result_type") or "",
        workload=str(subj_data.get("total_workload_hours") or ""),
        description=subj_data.get("description") or "",
        lo=lo,
        tla=subj_data.get("learning_and_teaching_activities") or "",
        req_rule=req["requisite_rule"],
        anti_rule=req["anti_requisite_rule"],
    )

    session.run(
        """
        MATCH (st:Structure {id: $sid})
        MATCH (s:Subject    {code: $code})
        MERGE (st)-[:CONTAINS]->(s)
        """,
        sid=struct_id,
        code=code,
    )

    session.run(
        """
        MATCH (s:Subject        {code: $code})
        MATCH (cv:CourseVersion {id: $cv_id})
        MERGE (s)-[:IN_COURSE_VERSION]->(cv)
        """,
        code=code,
        cv_id=course_version_id,
    )

    # Store requisite relationships (deferred linking done in Step 2;
    # but inline data also triggers linking so we call it here too)
    _create_requisite_nodes(session, version_id, req, year)


def _create_requisite_nodes(session, sv_id: str, req: dict, year: int) -> None:
    """
    Create AdmissionRequisite / OtherRequisite nodes and link them.
    Subject-to-subject PREREQUISITE / ANTI_REQUISITE relationships are created
    separately after all SubjectVersions exist (to avoid missing targets).
    """
    # AdmissionRequisite nodes
    for adm in req["admission"]:
        adm_id = f"adm_{sv_id}_{adm['item_id']}"
        session.run(
            """
            MERGE (ar:AdmissionRequisite {id: $id})
            SET   ar.detail    = $detail,
                  ar.item_id   = $item_id,
                  ar.item_type = $item_type,
                  ar.rule      = $rule

            WITH ar
            MATCH (sv:SubjectVersion {id: $sv_id})
            MERGE (sv)-[:HAS_ADMISSION_REQUISITE]->(ar)
            """,
            id=adm_id,
            detail=adm["detail"],
            item_id=adm["item_id"],
            item_type=adm["item_type"],
            rule=adm["rule"],
            sv_id=sv_id,
        )

    # OtherRequisite nodes
    for idx, other in enumerate(req["other"]):
        other_id = f"other_{sv_id}_{idx}"
        note_label = other["note"] if other["note"] else "Other Requisite"
        session.run(
            """
            MERGE (or:OtherRequisite {id: $id})
            SET   or.note = $note,
                  or.rule = $rule

            WITH or
            MATCH (sv:SubjectVersion {id: $sv_id})
            MERGE (sv)-[:HAS_OTHER_REQUISITE]->(or)
            """,
            id=other_id,
            note=note_label,
            rule=other["rule"],
            sv_id=sv_id,
        )


def _import_area_of_study(
    session,
    aos_data: dict,
    struct_id: str,
    course_version_id: str,
    year: int,
    path: str,
) -> None:
    code = str(aos_data.get("code") or "").strip()
    name = (aos_data.get("name") or "").strip()
    if not code:
        return

    cp = _normalise_cp(aos_data.get("credit_points"))

    session.run(
        """
        MERGE (a:AreaOfStudy {code: $code})
        SET   a.name = $name
        """,
        code=code,
        name=name,
    )

    version_id = f"{code}_{year}"
    session.run(
        """
        MERGE (av:AreaOfStudyVersion {id: $id})
        SET   av.code          = $code,
              av.name          = $name,
              av.year          = $year,
              av.url           = $url,
              av.credit_points = $cp,
              av.type          = $type,
              av.description   = $description

        WITH av
        MATCH (a:AreaOfStudy {code: $code})
        MERGE (a)-[:HAS_VERSION]->(av)
        """,
        id=version_id,
        code=code,
        name=name,
        year=year,
        url=aos_data.get("url") or "",
        cp=cp,
        type=aos_data.get("type") or "",
        description=aos_data.get("description") or "",
    )

    session.run(
        """
        MATCH (st:Structure  {id: $sid})
        MATCH (a:AreaOfStudy {code: $code})
        MERGE (st)-[:CONTAINS_AOS]->(a)
        """,
        sid=struct_id,
        code=code,
    )

    session.run(
        """
        MATCH (a:AreaOfStudy    {code: $code})
        MATCH (cv:CourseVersion {id: $cv_id})
        MERGE (a)-[:IN_COURSE_VERSION]->(cv)
        """,
        code=code,
        cv_id=course_version_id,
    )

    # Recurse into AoS internal structure
    for sub_idx, sub_struct in enumerate(_safe_list(aos_data.get("have_structure"))):
        if not isinstance(sub_struct, dict):
            continue
        inner_path = f"{path}_inner{sub_idx}"
        _import_structure(
            session=session,
            struct_data=sub_struct,
            parent_id=inner_path,
            parent_label="Structure",
            course_version_id=course_version_id,
            year=year,
            path=inner_path,
        )
        session.run(
            """
            MATCH (av:AreaOfStudyVersion {id: $av_id})
            MATCH (st:Structure          {id: $st_id})
            MERGE (av)-[:HAS_STRUCTURE]->(st)
            """,
            av_id=version_id,
            st_id=inner_path,
        )


# STEP 2 — SUBJECT ARCHIVES
_SUBJECT_UPSERT_CYPHER = """
UNWIND $rows AS row
MERGE (s:Subject {code: row.code})
SET   s.name = row.name

MERGE (sv:SubjectVersion {id: row.vid})
SET   sv.code                           = row.code,
      sv.name                           = row.name,
      sv.year                           = row.year,
      sv.url                            = row.url,
      sv.credit_points                  = row.cp,
      sv.type                           = row.type,
      sv.faculty                        = row.faculty,
      sv.study_level                    = row.study_level,
      sv.result_type                    = row.result_type,
      sv.total_workload_hours           = row.workload,
      sv.description                    = row.description,
      sv.learning_outcomes              = row.lo,
      sv.teaching_and_learning_activities = row.tla,
      sv.requisite_rule                 = row.req_rule,
      sv.anti_requisite_rule            = row.anti_rule

MERGE (s)-[:HAS_VERSION]->(sv)
MERGE (sv)-[:OF_SUBJECT]->(s)
"""

# Subject-to-subject requisite link (carries item_id and rule as props)
_PREREQ_CYPHER = """
UNWIND $rows AS row
MATCH (from_sv:SubjectVersion {id: row.from_vid})
MATCH (to_sv:SubjectVersion   {id: row.to_vid})
MERGE (from_sv)-[r:PREREQUISITE {item_id: row.item_id}]->(to_sv)
SET   r.rule      = row.rule,
      r.item_type = row.item_type
"""

_ANTI_CYPHER = """
UNWIND $rows AS row
MATCH (from_sv:SubjectVersion {id: row.from_vid})
MATCH (to_sv:SubjectVersion   {id: row.to_vid})
MERGE (from_sv)-[r:ANTI_REQUISITE {item_id: row.item_id}]->(to_sv)
SET   r.rule = row.rule
"""


def import_subject_archives(driver: Driver, subject_dir: Path) -> None:
    """
    Load each YYYY_subjects.json and upsert Subject + SubjectVersion nodes,
    then wire all requisite relationships (with item metadata on the edges).
    """
    files = sorted(subject_dir.glob("*_subjects.json"))
    if not files:
        log.warning("No subject archive files found in %s", subject_dir)
        return

    for filepath in files:
        year_match = re.search(r"(\d{4})", filepath.stem)
        if not year_match:
            log.warning("Cannot extract year from %s – skipping.", filepath.name)
            continue
        year = int(year_match.group(1))

        log.info("Processing subject archive: %s  (year=%d)", filepath.name, year)

        try:
            with open(filepath, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            log.error("Failed to read %s: %s", filepath, exc)
            continue

        subj_rows = []
        prereq_rows = []
        anti_rows = []
        adm_rows = []  # (sv_id, AdmissionRequisite data)
        other_rows = []  # (sv_id, OtherRequisite data)

        for code, subj in data.items():
            if not isinstance(subj, dict):
                continue

            raw_lo = subj.get("learning_outcomes") or []
            lo = _normalise_lo(raw_lo)
            cp = _normalise_cp(subj.get("credit_points"))
            vid = f"{code}_{year}"
            name = subj.get("name") or ""

            req = _parse_requisites(subj.get("requisite_list"))

            subj_rows.append(
                {
                    "code": str(code),
                    "name": name,
                    "year": year,
                    "vid": vid,
                    "url": subj.get("url") or "",
                    "cp": cp,
                    "type": subj.get("type") or "",
                    "faculty": subj.get("faculty") or "",
                    "study_level": subj.get("study_level") or "",
                    "result_type": subj.get("result_type") or "",
                    "workload": str(
                        subj.get("total_workload_hours") or subj.get("workload") or ""
                    ),
                    "description": subj.get("description") or "",
                    "lo": lo,
                    "tla": (
                        subj.get("learning_and_teaching_activities")
                        or subj.get("teaching_and_learning_activities")
                        or ""
                    ),
                    "req_rule": req["requisite_rule"],
                    "anti_rule": req["anti_requisite_rule"],
                }
            )

            for pre in req["prerequisite"]:
                prereq_rows.append(
                    {
                        "from_vid": vid,
                        "to_vid": f"{pre['code']}_{year}",
                        "item_id": pre["item_id"],
                        "item_type": pre["item_type"],
                        "rule": pre["rule"],
                    }
                )

            for anti in req["anti_requisite"]:
                anti_rows.append(
                    {
                        "from_vid": vid,
                        "to_vid": f"{anti['code']}_{year}",
                        "item_id": anti["item_id"],
                        "rule": anti["rule"],
                    }
                )

            for adm in req["admission"]:
                adm_rows.append({"sv_id": vid, **adm})

            for idx, other in enumerate(req["other"]):
                other_rows.append({"sv_id": vid, "idx": idx, **other})

        # Batch upsert SubjectVersion nodes
        _run_batches(driver, _SUBJECT_UPSERT_CYPHER, subj_rows)

        # Subject-to-subject prerequisite / anti-requisite edges
        if prereq_rows:
            _run_batches(driver, _PREREQ_CYPHER, prereq_rows)
        if anti_rows:
            _run_batches(driver, _ANTI_CYPHER, anti_rows)

        # AdmissionRequisite nodes and edges (per-subject, can't UNWIND easily with MERGE edge)
        if adm_rows:
            _run_batches(driver, _ADM_UPSERT_CYPHER, adm_rows)

        if other_rows:
            _run_batches(driver, _OTHER_UPSERT_CYPHER, other_rows)

        log.info(
            "  -> %d subjects | %d prereqs | %d anti | %d admission | %d other",
            len(subj_rows),
            len(prereq_rows),
            len(anti_rows),
            len(adm_rows),
            len(other_rows),
        )


_ADM_UPSERT_CYPHER = """
UNWIND $rows AS row
MERGE (ar:AdmissionRequisite {id: 'adm_' + row.sv_id + '_' + row.item_id})
SET   ar.detail    = row.detail,
      ar.item_id   = row.item_id,
      ar.item_type = row.item_type,
      ar.rule      = row.rule

WITH ar, row
MATCH (sv:SubjectVersion {id: row.sv_id})
MERGE (sv)-[:HAS_ADMISSION_REQUISITE]->(ar)
"""

_OTHER_UPSERT_CYPHER = """
UNWIND $rows AS row
MERGE (or:OtherRequisite {id: 'other_' + row.sv_id + '_' + toString(row.idx)})
SET   or.note = row.note,
      or.rule = row.rule

WITH or, row
MATCH (sv:SubjectVersion {id: row.sv_id})
MERGE (sv)-[:HAS_OTHER_REQUISITE]->(or)
"""

# STEP 3 — NEXT_VERSION CHAINS


def link_next_versions(driver: Driver) -> None:
    log.info("Linking NEXT_VERSION chains for SubjectVersion ...")
    with driver.session() as session:
        session.run("""
            MATCH (s:Subject)-[:HAS_VERSION]->(sv:SubjectVersion)
            WITH  s, sv ORDER BY sv.year
            WITH  s, collect(sv) AS versions
            UNWIND range(0, size(versions)-2) AS i
            WITH  versions[i] AS curr, versions[i+1] AS nxt
            MERGE (curr)-[:NEXT_VERSION]->(nxt)
        """)

    log.info("Linking NEXT_VERSION chains for AreaOfStudyVersion ...")
    with driver.session() as session:
        session.run("""
            MATCH (a:AreaOfStudy)-[:HAS_VERSION]->(av:AreaOfStudyVersion)
            WITH  a, av ORDER BY av.year
            WITH  a, collect(av) AS versions
            UNWIND range(0, size(versions)-2) AS i
            WITH  versions[i] AS curr, versions[i+1] AS nxt
            MERGE (curr)-[:NEXT_VERSION]->(nxt)
        """)

    log.info("NEXT_VERSION chains created.")


# MAIN


def main() -> None:
    log.info("Connecting to Neo4j at %s ...", NEO4J_URI)

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        log.info("Connection verified.")
    except Exception as exc:
        log.error("Cannot connect to Neo4j: %s", exc)
        raise SystemExit(1)

    try:
        create_constraints(driver)

        log.info("Scanning DATASET_PATH: %s", DATASET_PATH)
        course_dirs, subject_dir = discover_folders(DATASET_PATH)

        log.info(
            "=== Step 1: Importing course files (%d course dir(s)) ===",
            len(course_dirs),
        )
        import_courses(driver, course_dirs)

        if subject_dir:
            log.info("=== Step 2: Importing subject archives from %s ===", subject_dir)
            import_subject_archives(driver, subject_dir)
        else:
            log.warning("No subject_archives folder found – skipping Step 2.")

        log.info("=== Step 3: Linking version chains ===")
        link_next_versions(driver)

        log.info("Import complete.")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
