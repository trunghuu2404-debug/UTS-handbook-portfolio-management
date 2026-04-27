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


# scrape learning outcomes
def extract_learning_outcomes(soup):
    learning_outcomes_list = []

    # 1. Find the main container for Learning Outcomes
    # We target the data-menu-id to ensure we are in the right section of the page
    main_container = soup.find("div", {"data-menu-id": "Learningoutcomes"})

    if main_container:
        # 2. Find all accordion items within this section
        items = main_container.find_all(
            "div", class_=lambda x: x and "AccordionItem" in x
        )

        for item in items:
            # 3. Find the text within the 'clamp' div or the <p> tag
            outcome_text_tag = item.find("div", class_=lambda x: x and "clamp" in x)

            if outcome_text_tag:
                # Clean the text to remove extra whitespace/newlines
                text = outcome_text_tag.get_text(strip=True)
                if text:
                    learning_outcomes_list.append(text)

    return (
        learning_outcomes_list
        if learning_outcomes_list
        else "No learning outcomes available"
    )


# Scrape subject page
def scrape_subject(url):
    print(f"   → Visiting subject detail: {url}")
    driver.get(url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    data = {
        "faculty": None,
        "study_level": None,
        "result_type": None,
        "total_workload_hours": None,
        "leanring_outcomes": None,
        "learning_and_teaching_activities": None,
        "description": None,
    }
    # extract all attribute except subject type (already have one leater)
    allowed_keys = {
        "faculty": "faculty",
        "study level": "study_level",
        "result type": "result_type",
        "total workload hours": "total_workload_hours",
    }

    attr_table = soup.find("div", {"data-testid": "attributes-table"})
    if attr_table:
        containers = attr_table.find_all(
            "div", class_=lambda x: x and "AttrContainer" in x
        )
        for container in containers:
            header = container.find("h3")
            if header:
                header_text = header.get_text(strip=True).lower()

                # Check if the current header is in our allow-list
                if header_text in allowed_keys:
                    body = container.find("div", {"data-testid": "AttrBody"})
                    if body:
                        json_key = allowed_keys[header_text]
                        data[json_key] = body.get_text(strip=True)

    # Extract Learning Outcomes
    data["leanring_outcomes"] = extract_learning_outcomes(soup)

    # Extract learning and teaching eactivities
    activities_section = soup.find(
        "div", {"data-menu-id": "Learningandteachingactivities"}
    )
    if activities_section:
        activities_wrapper = activities_section.find(
            "div", class_="readmore-content-wrapper"
        )
        data["learning_and_teaching_activities"] = (
            activities_wrapper.get_text(strip=True)
            if activities_wrapper
            else "No activities available"
        )
    else:
        data["learning_and_teaching_activities"] = "No activities available"

    # Extract description
    desc_section = soup.find("div", {"data-menu-id": "Subjectdescription"})
    if desc_section:
        desc_wrapper = desc_section.find("div", class_="readmore-content-wrapper")
        data["description"] = (
            desc_wrapper.get_text(strip=True)
            if desc_wrapper
            else "No description available"
        )
    else:
        data["description"] = "No description available"

    req_div = soup.find("div", id="Requisites")
    if req_div:
        target_link = req_div.find("a", href=lambda h: h and "subjectcode=" in h)
        if target_link:
            access_url = target_link["href"]
            driver.get(access_url)
            time.sleep(2)

            # Create the container for requisites
            requisite_info = {}

            # Attempt to scrape all three types
            anti = extract_section_data("Anti-requisite(s)")
            reqs = extract_section_data("Requisite(s)")
            other = extract_section_data("Other requisite")

            # Only add to the dictionary if data was actually found
            if anti:
                requisite_info["anti_requisite"] = anti
            if reqs:
                requisite_info["requisite"] = reqs
            if other:
                requisite_info["other_requisite"] = other

            # Only add 'requisite_list' to the main 'data' if it's not empty
            if requisite_info:
                data["requisite_list"] = requisite_info

            driver.back()
            time.sleep(1)

    return data


# function to find if the item is subject or area of study based on the code (used in scrape_aos)
def get_item_type(code):
    if not code:
        return "Unknown"
    if re.match(r"^\d", code):
        return "Subject"
    if code.startswith("MAJ"):
        return "Major"
    if code.startswith("SMJ"):
        return "Sub-Major"
    if code.startswith("CBK"):
        return "Choice Block"
    return "Other"


# Scrape aos (Stand for Area of Study: Major, Sub-major and Choiceblock))
def scrape_aos(url):
    current_page_url = driver.current_url
    print(f"   → Visiting Area of Study detail: {url}")

    driver.get(url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    group_data = {"description": None, "have_structure": []}

    # Extract Description
    desc = soup.find("div", class_="readmore-content-wrapper")
    if desc:
        group_data["description"] = desc.get_text(strip=True)

    # Find the Structure section
    main_section = soup.find("div", {"data-menu-title": "Structure"})
    if main_section:
        # Get the top-level accordions specifically for this AOS (Major/SMJ/CBK)
        # This ensures we get 'Core', 'Options', etc., as separate branches
        top_accordions = [
            div
            for div in main_section.find_all(
                "div", class_=lambda x: x and "AccordionItem" in x
            )
            if not div.find_parent("div", class_=lambda x: x and "AccordionItem" in x)
        ]
        for acc in top_accordions:
            # Recursively crawl each top-level branch of the AOS
            group_data["have_structure"].append(scrape_structure(acc))

    # CRITICAL: Return to the page we were on before this function was called
    # This prevents the loop in scrape_structure from breaking
    print(f"   ← Returning to parent page...")
    driver.get(current_page_url)
    time.sleep(2)
    return group_data


# Scrape structure (The Recursive Tree)
def scrape_structure(parent_accordion):
    #
    name_tag = parent_accordion.find(
        ["strong", "h4"],
        class_=lambda x: x and ("SAlternateHeading" in x or "SDefaultHeading" in x),
    )

    structure_name = name_tag.get_text(strip=True) if name_tag else "Untitled Section"

    cp_tag = parent_accordion.find(
        "strong", class_=lambda x: x and "SAlternateSubheading" in x
    )
    structure_cp = (
        cp_tag.get_text(strip=True) if cp_tag else "No Credit Point Information"
    )

    details_tag = parent_accordion.find(
        "div", class_=lambda x: x and "SAccordionDescription" in x
    )
    structure_details = (
        details_tag.get_text(strip=True) if details_tag else "No Description"
    )

    current_node = {
        "structure_name": structure_name,
        "structure_cp": structure_cp,
        "structure_details": structure_details,
    }

    plate = parent_accordion.find(
        "div", class_=lambda x: x and "SAccordionContentContainer" in x
    )

    if plate:
        for child in plate.find_all("div", recursive=False):
            child_classes = str(child.get("class", []))

            # --- Link Group Logic ---
            if "Links--StyledLinkGroup" in child_classes:
                for a in child.find_all("a", class_="cs-list-item"):
                    code = (
                        a.find("div", class_="section1").get_text(strip=True)
                        if a.find("div", class_="section1")
                        else ""
                    )

                    # Determine Type first to know which list to use
                    item_type = get_item_type(code)

                    # Decide the key name based on type
                    # "Subject" goes to has_subject, everything else goes to has_area_of_study
                    list_key = (
                        "has_subject" if item_type == "Subject" else "has_area_of_study"
                    )

                    # CACHE CHECK
                    if code in visited_subjects:
                        print(f"      Using cached data for {code}")
                        item_obj = visited_subjects[code]
                    else:
                        name = (
                            a.find("div", class_="unit-title").get_text(strip=True)
                            if a.find("div", class_="unit-title")
                            else ""
                        )
                        cp_text = (
                            a.find("div", class_="section2").get_text(strip=True)
                            if a.find("div", class_="section2")
                            else ""
                        )
                        full_url = urljoin(BASE_URL, a["href"])

                        if item_type == "Subject":
                            details = scrape_subject(full_url)
                        else:
                            details = scrape_aos(full_url)

                        item_obj = {
                            "code": code,
                            "name": name,
                            "credit_points": cp_text,
                            "type": item_type,
                            "url": full_url,
                            **details,
                        }
                        visited_subjects[code] = item_obj

                    # Add to the specific list in current_node
                    if list_key not in current_node:
                        current_node[list_key] = []
                    current_node[list_key].append(item_obj)

            # --- Sub-sections (Recursive Call) ---
            elif "AccordionItem" in child_classes:
                sub_data = scrape_structure(child)
                if sub_data:
                    if "have_sub_structures" not in current_node:
                        current_node["have_sub_structures"] = []
                    current_node["have_sub_structures"].append(sub_data)

    return current_node


# Scrape course
def scrape_course(course_url):
    print(f"Scraping course page: {course_url}")
    driver.get(course_url)
    time.sleep(5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    # scrape course name and code
    course_header = soup.find("h2", {"data-testid": "ai-header"}).get_text()
    course_code, course_name = [item.strip() for item in course_header.split("-", 1)]
    # scrape course details
    details = soup.find("div", class_="readmore-content-wrapper")
    course_details = details.get_text(strip=True) if details else "No details"
    course_leanring_outcomes = extract_learning_outcomes(soup)
    course_data = {
        "course_code": course_code,
        "course_name": course_name,
        "course_details": course_details,
        "course_leanring_outcomes": course_leanring_outcomes,
        "course_url": course_url,
        "structure": [],
    }

    main_section = soup.find("div", {"data-menu-title": "Structure"})
    if main_section:
        # Get the top-level accordions (Core, Major, Options, etc.)
        top_accordions = [
            div
            for div in main_section.find_all(
                "div", class_=lambda x: x and "AccordionItem" in x
            )
            if not div.find_parent("div", class_=lambda x: x and "AccordionItem" in x)
        ]

        for acc in top_accordions:
            course_data["structure"].append(scrape_structure(acc))
            # After recursion finishes one big branch, ensure we are back on the main page
            driver.get(course_url)
            time.sleep(2)

    return course_data


visited_subjects = {}

if __name__ == "__main__":
    # Ask user for the URL
    target_url = input("Enter the UTS Course Handbook URL to scrape: ").strip()

    # Extract Metadata (Year) first to load the correct cache
    url_parts = target_url.rstrip("/").split("/")
    # Expected URL structure: .../course/2026/C10474...
    year = url_parts[-2]

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
    # Note: scrape_structure inside scrape_course will now use and update the 'visited_subjects' global dict
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
