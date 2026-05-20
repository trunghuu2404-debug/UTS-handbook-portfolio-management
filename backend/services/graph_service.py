"""
Graph-specific queries that return node/link JSON for visualisation:
  - Subject requisite network for one SubjectVersion
  - Area of Study internal structure graph
"""

from database.neo4j import run_query
from models.schemas import GraphResponse, GraphNode, GraphLink


# Helper
def _add_node(
    nodes: dict, node_id: str, label: str, node_type: str, props: dict = None
):
    if node_id and node_id not in nodes:
        nodes[node_id] = GraphNode(
            id=node_id, label=label, type=node_type, properties=props or {}
        )


def _add_link(
    links: list, seen: set, source: str, target: str, rel: str, props: dict = None
):
    if source and target:
        key = (source, target, rel)
        if key not in seen:
            seen.add(key)
            links.append(
                GraphLink(
                    source=source,
                    target=target,
                    relationship=rel,
                    properties=props or {},
                )
            )


# Subject requisite graph


def get_subject_requisite_graph(subject_code: str, year: int) -> GraphResponse:

    # Return a graph of one SubjectVersion and all its requisite relationships:
    #   - PREREQUISITE       → other SubjectVersion nodes
    #   - ANTI_REQUISITE     → other SubjectVersion nodes
    #   - HAS_ADMISSION_REQUISITE → AdmissionRequisite nodes
    #   - HAS_OTHER_REQUISITE     → OtherRequisite nodes

    # Relationship properties (item_id, rule) are stored on the link.

    vid = f"{subject_code}_{year}"
    nodes: dict[str, GraphNode] = {}
    links: list[GraphLink] = []
    seen: set[tuple] = set()

    # Centre node
    centre_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})
    RETURN sv.id AS id, sv.name AS name, sv.code AS code, sv.year AS year
    """
    centre_rows = run_query(centre_cypher, {"vid": vid})
    if not centre_rows:
        return GraphResponse(nodes=[], links=[])

    c = centre_rows[0]
    _add_node(
        nodes,
        vid,
        f"{c['code']} ({c['year']})",
        "SubjectVersion",
        {"code": c["code"], "name": c.get("name"), "year": c["year"]},
    )

    # Prerequisites
    prereq_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[r:PREREQUISITE]->(pre:SubjectVersion)
    OPTIONAL MATCH (pre)-[:OF_SUBJECT]->(s:Subject)
    RETURN pre.id    AS id,
           pre.code  AS code,
           pre.year  AS year,
           coalesce(s.name, pre.name) AS name,
           r.item_id AS item_id,
           r.item_type AS item_type,
           r.rule    AS rule
    """
    for r in run_query(prereq_cypher, {"vid": vid}):
        _add_node(
            nodes,
            r["id"],
            f"{r['code']} ({r['year']})",
            "SubjectVersion",
            {"code": r["code"], "name": r.get("name"), "year": r["year"]},
        )
        _add_link(
            links,
            seen,
            vid,
            r["id"],
            "PREREQUISITE",
            {
                "item_id": r.get("item_id", ""),
                "item_type": r.get("item_type", ""),
                "rule": r.get("rule", ""),
            },
        )

    # Anti-requisites
    anti_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[r:ANTI_REQUISITE]->(anti:SubjectVersion)
    OPTIONAL MATCH (anti)-[:OF_SUBJECT]->(s:Subject)
    RETURN anti.id   AS id,
           anti.code AS code,
           anti.year AS year,
           coalesce(s.name, anti.name) AS name,
           r.item_id AS item_id,
           r.rule    AS rule
    """
    for r in run_query(anti_cypher, {"vid": vid}):
        _add_node(
            nodes,
            r["id"],
            f"{r['code']} ({r['year']})",
            "SubjectVersion",
            {"code": r["code"], "name": r.get("name"), "year": r["year"]},
        )
        _add_link(
            links,
            seen,
            vid,
            r["id"],
            "ANTI_REQUISITE",
            {"item_id": r.get("item_id", ""), "rule": r.get("rule", "")},
        )

    # Admission requisites
    adm_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[:HAS_ADMISSION_REQUISITE]->(ar:AdmissionRequisite)
    RETURN ar.id        AS id,
           ar.detail    AS detail,
           ar.item_id   AS item_id,
           ar.item_type AS item_type,
           ar.rule      AS rule
    """
    for r in run_query(adm_cypher, {"vid": vid}):
        label = (r.get("detail") or "Admission Requisite")[:60]
        _add_node(
            nodes,
            r["id"],
            label,
            "AdmissionRequisite",
            {
                "item_id": r.get("item_id"),
                "item_type": r.get("item_type"),
                "rule": r.get("rule"),
            },
        )
        _add_link(links, seen, vid, r["id"], "HAS_ADMISSION_REQUISITE")

    # Other requisites
    other_cypher = """
    MATCH (sv:SubjectVersion {id: $vid})-[:HAS_OTHER_REQUISITE]->(or:OtherRequisite)
    RETURN or.id   AS id,
           or.note AS note,
           or.rule AS rule
    """
    for r in run_query(other_cypher, {"vid": vid}):
        _add_node(
            nodes,
            r["id"],
            r.get("note") or "Other Requisite",
            "OtherRequisite",
            {"rule": r.get("rule")},
        )
        _add_link(links, seen, vid, r["id"], "HAS_OTHER_REQUISITE")

    return GraphResponse(nodes=list(nodes.values()), links=links)


# Area of Study structure graph


def get_aos_graph(aos_code: str, year=None) -> GraphResponse:
    """
    Return a graph of an AreaOfStudy and its internal structure
    (AreaOfStudyVersion → Structure → Subjects).
    Optionally filter to a single year.
    """
    year_filter = "WHERE av.year = $year" if year is not None else ""

    cypher = f"""
    MATCH (a:AreaOfStudy {{code: $code}})-[:HAS_VERSION]->(av:AreaOfStudyVersion)
    {year_filter}
    OPTIONAL MATCH (av)-[:HAS_STRUCTURE]->(st:Structure)
    OPTIONAL MATCH (st)-[:HAS_CHILD*0..5]->(child:Structure)
    OPTIONAL MATCH (child)-[:CONTAINS]->(subj:Subject)
    RETURN
        a.code          AS aos_code,
        a.name          AS aos_name,
        av.id           AS av_id,
        av.year         AS av_year,
        av.type         AS av_type,
        av.credit_points AS av_cp,
        st.id           AS st_id,
        st.structure_name AS st_name,
        st.structure_cp   AS st_cp,
        child.id        AS child_id,
        child.structure_name AS child_name,
        subj.code       AS subj_code,
        subj.name       AS subj_name
    """
    rows = run_query(cypher, {"code": aos_code, "year": year})

    nodes: dict[str, GraphNode] = {}
    links: list[GraphLink] = []
    seen: set[tuple] = set()

    for r in rows:
        # AreaOfStudy root
        _add_node(nodes, r["aos_code"], r["aos_name"] or r["aos_code"], "AreaOfStudy")

        # AreaOfStudyVersion
        if r.get("av_id"):
            label = f"{r['aos_name']} ({r['av_year']})"
            _add_node(
                nodes,
                r["av_id"],
                label,
                "AreaOfStudyVersion",
                {
                    "year": r["av_year"],
                    "type": r.get("av_type"),
                    "credit_points": r.get("av_cp"),
                },
            )
            _add_link(links, seen, r["aos_code"], r["av_id"], "HAS_VERSION")

        # Top structure
        if r.get("st_id"):
            _add_node(
                nodes,
                r["st_id"],
                r.get("st_name") or "Structure",
                "Structure",
                {"credit_points": r.get("st_cp")},
            )
            _add_link(links, seen, r["av_id"], r["st_id"], "HAS_STRUCTURE")

        # Child structure
        if r.get("child_id") and r.get("child_id") != r.get("st_id"):
            _add_node(
                nodes, r["child_id"], r.get("child_name") or "Structure", "Structure"
            )
            _add_link(links, seen, r["st_id"], r["child_id"], "HAS_CHILD")

        # Subject
        if r.get("subj_code"):
            _add_node(
                nodes, r["subj_code"], r.get("subj_name") or r["subj_code"], "Subject"
            )
            parent = r.get("child_id") or r.get("st_id")
            if parent:
                _add_link(links, seen, parent, r["subj_code"], "CONTAINS")

    return GraphResponse(nodes=list(nodes.values()), links=links)
