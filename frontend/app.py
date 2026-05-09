"""
frontend/app.py
---------------
Streamlit testing frontend for the UTS Curriculum Digital Twin API.

Run:
    streamlit run app.py

Ensure the FastAPI backend is running at API_BASE_URL before starting.
"""

import streamlit as st
import requests
import json

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = "http://localhost:8000"

st.set_page_config(
    page_title="UTS Curriculum Digital Twin",
    page_icon="🎓",
    layout="wide",
)


# ---------------------------------------------------------------------------
# API helper — centralised request handling with error surfacing
# ---------------------------------------------------------------------------


def api_get(path: str, params: dict = None) -> dict | list | None:
    """
    Call the FastAPI backend with GET.
    Returns parsed JSON on success, displays an error and returns None on failure.
    """
    url = f"{API_BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 404:
            st.warning(f"Not found: {resp.json().get('detail', path)}")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error(
            f"Cannot connect to the API at **{API_BASE_URL}**. "
            "Is the FastAPI backend running?"
        )
        return None
    except requests.exceptions.HTTPError as exc:
        st.error(f"API error {exc.response.status_code}: {exc.response.text}")
        return None
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Sidebar — selectors
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🎓 UTS Digital Twin")
    st.markdown("---")

    # ── Course selector ───────────────────────────────────────────────────
    st.subheader("Course")
    courses_data = api_get("/courses")
    course_options = {}
    if courses_data:
        course_options = {f"{c['name']} ({c['code']})": c["code"] for c in courses_data}

    selected_course_label = st.selectbox(
        "Select course", options=list(course_options.keys()), key="course_select"
    )
    selected_course_code = course_options.get(selected_course_label)

    # Year filter (populated after course is chosen)
    selected_year = None
    if selected_course_code:
        versions_data = api_get(f"/courses/{selected_course_code}/versions")
        if versions_data:
            year_options = ["All versions"] + [str(v["year"]) for v in versions_data]
            selected_year_str = st.selectbox(
                "Version (year)", year_options, key="year_select"
            )
            selected_year = (
                int(selected_year_str) if selected_year_str != "All versions" else None
            )

    st.markdown("---")

    # ── Subject selector ───────────────────────────────────────────────────
    st.subheader("Subject")
    subject_search = st.text_input(
        "Search by code or name",
        placeholder="e.g. 31265 or Communication",
        key="subj_search",
    )
    subject_options = {}
    if subject_search and len(subject_search) >= 2:
        search_data = api_get("/subjects/search", params={"q": subject_search})
        if search_data:
            subject_options = {
                f"{s['name']} ({s['code']})": s["code"] for s in search_data
            }

    selected_subject_label = st.selectbox(
        "Select subject", options=list(subject_options.keys()), key="subject_select"
    )
    selected_subject_code = subject_options.get(selected_subject_label)

    # Year for subject version
    selected_subject_year = st.number_input(
        "Subject version year",
        min_value=2020,
        max_value=2030,
        value=2025,
        step=1,
        key="subj_year",
    )

    st.markdown("---")
    st.caption("FastAPI backend: " + API_BASE_URL)


# ---------------------------------------------------------------------------
# Main area — tabbed layout
# ---------------------------------------------------------------------------

st.title("UTS Curriculum Digital Twin")
st.markdown("Explore course structures and subject requisites stored in Neo4j.")

tab_course, tab_subject, tab_requisites, tab_graph = st.tabs(
    [
        "📚 Course Structure",
        "📖 Subject Detail",
        "🔗 Subject Requisites",
        "🕸️ Requisite Graph",
    ]
)


# ===========================================================================
# TAB 1 — Course Structure
# ===========================================================================

with tab_course:
    st.header("Course structure")

    if not selected_course_code:
        st.info("Select a course in the sidebar to begin.")
    else:
        year_label = str(selected_year) if selected_year else "all versions"
        st.subheader(f"{selected_course_label}  ·  {year_label}")

        with st.spinner("Loading course graph …"):
            params = {"year": selected_year} if selected_year else {}
            graph_data = api_get(
                f"/courses/{selected_course_code}/graph", params=params
            )

        if graph_data:
            nodes = graph_data.get("nodes", [])
            links = graph_data.get("links", [])

            # ── Summary metrics ───────────────────────────────────────────
            col1, col2, col3, col4 = st.columns(4)
            type_counts = {}
            for n in nodes:
                t = n.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

            col1.metric("Total nodes", len(nodes))
            col2.metric("Total relationships", len(links))
            col3.metric("Structures", type_counts.get("Structure", 0))
            col4.metric("Subjects", type_counts.get("Subject", 0))

            st.markdown("---")

            # ── Node table grouped by type ────────────────────────────────
            node_types = sorted(set(n["type"] for n in nodes))
            selected_type = st.selectbox(
                "Filter nodes by type", ["All"] + node_types, key="node_type_filter"
            )
            filtered_nodes = (
                nodes
                if selected_type == "All"
                else [n for n in nodes if n["type"] == selected_type]
            )

            st.markdown(f"**{len(filtered_nodes)} node(s)**")
            for node in filtered_nodes:
                props = node.get("properties", {})
                props_str = "  ·  ".join(f"`{k}`: {v}" for k, v in props.items() if v)
                st.markdown(f"- **{node['label']}** `{node['type']}` {props_str}")

            st.markdown("---")

            # ── Relationship table ────────────────────────────────────────
            with st.expander(f"Relationships ({len(links)})", expanded=False):
                for link in links:
                    props = link.get("properties", {})
                    props_str = "  ".join(f"`{k}={v}`" for k, v in props.items() if v)
                    st.markdown(
                        f"- `{link['source']}` **→{link['relationship']}→** "
                        f"`{link['target']}` {props_str}"
                    )

            # ── Raw JSON ──────────────────────────────────────────────────
            with st.expander("Raw graph JSON", expanded=False):
                st.json(graph_data)

        # ── Course version metadata ───────────────────────────────────────
        if selected_year:
            st.markdown("---")
            st.subheader("Version metadata")
            with st.spinner("Loading version metadata …"):
                versions = api_get(f"/courses/{selected_course_code}/versions")
            if versions:
                version = next(
                    (v for v in versions if v["year"] == selected_year), None
                )
                if version:
                    st.markdown(f"**URL:** {version.get('course_url') or '—'}")

                    details = version.get("course_details")
                    if details:
                        with st.expander("Course details"):
                            st.write(details)

                    clo = version.get("course_learning_outcomes") or []
                    if clo:
                        with st.expander(f"Learning outcomes ({len(clo)})"):
                            for i, lo in enumerate(clo, 1):
                                st.markdown(f"{i}. {lo}")


# ===========================================================================
# TAB 2 — Subject Detail
# ===========================================================================

with tab_subject:
    st.header("Subject detail")

    if not selected_subject_code:
        st.info("Search for a subject in the sidebar, then select it.")
    else:
        with st.spinner(f"Loading subject {selected_subject_code} …"):
            detail = api_get(f"/subjects/{selected_subject_code}")

        if detail:
            st.subheader(f"{detail['name']}  ·  `{detail['code']}`")

            versions = detail.get("versions", [])
            st.caption(f"{len(versions)} version(s) in database")

            # ── Version picker ────────────────────────────────────────────
            version_years = [v["year"] for v in versions]
            chosen_year = (
                st.select_slider(
                    "View version",
                    options=sorted(version_years),
                    value=max(version_years),
                    key="subject_version_slider",
                )
                if version_years
                else None
            )

            chosen_version = (
                next((v for v in versions if v["year"] == chosen_year), None)
                if chosen_year
                else None
            )

            if chosen_version:
                col1, col2, col3 = st.columns(3)
                col1.metric("Credit points", chosen_version.get("credit_points") or "—")
                col2.metric("Faculty", chosen_version.get("faculty") or "—")
                col3.metric(
                    "Workload (hrs)", chosen_version.get("total_workload_hours") or "—"
                )

                st.markdown("---")

                # Core metadata
                meta_cols = st.columns(2)
                with meta_cols[0]:
                    st.markdown(f"**Type:** {chosen_version.get('type') or '—'}")
                    st.markdown(
                        f"**Study level:** {chosen_version.get('study_level') or '—'}"
                    )
                    st.markdown(
                        f"**Result type:** {chosen_version.get('result_type') or '—'}"
                    )
                with meta_cols[1]:
                    url = chosen_version.get("url")
                    if url:
                        st.markdown(f"**URL:** [{url}]({url})")

                st.markdown("---")

                # Description
                desc = chosen_version.get("description")
                if desc:
                    with st.expander("Description", expanded=True):
                        st.write(desc)

                # Learning outcomes
                lo = chosen_version.get("learning_outcomes") or []
                if lo:
                    with st.expander(f"Learning outcomes ({len(lo)})", expanded=True):
                        for i, outcome in enumerate(lo, 1):
                            st.markdown(f"{i}. {outcome}")

                # Teaching activities
                tla = chosen_version.get("teaching_and_learning_activities")
                if tla:
                    with st.expander("Teaching & learning activities"):
                        st.write(tla)

                # Requisite rules (stored as strings on the node)
                req_rule = chosen_version.get("requisite_rule")
                anti_rule = chosen_version.get("anti_requisite_rule")
                if req_rule or anti_rule:
                    with st.expander("Requisite rules"):
                        if req_rule:
                            st.markdown(f"**Prerequisite rule:** `{req_rule}`")
                        if anti_rule:
                            st.markdown(f"**Anti-requisite rule:** `{anti_rule}`")

            # ── Version evolution table ───────────────────────────────────
            with st.expander("All versions summary", expanded=False):
                for v in versions:
                    st.markdown(
                        f"**{v['year']}** — {v.get('faculty') or '—'} · "
                        f"{v.get('credit_points') or '—'} CP · "
                        f"{v.get('study_level') or '—'}"
                    )


# ===========================================================================
# TAB 3 — Subject Requisites
# ===========================================================================

with tab_requisites:
    st.header("Subject requisites")

    if not selected_subject_code:
        st.info("Search for a subject in the sidebar, then select it.")
    else:
        year = int(selected_subject_year)
        with st.spinner(f"Loading requisites for {selected_subject_code} ({year}) …"):
            reqs = api_get(
                f"/subjects/{selected_subject_code}/version/{year}/requisites"
            )

        if reqs:
            st.subheader(
                f"{reqs.get('name') or reqs['code']}  ·  "
                f"`{reqs['code']}_{reqs['year']}`"
            )

            # Rule strings
            req_rule = reqs.get("requisite_rule")
            anti_rule = reqs.get("anti_requisite_rule")
            if req_rule:
                st.info(f"**Prerequisite rule:** {req_rule}")
            if anti_rule:
                st.warning(f"**Anti-requisite rule:** {anti_rule}")

            st.markdown("---")

            col_pre, col_anti = st.columns(2)

            # ── Prerequisites ─────────────────────────────────────────────
            with col_pre:
                prereqs = reqs.get("prerequisites", [])
                st.markdown(f"### Prerequisites  `{len(prereqs)}`")
                if prereqs:
                    for p in prereqs:
                        with st.container(border=True):
                            st.markdown(f"**{p['name']}**  `{p['code']}`")
                            st.caption(
                                f"Item `{p['item_id']}` · "
                                f"{p.get('item_type') or 'Academic'} · "
                                f"Year {p['year']}"
                            )
                else:
                    st.caption("None")

            # ── Anti-requisites ───────────────────────────────────────────
            with col_anti:
                antis = reqs.get("anti_requisites", [])
                st.markdown(f"### Anti-requisites  `{len(antis)}`")
                if antis:
                    for a in antis:
                        with st.container(border=True):
                            st.markdown(f"**{a['name']}**  `{a['code']}`")
                            st.caption(f"Item `{a['item_id']}` · Year {a['year']}")
                else:
                    st.caption("None")

            st.markdown("---")

            col_adm, col_other = st.columns(2)

            # ── Admission requisites ──────────────────────────────────────
            with col_adm:
                adms = reqs.get("admission_requisites", [])
                st.markdown(f"### Admission requisites  `{len(adms)}`")
                if adms:
                    for adm in adms:
                        with st.container(border=True):
                            st.markdown(adm.get("detail") or "—")
                            st.caption(
                                f"Item `{adm['item_id']}` · {adm.get('item_type') or '—'}"
                            )
                else:
                    st.caption("None")

            # ── Other requisites ──────────────────────────────────────────
            with col_other:
                others = reqs.get("other_requisites", [])
                st.markdown(f"### Other requisites  `{len(others)}`")
                if others:
                    for o in others:
                        with st.container(border=True):
                            st.markdown(f"**{o.get('note') or '—'}**")
                            st.caption(o.get("rule") or "")
                else:
                    st.caption("None")


# ===========================================================================
# TAB 4 — Requisite Graph (raw JSON for now, ready for D3/Cytoscape)
# ===========================================================================

with tab_graph:
    st.header("Requisite graph  (JSON)")
    st.markdown(
        "Raw graph payload — pipe this into D3.js, Cytoscape, or vis-network "
        "on the frontend for visual rendering."
    )

    if not selected_subject_code:
        st.info("Search for a subject in the sidebar, then select it.")
    else:
        year = int(selected_subject_year)
        with st.spinner(
            f"Loading requisite graph for {selected_subject_code} ({year}) …"
        ):
            graph = api_get(f"/graph/subject/{selected_subject_code}/version/{year}")

        if graph:
            nodes = graph.get("nodes", [])
            links = graph.get("links", [])

            col1, col2 = st.columns(2)
            col1.metric("Nodes", len(nodes))
            col2.metric("Relationships", len(links))

            st.markdown("---")

            # ── Node breakdown ────────────────────────────────────────────
            st.subheader("Nodes")
            type_groups: dict[str, list] = {}
            for n in nodes:
                t = n.get("type", "Unknown")
                type_groups.setdefault(t, []).append(n)

            for node_type, group in type_groups.items():
                with st.expander(f"{node_type}  ({len(group)})", expanded=True):
                    for n in group:
                        props = n.get("properties", {})
                        props_str = "  ·  ".join(
                            f"`{k}`: {v}" for k, v in props.items() if v
                        )
                        st.markdown(f"- **{n['label']}**  {props_str}")

            # ── Edge breakdown ────────────────────────────────────────────
            st.subheader("Relationships")
            with st.expander(f"All edges  ({len(links)})", expanded=True):
                for link in links:
                    props = link.get("properties", {})
                    props_items = [f"`{k}={v}`" for k, v in props.items() if v]
                    props_str = "  ".join(props_items)
                    st.markdown(
                        f"- `{link['source']}` **→{link['relationship']}→** "
                        f"`{link['target']}`  {props_str}"
                    )

            # ── Full JSON ─────────────────────────────────────────────────
            with st.expander("Full raw JSON", expanded=False):
                st.json(graph)

            # ── Download ──────────────────────────────────────────────────
            st.download_button(
                label="Download graph JSON",
                data=json.dumps(graph, indent=2),
                file_name=f"graph_{selected_subject_code}_{year}.json",
                mime="application/json",
            )
