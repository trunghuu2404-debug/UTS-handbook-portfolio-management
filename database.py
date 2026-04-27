"""
UTS Course Graph Importer
=========================
Reads any UTS course handbook JSON file (produced by post_2025_scrapping.py)
and imports it into Neo4j using parameterised Cypher — fully idempotent (MERGE).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JSON STRUCTURE  (mirroring scraper output)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Course
└── structure[]                          ← list of top-level Structure dicts
    Each Structure dict has:
      structure_name, structure_cp, structure_details
      items[]          ← list of Subject / Sub-Major / Choice Block / Major
      sub_sections[]   ← list of child Structure dicts  (recursive, same shape)

    A Structure has EITHER items OR sub_sections (or both).

Subject  (item where type == "Subject")
  code, name, credit_points, url, description
  requisite_list{}
    requisite{}        → rule + items[]  each with item_id, details, type
    anti_requisite{}   → rule + items[]  each with item_id, details
    other_requisite{}  → rule + items[]  each with note  (free-text)

Area of Study  (item where type in Major / Sub-Major / Choice Block)
  code, name, credit_points, url, description
  structure[]          ← same recursive structure as Course.structure

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRAPH MODEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nodes
  (:Course)         code, name, url, details
  (:Structure)      code (namespaced), name, credit_points, details
  (:Subject)        code, name, credit_points, url, description
  (:Major)          code, name, credit_points, url, description
  (:SubMajor)       code, name, credit_points, url, description
  (:ChoiceBlock)    code, name, credit_points, url, description
  (:Requisite)      subject_code, details, type, rule, item_id
  (:AntiRequisite)  subject_code, details, rule, item_id
  (:OtherRequisite) subject_code, note, rule

Relationships
  (:Course)                              -[:HAS_STRUCTURE    {order}]-> (:Structure)
  (:Structure)                           -[:HAS_SUB_SECTION  {order}]-> (:Structure)
  (:Structure)                           -[:HAS_SUBJECT      {order}]-> (:Subject)
  (:Structure)                           -[:HAS_AREA_OF_STUDY {order, area_type}]->
                                              (:Major | :SubMajor | :ChoiceBlock)
  (:Major | :SubMajor | :ChoiceBlock)    -[:HAS_STRUCTURE    {order}]-> (:Structure)
  (:Subject)                             -[:HAS_REQUISITE]->       (:Requisite)
  (:Subject)                             -[:HAS_ANTI_REQUISITE]->  (:AntiRequisite)
  (:Subject)                             -[:HAS_OTHER_REQUISITE]-> (:OtherRequisite)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python uts_graph_importer.py                             # 2026.json, localhost
  python uts_graph_importer.py path/to/course.json
  python uts_graph_importer.py course.json bolt://host:7687 user password
"""

from __future__ import annotations

import json
import sys

from neo4j import GraphDatabase


# ─────────────────────────────────────────────────────────────────────────────
# Label mapping  (scraper type string  →  Neo4j node label)
# ─────────────────────────────────────────────────────────────────────────────
AREA_LABEL: dict[str, str] = {
    "Major": "Major",
    "Sub-Major": "SubMajor",
    "Choice Block": "ChoiceBlock",
}


# ─────────────────────────────────────────────────────────────────────────────
# Driver wrapper
# ─────────────────────────────────────────────────────────────────────────────
class UTSGraphImporter:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def import_course(self, data: dict) -> None:
        course_code = data["course_code"]
        print(f"🚀  Importing: {data.get('course_name', '(unnamed)')}  [{course_code}]")

        with self.driver.session() as session:
            # 1. Course node
            session.execute_write(_create_course, data)

            # 2. Walk every top-level structure attached to the Course
            for order, struct in enumerate(data.get("structure", [])):
                session.execute_write(
                    _import_structure,
                    parent_code=course_code,
                    parent_label="Course",
                    struct=struct,
                    order=order,
                    namespace=course_code,
                )

        print("✅  Import complete.\n")


# ─────────────────────────────────────────────────────────────────────────────
# Transaction: Course node
# ─────────────────────────────────────────────────────────────────────────────
def _create_course(tx, data: dict) -> None:
    tx.run(
        """
        MERGE (c:Course {code: $code})
        SET c.name    = $name,
            c.url     = $url,
            c.details = $details
        """,
        code=data["course_code"],
        name=data.get("course_name", ""),
        url=data.get("course_url", ""),
        details=data.get("course_details", ""),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Transaction: one Structure node + everything inside it  (fully recursive)
#
# scrape_structure() produces dicts with:
#   structure_name, structure_cp, structure_details
#   items[]        ← Subjects or Areas of Study at THIS level
#   sub_sections[] ← child Structure dicts  (same shape, recursive)
#
# The `namespace` argument is threaded through recursion to build unique
# section codes even when section names like "Core" or "Options" repeat.
# ─────────────────────────────────────────────────────────────────────────────
def _import_structure(
    tx,
    parent_code: str,
    parent_label: str,
    struct: dict,
    order: int,
    namespace: str,
) -> None:

    sec_name = struct.get("structure_name", "Untitled Section")
    sec_cp = struct.get("structure_cp", "")
    sec_details = struct.get("structure_details", "")

    # Unique code: carry full ancestry as prefix
    section_code = f"{namespace}::{sec_name}"

    # ── 1. Upsert :Structure node ──────────────────────────────────────
    tx.run(
        """
        MERGE (s:Structure {code: $code})
        SET s.name          = $name,
            s.credit_points = $cp,
            s.details       = $details
        """,
        code=section_code,
        name=sec_name,
        cp=sec_cp,
        details=sec_details,
    )

    # ── 2. Link parent  -[:HAS_STRUCTURE]->  this Structure ───────────
    # Parent can be: Course, Structure, Major, SubMajor, ChoiceBlock
    tx.run(
        f"""
        MATCH (p:{parent_label} {{code: $parent_code}})
        MATCH (s:Structure       {{code: $section_code}})
        MERGE (p)-[:HAS_STRUCTURE {{order: $order}}]->(s)
        """,
        parent_code=parent_code,
        section_code=section_code,
        order=order,
    )

    # ── 3. sub_sections[]  →  child Structure nodes ───────────────────
    # Each sub-section is also a Structure; we create HAS_SUB_SECTION
    # in addition to HAS_STRUCTURE so both semantic relationships exist.
    for sub_order, sub_struct in enumerate(struct.get("sub_sections", [])):
        sub_name = sub_struct.get("structure_name", "Untitled Section")
        sub_code = f"{section_code}::{sub_name}"

        # Recurse: create the child Structure and link it
        _import_structure(
            tx,
            parent_code=section_code,
            parent_label="Structure",
            struct=sub_struct,
            order=sub_order,
            namespace=section_code,  # continue namespacing downward
        )

        # Semantic alias: Structure -[:HAS_SUB_SECTION]-> Structure
        tx.run(
            """
            MATCH (parent:Structure {code: $parent_code})
            MATCH (child:Structure  {code: $child_code})
            MERGE (parent)-[:HAS_SUB_SECTION {order: $order}]->(child)
            """,
            parent_code=section_code,
            child_code=sub_code,
            order=sub_order,
        )

    # ── 4. items[]  →  Subjects and/or Areas of Study ─────────────────
    for item_order, item in enumerate(struct.get("items", [])):
        item_type = item.get("type", "")

        if item_type == "Subject":
            # Upsert Subject and all its requisites
            _upsert_subject(tx, item)

            # Structure -[:HAS_SUBJECT]-> Subject
            tx.run(
                """
                MATCH (s:Structure {code: $sec_code})
                MATCH (subj:Subject {code: $subj_code})
                MERGE (s)-[:HAS_SUBJECT {order: $order}]->(subj)
                """,
                sec_code=section_code,
                subj_code=item["code"],
                order=item_order,
            )

        elif item_type in AREA_LABEL:
            label = AREA_LABEL[item_type]

            # Upsert the Area of Study node itself
            _upsert_area_of_study(tx, item, label)

            # Structure -[:HAS_AREA_OF_STUDY]-> Major|SubMajor|ChoiceBlock
            tx.run(
                f"""
                MATCH (s:Structure {{code: $sec_code}})
                MATCH (a:{label}   {{code: $area_code}})
                MERGE (s)-[:HAS_AREA_OF_STUDY {{order: $order, area_type: $area_type}}]->(a)
                """,
                sec_code=section_code,
                area_code=item["code"],
                order=item_order,
                area_type=item_type,
            )

            # Recurse into the AoS's own internal structure[]
            # (same shape as Course.structure — scraped by scrape_aos)
            for sub_order, sub_struct in enumerate(item.get("structure", [])):
                _import_structure(
                    tx,
                    parent_code=item["code"],
                    parent_label=label,
                    struct=sub_struct,
                    order=sub_order,
                    namespace=item["code"],  # AoS code starts fresh namespace
                )

        else:
            if item_type:  # suppress noise for empty type fields
                print(
                    f"  ⚠️   Unknown item type '{item_type}' "
                    f"(code={item.get('code', '?')})"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Subject node  +  requisites
# ─────────────────────────────────────────────────────────────────────────────
def _upsert_subject(tx, item: dict) -> None:
    tx.run(
        """
        MERGE (s:Subject {code: $code})
        SET s.name          = $name,
            s.credit_points = $cp,
            s.url           = $url,
            s.description   = $desc
        """,
        code=item["code"],
        name=item.get("name", ""),
        cp=item.get("credit_points", ""),
        url=item.get("url", ""),
        desc=item.get("description", ""),
    )

    req_list = item.get("requisite_list", {})
    if req_list:
        _process_requisites(tx, item["code"], req_list)


# ─────────────────────────────────────────────────────────────────────────────
# Area of Study node  (Major / SubMajor / ChoiceBlock)
# Internal structure[] is handled by the caller via _import_structure recursion.
# ─────────────────────────────────────────────────────────────────────────────
def _upsert_area_of_study(tx, item: dict, label: str) -> None:
    tx.run(
        f"""
        MERGE (a:{label} {{code: $code}})
        SET a.name          = $name,
            a.credit_points = $cp,
            a.url           = $url,
            a.description   = $desc
        """,
        code=item["code"],
        name=item.get("name", ""),
        cp=item.get("credit_points", ""),
        url=item.get("url", ""),
        desc=item.get("description", ""),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Requisite processing
#
# The scraper captures exactly three keys inside requisite_list{}:
#
#   "requisite"       – things the student must satisfy BEFORE enrolling.
#                       Items have: item_id, details, type
#                         type = "Academic requisite"   (passed subjects / CP thresholds)
#                         type = "Admission requisite"  (must be admitted to a course/major)
#                       → Node:  (:Requisite)
#                       → Rel:   (Subject)-[:HAS_REQUISITE]->(:Requisite)
#
#   "anti_requisite"  – subjects that PREVENT enrolment if already completed.
#                       Items have: item_id, details   (no type field)
#                       → Node:  (:AntiRequisite)
#                       → Rel:   (Subject)-[:HAS_ANTI_REQUISITE]->(:AntiRequisite)
#
#   "other_requisite" – free-text informational notes.
#                       Items have: note                (no item_id / details)
#                       → Node:  (:OtherRequisite)
#                       → Rel:   (Subject)-[:HAS_OTHER_REQUISITE]->(:OtherRequisite)
#
# Each requisite node is keyed on (subject_code + details/note) to avoid
# duplicates within a subject's requisite set while remaining idempotent.
# ─────────────────────────────────────────────────────────────────────────────
def _process_requisites(tx, subject_code: str, req_list: dict) -> None:

    # ── requisite  (Academic requisite / Admission requisite) ─────────
    req_block = req_list.get("requisite")
    if req_block:
        rule = req_block.get("rule", "")
        for entry in req_block.get("items", []):
            item_id = entry.get("item_id", "")
            details = entry.get("details", "")
            req_type = entry.get(
                "type", ""
            )  # "Academic requisite" or "Admission requisite"

            if not details:
                continue

            # Upsert :Requisite node
            tx.run(
                """
                MERGE (r:Requisite {subject_code: $scode, details: $details})
                SET r.type    = $req_type,
                    r.rule    = $rule,
                    r.item_id = $item_id
                """,
                scode=subject_code,
                details=details,
                req_type=req_type,
                rule=rule,
                item_id=item_id,
            )

            # (Subject)-[:HAS_REQUISITE]->(:Requisite)
            tx.run(
                """
                MATCH (s:Subject   {code: $scode})
                MATCH (r:Requisite {subject_code: $scode, details: $details})
                MERGE (s)-[:HAS_REQUISITE]->(r)
                """,
                scode=subject_code,
                details=details,
            )

    # ── anti_requisite ────────────────────────────────────────────────
    anti_block = req_list.get("anti_requisite")
    if anti_block:
        rule = anti_block.get("rule", "")
        for entry in anti_block.get("items", []):
            item_id = entry.get("item_id", "")
            details = entry.get("details", "")

            if not details:
                continue

            # Upsert :AntiRequisite node
            tx.run(
                """
                MERGE (a:AntiRequisite {subject_code: $scode, details: $details})
                SET a.rule    = $rule,
                    a.item_id = $item_id
                """,
                scode=subject_code,
                details=details,
                rule=rule,
                item_id=item_id,
            )

            # (Subject)-[:HAS_ANTI_REQUISITE]->(:AntiRequisite)
            tx.run(
                """
                MATCH (s:Subject       {code: $scode})
                MATCH (a:AntiRequisite {subject_code: $scode, details: $details})
                MERGE (s)-[:HAS_ANTI_REQUISITE]->(a)
                """,
                scode=subject_code,
                details=details,
            )

    # ── other_requisite  (free-text notes) ───────────────────────────
    other_block = req_list.get("other_requisite")
    if other_block:
        rule = other_block.get("rule", "")
        for entry in other_block.get("items", []):
            note = entry.get("note", "").strip()

            if not note:
                continue

            # Upsert :OtherRequisite node
            tx.run(
                """
                MERGE (o:OtherRequisite {subject_code: $scode, note: $note})
                SET o.rule = $rule
                """,
                scode=subject_code,
                note=note,
                rule=rule,
            )

            # (Subject)-[:HAS_OTHER_REQUISITE]->(:OtherRequisite)
            tx.run(
                """
                MATCH (s:Subject        {code: $scode})
                MATCH (o:OtherRequisite {subject_code: $scode, note: $note})
                MERGE (s)-[:HAS_OTHER_REQUISITE]->(o)
                """,
                scode=subject_code,
                note=note,
            )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    json_file = "2026.json"
    neo4j_uri = "neo4j://127.0.0.1:7687"
    neo4j_user = "neo4j"
    neo4j_pass = "Trungvip2404@"

    try:
        with open(json_file, encoding="utf-8") as f:
            course_data = json.load(f)
    except FileNotFoundError:
        print(f"❌  File not found: {json_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌  JSON parse error: {e}")
        sys.exit(1)

    importer = UTSGraphImporter(neo4j_uri, neo4j_user, neo4j_pass)
    try:
        importer.import_course(course_data)
    finally:
        importer.close()


if __name__ == "__main__":
    main()
