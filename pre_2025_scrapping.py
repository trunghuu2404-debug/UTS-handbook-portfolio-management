import os
import time
import json
from urllib.parse import urljoin
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from bs4 import BeautifulSoup


# setup selenium
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)

BASE_URL = "https://coursehandbook.uts.edu.au"


# Find requisite
def extract_section_data(header_text):
    soup = BeautifulSoup(driver.page_source, "html.parser")

    table = None

    # Strategy 1: Find <h3> (used for Requisites and Anti-requisites)
    header = soup.find("h3", string=lambda t: t and header_text in t)
    if header:
        table = header.find_next("table")

    # Strategy 2: Find text inside a <strong> tag within a table (used for Other Requisite)
    if not table:
        strong_tag = soup.find("strong", string=lambda t: t and header_text in t)
        if strong_tag:
            table = strong_tag.find_parent("table")

    if not table:
        return None

    section_data = {"rule": "", "items": []}

    # Identify the Rule or Header row (colspan row)
    rule_cell = table.find("td", colspan=True)
    if rule_cell:
        section_data["rule"] = rule_cell.get_text(strip=True)

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")

        # 1. Skip if it's the rule cell we already captured
        if rule_cell in cells:
            continue

        # 2. Skip the table header row (Item | Type | Details)
        if row.find("th"):
            continue

        # 3. Scenario A: Standard subject-code/admission rows (2 or 3 columns)
        # We ensure it's not a colspan row to avoid capturing notes here
        if len(cells) >= 2 and not row.find("td", colspan=True):
            item_entry = {
                "item_id": cells[0].get_text(strip=True),
                "details": cells[-1].get_text(strip=True),
            }
            # Catch 'Type' column if it exists (index 1)
            if len(cells) == 3:
                item_entry["type"] = cells[1].get_text(strip=True)

            section_data["items"].append(item_entry)

        # 4. Scenario B: "Other Requisite" style row or extra instructions
        elif len(cells) == 1 or row.find("td", colspan=True):
            text_content = row.get_text(strip=True)
            # Make sure we aren't just re-adding the 'Other requisite' label
            if text_content and text_content.lower() != header_text.lower():
                section_data["items"].append({"note": text_content})

    return section_data if (section_data["items"] or section_data["rule"]) else None


def scrape_subject(url, code, name, cp):
    print(f"   → Visiting subject: {url}")
    driver.get(url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    data = {
        "code": code,
        "name": name,
        "credit_points": cp,
        "type": "Subject",
        "url": url,
        "faculty": "No faculty information",
        "study_level": "No study level available",
        "result_type": "No result type available",
        "total_workload_hours": "No workload information",
        "leanring_outcomes": "No learning outcomes available",
        "learning_and_teaching_activities": "No activities available",
        "description": "No description available",
    }

    content_div = soup.find("div", id="content")
    if not content_div:
        return data

    # 1. Extract Total Workload Hours (Main Page)
    all_em_tags = content_div.find_all("em")
    workload_info = "No workload information"
    for em in all_em_tags[1:]:
        text = em.get_text(strip=True).lower()
        if any(
            key in text
            for key in ["hpw", "weeks", "attendance", "tutorial", "lecture", "block"]
        ):
            workload_info = em.get_text(strip=True)
            break
        if "requisite" in text:
            break
    data["total_workload_hours"] = workload_info

    # 2. Extract Requisites from "Access conditions" (Main Page)
    # Target the <h4> link specifically as requested
    access_link_header = content_div.find("h4")
    access_link = None
    if access_link_header:
        access_link = access_link_header.find(
            "a", href=lambda h: h and "subjectcode=" in h
        )

    # Fallback search if not in h4
    if not access_link:
        access_link = content_div.find(
            "a", string=lambda t: t and "Access conditions" in t
        )

    if access_link:
        access_url = access_link["href"]
        driver.get(access_url)
        time.sleep(2)

        requisite_info = {}
        anti = extract_section_data("Anti-requisite(s)")
        reqs = extract_section_data("Requisite(s)")
        other = extract_section_data("Other requisite")

        if anti:
            requisite_info["anti_requisite"] = anti
        if reqs:
            requisite_info["requisite"] = reqs
        if other:
            requisite_info["other_requisite"] = other

        if requisite_info:
            data["requisite_list"] = requisite_info

        # Return to main page to continue
        driver.back()
        time.sleep(1)
        # Refresh soup after coming back
        soup = BeautifulSoup(driver.page_source, "html.parser")
        content_div = soup.find("div", id="content")

    # 3. Navigate to "Detailed subject description" for outcomes and activities
    detailed_link_tag = content_div.find(
        "a", string=lambda t: t and "Detailed subject description" in t
    )

    if detailed_link_tag:
        detailed_url = urljoin(url, detailed_link_tag["href"])
        driver.get(detailed_url)
        time.sleep(2)
        detailed_soup = BeautifulSoup(driver.page_source, "html.parser")

        # Faculty info (Detailed page)
        faculty_tag = detailed_soup.find("em", string=re.compile(r"^UTS:", re.I))
        if faculty_tag:
            data["faculty"] = faculty_tag.get_text(strip=True)

        # Description
        desc_header = detailed_soup.find(
            "h3", string=lambda t: t and "Description" in t
        )
        if desc_header:
            desc_paragraphs = []
            curr = desc_header.find_next()
            while curr and curr.name != "h3":
                if curr.name == "p":
                    desc_paragraphs.append(curr.get_text(strip=True))
                curr = curr.find_next_sibling()
            data["description"] = (
                " ".join(desc_paragraphs) if desc_paragraphs else data["description"]
            )

        # Learning Outcomes
        slo_table = detailed_soup.find("table", class_="SLOTable")
        if slo_table:
            outcomes = [
                td.get_text(strip=True)
                for td in slo_table.find_all("td")
                if td.get_text(strip=True)
            ]
            data["leanring_outcomes"] = (
                outcomes if outcomes else data["leanring_outcomes"]
            )

        # Teaching and Learning Strategies
        teaching_header = detailed_soup.find(
            "h3", string=lambda t: t and "Teaching and learning strategies" in t
        )
        if teaching_header:
            strat_paragraphs = []
            curr = teaching_header.find_next()
            while curr and curr.name != "h3":
                if curr.name == "p":
                    strat_paragraphs.append(curr.get_text(strip=True))
                curr = curr.find_next_sibling()
            data["learning_and_teaching_activities"] = (
                "\n".join(strat_paragraphs)
                if strat_paragraphs
                else data["learning_and_teaching_activities"]
            )

        # Attributes
        for em in detailed_soup.find_all("em"):
            if "result type" in em.get_text(strip=True).lower():
                data["result_type"] = (
                    em.next_sibling.strip(": ")
                    if em.next_sibling
                    else data["result_type"]
                )

        level_p = detailed_soup.find("p", string=lambda t: t and "Subject level" in t)
        if level_p:
            next_p = level_p.find_next("p")
            if next_p:
                data["study_level"] = next_p.get_text(strip=True)

    return data


# function to find if the item is subject or area of study based on the code (used in scrape_aos)
def get_item_type(code):
    if code.startswith("STM"):
        return "Stream"
    if code.startswith("CBK"):
        return "Choice Block"
    if code.startswith("MAJ"):
        return "Major"
    if code.startswith("SMJ"):
        return "Sub-Major"
    return "Subject"


# Scrape aos (Stand for Area of Study: Major, Sub-major and Choiceblock))
def scrape_aos(url, code, name, cp):
    current_page_url = driver.current_url
    print(f"   → Visiting Area of Study detail: {url}")
    driver.get(url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    group_data = {
        "code": code,
        "name": name,
        "credit_points": cp,
        "type": get_item_type(code),
        "url": url,
        "description": "No description available",
        "have_structure": [],
    }

    content_div = soup.find("div", id="content")
    if content_div:
        # Extract description paragraphs
        desc_paragraphs = [
            p.get_text(strip=True)
            for p in content_div.find_all("p", recursive=False)
            if p.get_text(strip=True)
        ]
        if desc_paragraphs:
            group_data["description"] = "\n\n".join(desc_paragraphs)

        # Parse the internal table
        structure_node = scrape_structure(url, code=code, name=name, cp=cp)

        # --- SMART UNWRAPPING LOGIC ---
        # If the node only acts as a wrapper for sub-structures (Streams or chunked blocks)
        # and has no direct items of its own, we promote the sub_structures to avoid double-nesting.
        has_direct_items = (
            "has_subject" in structure_node or "has_area_of_study" in structure_node
        )
        has_subs = "have_sub_structures" in structure_node

        if has_subs and not has_direct_items:
            # 1. Rescue CP if the wrapper found it but we didn't have it
            if structure_node.get("structure_cp") and not group_data.get(
                "credit_points"
            ):
                group_data["credit_points"] = structure_node["structure_cp"]

            # 2. Rescue the selection rule (e.g., "Select 24 credit points of options: 24cp")
            if structure_node.get("structure_details"):
                rule_text = structure_node["structure_details"]
                if group_data["description"] == "No description available":
                    group_data["description"] = rule_text
                else:
                    group_data["description"] += f"\n\nRule: {rule_text}"

            # 3. Promote the inner streams/blocks directly to the AOS level
            group_data["have_structure"].extend(structure_node["have_sub_structures"])
        else:
            # Keep it as-is if it contains direct subjects
            if structure_node:
                group_data["have_structure"].append(structure_node)

    driver.get(current_page_url)
    time.sleep(1)
    return group_data


# Scrape structure (The Recursive Tree)
def scrape_structure(url, code, name, cp):
    print(f"   → Analyzing Structure: {url} | {code}, {name}")
    driver.get(url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    current_node = {
        "structure_name": name,
        "structure_code": code,
        "structure_cp": cp,
        "structure_details": "",
    }

    content_div = soup.find("div", id="content")
    table = content_div.find("table") if content_div else None
    if not table:
        return current_node

    rows = table.find_all("tr")

    # Phase 1: Sequential Extraction & Chunking
    blocks = []
    current_block = {"name": "Compulsory", "cp": "", "items": []}

    for i, row in enumerate(rows):
        cells = row.find_all("td")
        if not cells:
            continue

        row_text = row.get_text(strip=True)
        link_tag = row.find("a")

        is_rule = (
            "select" in row_text.lower()
            and "credit points" in row_text.lower()
            and not link_tag
        )

        if is_rule:
            rule_cp = cells[-1].get_text(strip=True) if len(cells) > 1 else ""
            if i == 0:
                current_node["structure_details"] = row_text
                if rule_cp:
                    current_node["structure_cp"] = rule_cp
                current_block["name"] = row_text
                current_block["cp"] = rule_cp
            else:
                if current_block["items"]:
                    blocks.append(current_block)
                current_block = {"name": row_text, "cp": rule_cp, "items": []}
            continue

        if "total" in row_text.lower() and len(cells) < 3:
            continue

        if link_tag:
            item_code = link_tag.get_text(strip=True)
            full_cell_text = cells[0].get_text(strip=True)
            item_name = full_cell_text.replace(item_code, "").strip()
            item_url = urljoin(url, link_tag["href"])
            item_type = get_item_type(item_code)
            item_cp = cells[-1].get_text(strip=True) if len(cells) > 1 else ""

            if item_code in visited_subjects:
                print(f"      Using cached data for {item_code}")
                item_obj = visited_subjects[
                    item_code
                ].copy()  # Shallow copy to avoid mutating cached structures
            else:
                # --- THE FIX: Treat STM as a direct Structure, not an AOS ---
                if item_type == "Subject":
                    item_obj = scrape_subject(item_url, item_code, item_name, item_cp)
                elif item_type == "Stream":
                    # Call scrape_structure recursively for Streams
                    item_obj = scrape_structure(item_url, item_code, item_name, item_cp)
                    item_obj["type"] = (
                        "Stream"  # Temporary marker for the sorting phase
                    )
                else:
                    item_obj = scrape_aos(item_url, item_code, item_name, item_cp)

                visited_subjects[item_code] = item_obj

            current_block["items"].append(item_obj)

    if current_block["items"]:
        blocks.append(current_block)

    # Phase 2: Smart Assembly (Handling Streams as sub-structures)
    if len(blocks) == 1:
        block = blocks[0]
        subjects = [i for i in block["items"] if i.get("type") == "Subject"]
        aos = [
            i
            for i in block["items"]
            if i.get("type") in ("Choice Block", "Major", "Sub-Major")
        ]
        streams = [i for i in block["items"] if i.get("type") == "Stream"]

        types_present_for_aos = set([i.get("type") for i in aos])

        if block["name"] == "Compulsory" and len(types_present_for_aos) > 1:
            current_node["have_sub_structures"] = []
            if subjects:
                current_node["have_sub_structures"].append(
                    {
                        "structure_name": "Core Subjects",
                        "structure_cp": "",
                        "has_subject": subjects,
                    }
                )
            for t in sorted(list(types_present_for_aos)):
                t_items = [i for i in aos if i.get("type") == t]
                current_node["have_sub_structures"].append(
                    {
                        "structure_name": f"{t}s",
                        "structure_cp": "",
                        "has_area_of_study": t_items,
                    }
                )
        else:
            if subjects:
                current_node["has_subject"] = subjects
            if aos:
                current_node["has_area_of_study"] = aos

        # Add Streams directly to have_sub_structures
        if streams:
            if "have_sub_structures" not in current_node:
                current_node["have_sub_structures"] = []
            for s in streams:
                s.pop("type", None)  # Remove the temporary marker before JSON output
                current_node["have_sub_structures"].append(s)

    else:
        current_node["have_sub_structures"] = []
        for block in blocks:
            sub_node = {"structure_name": block["name"], "structure_cp": block["cp"]}
            subjects = [i for i in block["items"] if i.get("type") == "Subject"]
            aos = [
                i
                for i in block["items"]
                if i.get("type") in ("Choice Block", "Major", "Sub-Major")
            ]
            streams = [i for i in block["items"] if i.get("type") == "Stream"]

            if subjects:
                sub_node["has_subject"] = subjects
            if aos:
                sub_node["has_area_of_study"] = aos

            # If the block contains a Stream, nest it inside this block's sub-structures
            if streams:
                sub_node["have_sub_structures"] = []
                for s in streams:
                    s.pop("type", None)  # Remove the temporary marker
                    sub_node["have_sub_structures"].append(s)

            current_node["have_sub_structures"].append(sub_node)

    return current_node


def scrape_course(course_url):
    print(f"Scraping legacy course page: {course_url}")
    driver.get(course_url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # 1. Course Metadata Extraction
    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True)
        # Separates code (e.g. C10474v1) from the name
        parts = h1_text.split(" ", 1)
        raw_code = parts[0] if len(parts) > 0 else "Unknown"

        # Strip the version suffix (e.g., "C10474v1" -> "C10474", "C10474v2" -> "C10474")
        course_code = re.sub(r"v\d+$", "", raw_code, flags=re.IGNORECASE)

        course_name = parts[1] if len(parts) > 1 else "Unknown"
    else:
        course_code, course_name = "Unknown", "Unknown"

    # 2. Overview Extraction
    overview_header = soup.find("h2", string=lambda t: t and "Overview" in t)
    course_details = "No details available"
    if overview_header:
        paragraphs = []
        curr = overview_header.find_next_sibling()
        while curr and curr.name == "p":
            paragraphs.append(curr.get_text(strip=True))
            curr = curr.find_next_sibling()
        if paragraphs:
            course_details = " ".join(paragraphs)

    # 3. Learning Outcomes Extraction
    cilo_header = soup.find(
        "h2", string=lambda t: t and "Course intended learning outcomes" in t
    )
    course_learning_outcomes = []
    if cilo_header:
        cilo_table = cilo_header.find_next("table")
        if cilo_table:
            for row in cilo_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    course_learning_outcomes.append(cells[1].get_text(strip=True))

    course_data = {
        "course_code": course_code,
        "course_name": course_name,
        "course_details": course_details,
        "course_leanring_outcomes": (
            course_learning_outcomes
            if course_learning_outcomes
            else "No learning outcomes available"
        ),
        "course_url": course_url,
        "structure": [],
    }

    # 4. Structure Extraction (Row-by-Row Title/CP Capture)
    # We find the table directly under the "Course completion requirements" header
    req_header = soup.find(
        "h2", string=lambda t: t and "Course completion requirements" in t
    )
    if req_header:
        req_table = req_header.find_next("table")
        if req_table:
            for row in req_table.find_all("tr"):
                link = row.find("a")
                cells = row.find_all("td")

                # Skip the "Total" row or rows without links
                if not link or "total" in row.get_text(strip=True).lower():
                    continue

                # Extract code to clean the title
                code = link.get_text(strip=True)
                # Extract full text from the cell and remove the code prefix to get the clean title
                # e.g., "STM90651 Core subjects (Information Technology)" -> "Core subjects (Information Technology)"
                full_cell_text = cells[0].get_text(strip=True)
                clean_title = full_cell_text.replace(code, "").strip()

                # Capture the credit points from the last cell (e.g., 48cp)
                cp_val = cells[-1].get_text(strip=True) if len(cells) > 1 else ""

                target_url = urljoin(course_url, link["href"])

                # Pass the semantic name and CP into the structure scraper
                course_data["structure"].append(
                    scrape_structure(target_url, code=code, name=clean_title, cp=cp_val)
                )

    return course_data


visited_subjects = {}

if __name__ == "__main__":
    # Ask user for the URL
    target_url = input("Enter the UTS Course Handbook URL to scrape: ").strip()

    # Extract Metadata (Year) using Regex to handle "2023_1", "2022_2", etc.
    # It looks for a 4-digit number, optionally followed by an underscore and number.
    year_match = re.search(r"/(\d{4})(?:_\d+)?/", target_url)
    if year_match:
        year = year_match.group(1)  # Extracts just the '2023' part
    else:
        print("Could not detect year in URL. Defaulting to 'archive'.")
        year = "archive"

    # 3. Setup Subject Archive Paths & Load Cache
    archive_dir = os.path.join("dataset", "subjects_archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    master_list_path = os.path.join(archive_dir, f"{year}_subjects.json")

    # Load existing subjects for this year if they exist
    if os.path.exists(master_list_path):
        with open(master_list_path, "r", encoding="utf-8") as f:
            visited_subjects = json.load(f)
        print(f"Loaded {len(visited_subjects)} subjects from {year} archive.")
    else:
        visited_subjects = {}
        print(f"No existing archive for {year}. Starting fresh.")

    # 4. Run the scraper
    final_data = scrape_course(target_url)

    # 5. Create Directory Structure using SCRAPED data
    safe_course_name = "".join(
        [c for c in final_data["course_name"] if c.isalnum() or c in (" ", "_")]
    ).strip()

    course_code = final_data["course_code"]
    course_folder_name = f"{course_code}_{safe_course_name}"

    # Build paths for the Course Tree
    base_dir = "dataset"
    course_path = os.path.join(base_dir, course_folder_name)

    if not os.path.exists(course_path):
        os.makedirs(course_path, exist_ok=True)
        print(f"Created folder: {course_path}")

    # 6. Save the Course Tree JSON (Year-based)
    filename = f"{year}.json"
    full_save_path = os.path.join(course_path, filename)

    with open(full_save_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)

    # 7. Save the UPDATED Subject Archive for that year
    with open(master_list_path, "w", encoding="utf-8") as f:
        json.dump(visited_subjects, f, indent=4, ensure_ascii=False)

    print(f"\n--- SUCCESS ---")
    print(f"📁 Course Tree: {full_save_path}")
    print(f"📁 Subject Archive: {master_list_path}")

    driver.quit()
