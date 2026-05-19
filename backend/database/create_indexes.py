"""
backend/database/create_indexes.py
------------------------------------
One-time script: creates Neo4j indexes for all properties that are
used in MATCH patterns throughout the application.

Run once after importing data:
    cd backend
    python -m database.create_indexes

Safe to re-run — IF NOT EXISTS means already-present indexes are skipped.
"""

import logging
from database.neo4j import get_driver, close_driver

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

INDEXES = [
    # Subject lookups (most frequent — every prereq/similarity/detail query)
    ("Subject", "code", "idx_subject_code"),
    ("SubjectVersion", "year", "idx_subjectversion_year"),
    ("SubjectVersion", "code", "idx_subjectversion_code"),
    # Course lookups
    ("Course", "code", "idx_course_code"),
    ("CourseVersion", "year", "idx_courseversion_year"),
    # Requisite node lookups
    ("AdmissionRequisite", "id", "idx_admissionrequisite_id"),
    ("OtherRequisite", "id", "idx_otherrequisite_id"),
    # Structure traversal
    ("Structure", "structure_name", "idx_structure_name"),
]


def create_indexes():
    driver = get_driver()
    created = 0
    skipped = 0

    with driver.session() as session:
        for label, prop, name in INDEXES:
            cypher = (
                f"CREATE INDEX {name} IF NOT EXISTS " f"FOR (n:{label}) ON (n.{prop})"
            )
            try:
                session.run(cypher)
                log.info(f"  OK  {name}  ({label}.{prop})")
                created += 1
            except Exception as exc:
                log.warning(f"  SKIP  {name}: {exc}")
                skipped += 1

    log.info(f"\nDone — {created} index(es) created/verified, {skipped} skipped.")


if __name__ == "__main__":
    create_indexes()
    close_driver()
