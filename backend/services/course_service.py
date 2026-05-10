"""
services/course_service.py
--------------------------
All Cypher queries and data transformation for Course endpoints.
Routes call these functions — no Cypher lives in routes.
"""

from database.neo4j import run_query
from models.schemas import (
    CourseOut,
    CourseVersionOut,
    GraphResponse,
    GraphNode,
    GraphLink,
)


def get_all_courses() -> list[CourseOut]:
    """Return every Course node as a lightweight listing."""
    cypher = """
    MATCH (c:Course)
    RETURN c.code AS code,
           c.name AS name
    ORDER BY c.name
    """
    rows = run_query(cypher)
    return [CourseOut(code=r["code"], name=r["name"]) for r in rows]


def get_course_versions(course_code: str) -> list[CourseVersionOut]:
    """Return all CourseVersion nodes for a given course code."""
    cypher = """
    MATCH (c:Course {code: $code})-[:HAS_VERSION]->(cv:CourseVersion)
    RETURN cv.id                        AS id,
           cv.course_code               AS course_code,
           cv.course_name               AS course_name,
           cv.year                      AS year,
           cv.course_url                AS course_url,
           cv.course_details            AS course_details,
           cv.course_learning_outcomes  AS course_learning_outcomes
    ORDER BY cv.year DESC
    """
    rows = run_query(cypher, {"code": course_code})

    result = []
    for r in rows:
        lo = r.get("course_learning_outcomes") or []
        result.append(
            CourseVersionOut(
                id=r["id"],
                course_code=r["course_code"],
                course_name=r["course_name"],
                year=r["year"],
                course_url=r.get("course_url"),
                course_details=r.get("course_details"),
                course_learning_outcomes=lo if isinstance(lo, list) else [lo],
            )
        )
    return result


def get_course_graph(course_code: str, year=None) -> GraphResponse:
    """
    Build the full graph for a course (optionally filtered to one year).

    The graph includes:
        Course → CourseVersion → Structure → (Subject | AreaOfStudy)
        Structure → child Structure (HAS_CHILD)

    Each node gets a 'type' so the frontend can colour-code them.
    """
    # Build optional year filter — must use WHERE not AND after MATCH
    year_filter = "WHERE cv.year = $year" if year is not None else ""

    cypher = f"""
    MATCH (c:Course {{code: $code}})-[:HAS_VERSION]->(cv:CourseVersion)
    {year_filter}

    // Top-level structures
    OPTIONAL MATCH (cv)-[:HAS_STRUCTURE]->(top:Structure)

    // Nested child structures (up to 5 levels deep)
    OPTIONAL MATCH (top)-[:HAS_CHILD*0..5]->(child:Structure)

    // Subjects inside any structure node
    OPTIONAL MATCH (child)-[:CONTAINS]->(subj:Subject)

    // Areas of study inside any structure node
    OPTIONAL MATCH (child)-[:CONTAINS_AOS]->(aos:AreaOfStudy)

    RETURN
        c.code          AS course_code,
        c.name          AS course_name,
        cv.id           AS cv_id,
        cv.year         AS cv_year,
        cv.course_name  AS cv_name,
        top.id          AS top_id,
        top.structure_name AS top_name,
        top.structure_cp   AS top_cp,
        child.id           AS child_id,
        child.structure_name AS child_name,
        child.structure_cp   AS child_cp,
        subj.code       AS subj_code,
        subj.name       AS subj_name,
        aos.code        AS aos_code,
        aos.name        AS aos_name
    """

    rows = run_query(cypher, {"code": course_code, "year": year})

    nodes: dict[str, GraphNode] = {}
    links: list[GraphLink] = []
    seen_links: set[tuple] = set()

    def add_node(node_id: str, label: str, node_type: str, props: dict = None) -> None:
        if node_id and node_id not in nodes:
            nodes[node_id] = GraphNode(
                id=node_id, label=label, type=node_type, properties=props or {}
            )

    def add_link(source: str, target: str, rel: str, props: dict = None) -> None:
        if source and target:
            key = (source, target, rel)
            if key not in seen_links:
                seen_links.add(key)
                links.append(
                    GraphLink(
                        source=source,
                        target=target,
                        relationship=rel,
                        properties=props or {},
                    )
                )

    for r in rows:
        # Course node
        add_node(r["course_code"], r["course_name"], "Course")

        # CourseVersion node
        if r.get("cv_id"):
            add_node(
                r["cv_id"],
                f"{r['cv_name']} ({r['cv_year']})",
                "CourseVersion",
                {"year": r["cv_year"]},
            )
            add_link(r["course_code"], r["cv_id"], "HAS_VERSION")

        # Top-level structure
        if r.get("top_id"):
            add_node(
                r["top_id"],
                r["top_name"] or "Structure",
                "Structure",
                {"credit_points": r.get("top_cp")},
            )
            add_link(r["cv_id"], r["top_id"], "HAS_STRUCTURE")

        # Child / nested structure
        if r.get("child_id") and r.get("child_id") != r.get("top_id"):
            add_node(
                r["child_id"],
                r["child_name"] or "Structure",
                "Structure",
                {"credit_points": r.get("child_cp")},
            )
            # child could be directly under top or deeper — link to closest known parent
            parent = r.get("top_id")
            add_link(parent, r["child_id"], "HAS_CHILD")

        # Subject leaf
        if r.get("subj_code"):
            add_node(r["subj_code"], r["subj_name"] or r["subj_code"], "Subject")
            parent_struct = r.get("child_id") or r.get("top_id")
            if parent_struct:
                add_link(parent_struct, r["subj_code"], "CONTAINS")

        # AreaOfStudy leaf
        if r.get("aos_code"):
            add_node(r["aos_code"], r["aos_name"] or r["aos_code"], "AreaOfStudy")
            parent_struct = r.get("child_id") or r.get("top_id")
            if parent_struct:
                add_link(parent_struct, r["aos_code"], "CONTAINS_AOS")

    return GraphResponse(nodes=list(nodes.values()), links=links)
