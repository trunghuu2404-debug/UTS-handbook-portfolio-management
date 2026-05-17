"""
frontend/app.py
---------------
Streamlit testing frontend for the UTS Curriculum Digital Twin API.

Run:
    streamlit run app.py

Ensure the FastAPI backend is running at API_BASE_URL before starting.
"""

import json
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

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
# API helpers
# ---------------------------------------------------------------------------


def api_get(path: str, params: dict = None):
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
            f"Cannot connect to **{API_BASE_URL}**. Is the FastAPI backend running?"
        )
        return None
    except requests.exceptions.HTTPError as exc:
        st.error(f"API error {exc.response.status_code}: {exc.response.text}")
        return None
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
        return None


def api_get_silent(path: str, params: dict = None):
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=3)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


def show_viz(path: str, height: int = 900, params: dict = None) -> None:
    """Fetch an HTML viz from the API and embed it inline."""
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=30)
        if resp.status_code == 200:
            components.html(resp.text, height=height, scrolling=True)
        else:
            st.warning(f"Visualization not available ({resp.status_code}): {path}")
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to **{API_BASE_URL}**.")
    except Exception as exc:
        st.error(f"Failed to load visualization: {exc}")


# ---------------------------------------------------------------------------
# Local-JSON fallbacks for sidebar
# ---------------------------------------------------------------------------

_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


@st.cache_data(show_spinner=False)
def _local_courses() -> list:
    out = []
    if not _DATASET_DIR.exists():
        return out
    for d in sorted(_DATASET_DIR.iterdir()):
        if not d.is_dir() or not d.name.startswith("C"):
            continue
        year_jsons = sorted(d.glob("*.json"))
        if not year_jsons:
            continue
        try:
            data = json.loads(year_jsons[-1].read_text(encoding="utf-8"))
            out.append({"code": data["course_code"], "name": data["course_name"]})
        except Exception:
            pass
    return out


@st.cache_data(show_spinner=False)
def _local_course_versions(course_code: str) -> list:
    out = []
    for d in _DATASET_DIR.iterdir():
        if d.is_dir() and d.name.startswith(course_code):
            for jp in sorted(d.glob("*.json")):
                if jp.stem.isdigit():
                    out.append({"year": int(jp.stem)})
            break
    return sorted(out, key=lambda v: v["year"], reverse=True)


@st.cache_data(show_spinner=False)
def _local_subject_search(query: str, year: int = 2026) -> list:
    if not query or len(query) < 2:
        return []
    sub_path = _DATASET_DIR / "subjects_archive" / f"{year}_subjects.json"
    if not sub_path.exists():
        return []
    try:
        subs = json.loads(sub_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    q = query.lower()
    out = []
    for code, sub in subs.items():
        name = sub.get("name", "")
        if q in code.lower() or q in name.lower():
            out.append({"code": code, "name": name})
        if len(out) >= 50:
            break
    return out


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🎓 UTS Digital Twin")
    st.markdown("---")

    st.subheader("Course")
    courses_data = api_get_silent("/courses")
    if not courses_data:
        courses_data = _local_courses()
        if courses_data:
            st.caption("📂 Using local data (backend offline)")
    course_options = {}
    if courses_data:
        course_options = {f"{c['name']} ({c['code']})": c["code"] for c in courses_data}

    selected_course_label = st.selectbox(
        "Select course", options=list(course_options.keys()), key="course_select"
    )
    selected_course_code = course_options.get(selected_course_label)

    selected_year = None
    if selected_course_code:
        versions_data = api_get_silent(f"/courses/{selected_course_code}/versions")
        if not versions_data:
            versions_data = _local_course_versions(selected_course_code)
        if versions_data:
            year_options = ["All versions"] + [str(v["year"]) for v in versions_data]
            selected_year_str = st.selectbox(
                "Version (year)", year_options, key="year_select"
            )
            selected_year = (
                int(selected_year_str) if selected_year_str != "All versions" else None
            )

    st.markdown("---")

    st.subheader("Subject")
    subject_search = st.text_input(
        "Search by code or name",
        placeholder="e.g. 31265 or Communication",
        key="subj_search",
    )
    subject_options = {}
    if subject_search and len(subject_search) >= 2:
        search_data = api_get_silent("/subjects/search", params={"q": subject_search})
        if not search_data:
            search_data = _local_subject_search(subject_search)
        if search_data:
            subject_options = {
                f"{s['name']} ({s['code']})": s["code"] for s in search_data
            }

    selected_subject_label = st.selectbox(
        "Select subject", options=list(subject_options.keys()), key="subject_select"
    )
    selected_subject_code = subject_options.get(selected_subject_label)

    selected_subject_year = st.number_input(
        "Subject version year",
        min_value=2023,
        max_value=2026,
        value=2026,
        step=1,
        key="subj_year",
    )

    st.markdown("---")
    st.caption(f"FastAPI backend: {API_BASE_URL}")


# ---------------------------------------------------------------------------
# Main — 4 flat sections
# ---------------------------------------------------------------------------

st.title("UTS Curriculum Digital Twin")
st.markdown("Explore course structures and subject requisites stored in Neo4j.")

sec_course, sec_subject, sec_twin, sec_similarity = st.tabs(
    [
        "Course Structure",
        "Subject Details",
        "Subject Twin",
        "Subject Similarity",
    ]
)


# ===========================================================================
# SECTION 1 — Course Structure
# Course overview metrics · Sunburst · D3 Tree
# ===========================================================================

with sec_course:
    st.header("Course Structure")

    if not selected_course_code:
        st.info("Select a course in the sidebar to begin.")
    else:
        year_label = str(selected_year) if selected_year else "all versions"
        viz_year = selected_year or 2026

        # ── Overview metrics ─────────────────────────────────────────────────
        st.subheader(f"Overview · {selected_course_label} · {year_label}")
        with st.spinner("Loading course graph …"):
            params = {"year": selected_year} if selected_year else {}
            graph_data = api_get(
                f"/courses/{selected_course_code}/graph", params=params
            )

        if graph_data:
            nodes = graph_data.get("nodes", [])
            links = graph_data.get("links", [])
            type_counts = {}
            for n in nodes:
                t = n.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total nodes", len(nodes))
            col2.metric("Total relationships", len(links))
            col3.metric("Structures", type_counts.get("Structure", 0))
            col4.metric("Subjects", type_counts.get("Subject", 0))

            node_types = sorted(set(n["type"] for n in nodes))
            selected_type = st.selectbox(
                "Filter by type", ["All"] + node_types, key="node_type_filter"
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

        if selected_year:
            with st.spinner("Loading version metadata …"):
                versions = api_get(f"/courses/{selected_course_code}/versions")
            if versions:
                version = next(
                    (v for v in versions if v["year"] == selected_year), None
                )
                if version:
                    st.markdown(f"**URL:** {version.get('course_url') or '—'}")
                    if version.get("course_details"):
                        with st.expander("Course details"):
                            st.write(version["course_details"])
                    clo = version.get("course_learning_outcomes") or []
                    if clo:
                        with st.expander(f"Learning outcomes ({len(clo)})"):
                            for i, lo in enumerate(clo, 1):
                                st.markdown(f"{i}. {lo}")

        st.divider()

        # ── Sunburst ──────────────────────────────────────────────────────────
        st.subheader(f"Sunburst · {selected_course_label} · {viz_year}")
        st.caption("Click any wedge to zoom in. Grey = no subject data in that branch.")
        with st.spinner("Building sunburst …"):
            show_viz(
                f"/viz/course/{selected_course_code}/{viz_year}/sunburst", height=900
            )

        st.divider()

        # ── D3 Tree ───────────────────────────────────────────────────────────
        st.subheader(f"Course Tree (D3) · {selected_course_label} · {viz_year}")
        st.caption(
            "Top-down hierarchy. Click blue/purple nodes to expand. Scroll to zoom."
        )
        with st.spinner("Building course tree …"):
            show_viz(f"/viz/course/{selected_course_code}/{viz_year}/tree", height=900)


# ===========================================================================
# SECTION 2 — Subject Details
# Details · Requisites · Requisite Graph · Evolution · Prereq Tree
# ===========================================================================

with sec_subject:
    st.header("Subject Details")

    if not selected_subject_code:
        st.info("Search for a subject in the sidebar, then select it.")
    else:
        year = int(selected_subject_year)

        # ── Subject metadata ──────────────────────────────────────────────────
        with st.spinner(f"Loading subject {selected_subject_code} …"):
            detail = api_get(f"/subjects/{selected_subject_code}")

        if detail:
            st.subheader(f"{detail['name']}  ·  `{detail['code']}`")
            versions = detail.get("versions", [])
            st.caption(f"{len(versions)} version(s) in database")

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

                m1, m2 = st.columns(2)
                with m1:
                    st.markdown(f"**Type:** {chosen_version.get('type') or '—'}")
                    st.markdown(
                        f"**Study level:** {chosen_version.get('study_level') or '—'}"
                    )
                    st.markdown(
                        f"**Result type:** {chosen_version.get('result_type') or '—'}"
                    )
                with m2:
                    url = chosen_version.get("url")
                    if url:
                        st.markdown(f"**URL:** [{url}]({url})")

                if chosen_version.get("description"):
                    with st.expander("Description", expanded=True):
                        st.write(chosen_version["description"])
                lo = chosen_version.get("learning_outcomes") or []
                if lo:
                    with st.expander(f"Learning outcomes ({len(lo)})", expanded=True):
                        for i, outcome in enumerate(lo, 1):
                            st.markdown(f"{i}. {outcome}")
                if chosen_version.get("teaching_and_learning_activities"):
                    with st.expander("Teaching & learning activities"):
                        st.write(chosen_version["teaching_and_learning_activities"])
                if chosen_version.get("requisite_rule") or chosen_version.get(
                    "anti_requisite_rule"
                ):
                    with st.expander("Requisite rules"):
                        if chosen_version.get("requisite_rule"):
                            st.markdown(
                                f"**Prerequisite rule:** `{chosen_version['requisite_rule']}`"
                            )
                        if chosen_version.get("anti_requisite_rule"):
                            st.markdown(
                                f"**Anti-requisite rule:** `{chosen_version['anti_requisite_rule']}`"
                            )

            with st.expander("All versions summary", expanded=False):
                for v in versions:
                    st.markdown(
                        f"**{v['year']}** — {v.get('faculty') or '—'} · "
                        f"{v.get('credit_points') or '—'} CP · {v.get('study_level') or '—'}"
                    )

        st.divider()

        # ── Requisites ────────────────────────────────────────────────────────
        st.subheader(f"Requisites · {selected_subject_code} · {year}")
        with st.spinner("Loading requisites …"):
            reqs = api_get(
                f"/subjects/{selected_subject_code}/version/{year}/requisites"
            )

        if reqs:
            if reqs.get("requisite_rule"):
                st.info(f"**Prerequisite rule:** {reqs['requisite_rule']}")
            if reqs.get("anti_requisite_rule"):
                st.warning(f"**Anti-requisite rule:** {reqs['anti_requisite_rule']}")

            col_pre, col_anti = st.columns(2)
            with col_pre:
                prereqs = reqs.get("prerequisites", [])
                st.markdown(f"**Prerequisites ({len(prereqs)})**")
                for p in prereqs:
                    with st.container(border=True):
                        st.markdown(f"**{p['name']}**  `{p['code']}`")
                        st.caption(
                            f"Item `{p['item_id']}` · {p.get('item_type') or 'Academic'} · Year {p['year']}"
                        )
                if not prereqs:
                    st.caption("None")

            with col_anti:
                antis = reqs.get("anti_requisites", [])
                st.markdown(f"**Anti-requisites ({len(antis)})**")
                for a in antis:
                    with st.container(border=True):
                        st.markdown(f"**{a['name']}**  `{a['code']}`")
                        st.caption(f"Item `{a['item_id']}` · Year {a['year']}")
                if not antis:
                    st.caption("None")

            col_adm, col_other = st.columns(2)
            with col_adm:
                adms = reqs.get("admission_requisites", [])
                st.markdown(f"**Admission requisites ({len(adms)})**")
                for adm in adms:
                    with st.container(border=True):
                        st.markdown(adm.get("detail") or "—")
                        st.caption(
                            f"Item `{adm['item_id']}` · {adm.get('item_type') or '—'}"
                        )
                if not adms:
                    st.caption("None")

            with col_other:
                others = reqs.get("other_requisites", [])
                st.markdown(f"**Other requisites ({len(others)})**")
                for o in others:
                    with st.container(border=True):
                        st.markdown(f"**{o.get('note') or '—'}**")
                        st.caption(o.get("rule") or "")
                if not others:
                    st.caption("None")

        st.divider()

        # ── Requisite Graph ───────────────────────────────────────────────────
        st.subheader(f"Requisite Graph · {selected_subject_code} · {year}")
        st.caption(
            "Click any subject node to expand its prerequisites. "
            "Green = prerequisite, red dashed = anti-requisite, "
            "orange diamond = admission requisite, grey square = other requisite."
        )
        with st.spinner("Building requisite graph …"):
            show_viz(
                f"/viz/subject/{selected_subject_code}/{year}/prereq-graph",
                height=700,
            )

        st.divider()

        # ── Evolution ─────────────────────────────────────────────────────────
        st.subheader(f"Subject Evolution · {selected_subject_code}")
        st.caption("How this subject changed across 2023–2026: metrics + text diff.")
        with st.spinner("Building evolution timeline …"):
            show_viz(f"/viz/subject/{selected_subject_code}/evolution", height=1200)


# ===========================================================================
# SECTION 3 — Subject Twin
# Similarity network · Shared subjects
# ===========================================================================

with sec_twin:
    st.header("Subject Twin")

    # ── Subject Twins (similarity network) ───────────────────────────────────
    st.subheader("Subject Twins & Siblings")
    st.markdown(
        "Network of subjects whose descriptions and learning outcomes are textually similar "
        "(cosine similarity ≥ 0.70). Node colour = faculty. Tight clusters = twins across programs."
    )
    twins_year = st.radio(
        "Year", ["2026", "2025", "2024", "2023"], horizontal=True, key="twins_year"
    )
    with st.spinner(f"Loading similarity network for {twins_year} …"):
        show_viz(f"/viz/similarity/{twins_year}", height=950)

    st.divider()

    # ── Shared Subjects ───────────────────────────────────────────────────────
    st.subheader("Subjects Shared Across Programs")
    st.markdown(
        "Bipartite graph: coloured nodes = programs, small nodes = subjects. "
        "Gold = appears in 2+ programs."
    )
    shared_year = st.radio(
        "Year", ["2026", "2025", "2024", "2023"], horizontal=True, key="shared_year"
    )
    with st.spinner(f"Loading shared subjects for {shared_year} …"):
        show_viz(f"/viz/shared-subjects/{shared_year}", height=950)


# ===========================================================================
# SECTION 4 — Subject Similarity
# TF-IDF pairwise comparison + top-N
# ===========================================================================

with sec_similarity:
    st.header("Subject Similarity")
    st.markdown(
        "Compare two subjects using TF-IDF vectorisation and cosine similarity."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Subject 1")
        subject_code_1 = st.text_input("Subject 1 code", value="41040")
        year_1 = st.number_input(
            "Subject 1 year",
            min_value=2023,
            max_value=2026,
            value=2026,
            step=1,
            key="similarity_year_1",
        )
    with col_b:
        st.subheader("Subject 2")
        subject_code_2 = st.text_input("Subject 2 code", value="42172")
        year_2 = st.number_input(
            "Subject 2 year",
            min_value=2023,
            max_value=2026,
            value=2026,
            step=1,
            key="similarity_year_2",
        )

    if st.button("Compare subjects", type="primary"):
        with st.spinner("Calculating similarity …"):
            result = api_get(
                "/similarity/compare",
                params={
                    "subject_code_1": subject_code_1.strip(),
                    "subject_code_2": subject_code_2.strip(),
                    "year_1": str(year_1),
                    "year_2": str(year_2),
                },
            )

        if result:
            s1 = result["subject_1"]
            s2 = result["subject_2"]
            pct = result["similarity_percentage"]
            score = result["similarity_score"]

            st.divider()
            left, mid, right = st.columns([2, 1, 2])
            with left:
                st.markdown(f"### {s1['name']}")
                st.caption(f"{s1['code']} · {s1['year']}")
                st.markdown(f"**Faculty:** {s1.get('faculty') or '—'}")
                st.markdown(f"**Study level:** {s1.get('study_level') or '—'}")
                st.markdown(f"**Credit points:** {s1.get('credit_points') or '—'}")
            with mid:
                st.metric("Similarity", f"{pct}%")
                st.progress(score)
            with right:
                st.markdown(f"### {s2['name']}")
                st.caption(f"{s2['code']} · {s2['year']}")
                st.markdown(f"**Faculty:** {s2.get('faculty') or '—'}")
                st.markdown(f"**Study level:** {s2.get('study_level') or '—'}")
                st.markdown(f"**Credit points:** {s2.get('credit_points') or '—'}")

            diagram_html = f"""
            <div style="background:#0e1117;color:#fafafa;display:flex;align-items:center;
                        justify-content:space-between;gap:24px;padding:24px;font-family:Arial,sans-serif;">
              <div style="flex:1;padding:22px;border:1px solid #4b5563;border-radius:14px;
                          text-align:center;background:#111827;">
                <h2 style="margin:0 0 10px 0;">{s1['code']}</h2>
                <p style="margin:0 0 8px 0;color:#e5e7eb;">{s1['name']}</p>
                <small style="color:#9ca3af;">{s1['year']}</small>
              </div>
              <div style="flex:1;text-align:center;">
                <div style="font-size:32px;font-weight:bold;">{pct}%</div>
                <div style="margin:12px 0;font-size:22px;color:#60a5fa;">──────────────▶</div>
                <div style="font-size:13px;color:#d1d5db;">TF-IDF + Cosine Similarity</div>
              </div>
              <div style="flex:1;padding:22px;border:1px solid #4b5563;border-radius:14px;
                          text-align:center;background:#111827;">
                <h2 style="margin:0 0 10px 0;">{s2['code']}</h2>
                <p style="margin:0 0 8px 0;color:#e5e7eb;">{s2['name']}</p>
                <small style="color:#9ca3af;">{s2['year']}</small>
              </div>
            </div>
            """
            components.html(diagram_html, height=220)

            st.divider()
            st.subheader("Field-level similarity")
            for key, label in {
                "description": "Description",
                "learning_outcomes": "Learning outcomes",
                "learning_activities": "Learning and teaching activities",
            }.items():
                field = result.get("field_scores", {}).get(key)
                if field:
                    st.markdown(f"**{label}** — {field['percentage']}%")
                    st.progress(field["score"])
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**{s1['code']}**")
                        st.write(s1.get(key) or "No data.")
                    with c2:
                        st.markdown(f"**{s2['code']}**")
                        st.write(s2.get(key) or "No data.")
                    st.markdown("")

            st.divider()
            st.success(result["classification"])
            st.caption(f"Method: {result['method']}")

            st.divider()
            st.subheader("Top 5 similar subjects")
            top_result = api_get(
                "/similarity/top",
                params={
                    "subject_code": subject_code_1.strip(),
                    "year": str(year_1),
                    "limit": 5,
                },
            )
            if top_result:
                for match in top_result.get("top_matches", []):
                    with st.container(border=True):
                        st.markdown(
                            f"**{match['name']}**  `{match['code']}` · {match['year']}"
                        )
                        st.metric("Similarity", f"{match['similarity_percentage']}%")
                        st.caption(match["classification"])
                        st.progress(match["similarity_score"])

            with st.expander("Raw API response"):
                st.json(result)
