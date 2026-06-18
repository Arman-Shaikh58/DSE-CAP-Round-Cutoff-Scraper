"""
Phase 2: Extract cutoff data from downloaded CAP round PDFs.

Uses pdfplumber for structured table extraction and LangChain + Ollama
(gemma4:e2b) for classifying branches as CS-related.
"""

import csv
import re
from pathlib import Path

import pdfplumber
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
PDF_DIR = BASE_DIR / "pdfs"
COLLEGES_CSV = BASE_DIR / "colleges_links.csv"
CUTOFFS_CSV = BASE_DIR / "cutoffs_raw.csv"

CAP_ROUNDS = [1, 2, 3, 4]

# Keywords that definitely mark a branch as CS-related (fast path, no LLM)
CS_KEYWORDS = [
    "computer science",
    "computer engineering",
    "computer technology",
    "information technology",
    "artificial intelligence",
    "machine learning",
    "data science",
    "data engineering",
    "robotics",
    "automation",
    "aiml",
    "ai&ml",
    "ai & ml",
    "cyber security",
    "cybersecurity",
    "iot",
    "internet of things",
    "cloud computing",
    "software engineering",
    "cse",
    "csbs",
    "cs&bs",
]

# ---------------------------------------------------------------------------
# All possible seat type groupings — master list
# Each key is a cutoff category name, and its value lists the seat type codes
# (as they appear in the PDFs after .upper()) that belong to that category.
# ---------------------------------------------------------------------------
ALL_SEAT_TYPE_GROUPS: dict[str, list[str]] = {
    "Open":   ["GOPEN", "LOPEN"],
    "OBC":    ["GOBC", "LOBC", "OBC"],
    "EWS":    ["GEWS", "LEWS", "EWS"],
    "SEBC":   ["GSEBC", "LSEBC"],
    "SC":     ["GSC", "LSC", "SC"],
    "ST":     ["GST", "LST", "ST"],
    "VJ/DT":  ["GVJDTNTA", "GVJDTNTB", "GVJDTNTC", "GVJDTNTD",
               "LVJDTNTA", "LVJDTNTB", "LVJDTNTC", "LVJDTNTD"],
    "NT1":    ["GNT1", "LNT1", "NT1"],
    "NT2":    ["GNT2", "LNT2", "NT2"],
    "NT3":    ["GNT3", "LNT3", "NT3"],
    "TFWS":   ["TFWS"],
}


def prompt_categories(
    all_groups: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Display all available categories and let the user pick which ones
    to include.  Press Enter with no input to select all.

    Returns a list of selected category names (keys of ALL_SEAT_TYPE_GROUPS).
    """
    groups = all_groups or ALL_SEAT_TYPE_GROUPS
    names = list(groups.keys())

    print("\n[Phase 2] Available cutoff categories:")
    for i, name in enumerate(names, 1):
        seat_codes = ", ".join(groups[name])
        print(f"  {i:>2}. {name:<8}  (seat types: {seat_codes})")

    print(
        f"\nEnter category numbers separated by commas (e.g. 1,2,3),\n"
        f"or press Enter to select ALL:"
    )
    user_input = input(">>> ").strip()

    if not user_input:
        selected = names
    else:
        selected = []
        for part in user_input.split(","):
            part = part.strip()
            try:
                idx = int(part) - 1
                if 0 <= idx < len(names):
                    selected.append(names[idx])
                else:
                    print(f"  ⚠ Ignoring invalid number: {part}")
            except ValueError:
                print(f"  ⚠ Ignoring invalid input: {part}")

    if not selected:
        print("  No valid selection — defaulting to ALL categories.")
        selected = names

    print(f"[Phase 2] Selected categories: {', '.join(selected)}\n")
    return selected


# ---------------------------------------------------------------------------
# LLM Setup (lazy init)
# ---------------------------------------------------------------------------
_llm = None


def get_llm() -> ChatOllama:
    """Lazy-initialize the Ollama LLM."""
    global _llm
    if _llm is None:
        print("[Phase 2] Initializing Ollama LLM (gemma4:e2b)...")
        _llm = ChatOllama(
            model="gemma4:e2b",
            temperature=0,
        )
    return _llm


def is_cs_related_fast(branch_name: str) -> bool | None:
    """
    Quick keyword check. Returns True/False if confident, None if unsure.
    """
    name_lower = branch_name.lower()
    for kw in CS_KEYWORDS:
        if kw in name_lower:
            return True

    # Definitely NOT CS-related keywords
    non_cs = [
        "civil",
        "mechanical",
        "electrical",
        "electronics",
        "chemical",
        "textile",
        "metallurgy",
        "mining",
        "environmental",
        "production",
        "automobile",
        "polymer",
        "plastic",
        "food",
        "aeronautical",
        "aerospace",
        "marine",
        "biomedical",
        "biotechnology",
        "bio tech",
        "instrumentation",
        "petroleum",
        "agricultural",
        "printing",
        "architecture",
        "pharmacy",
        "pharmaceutical",
    ]
    for kw in non_cs:
        if kw in name_lower:
            return False

    return None  # Unsure — ask LLM


def is_cs_related_llm(branch_name: str) -> bool:
    """Use the Ollama LLM to classify if a branch is CS-related."""
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a branch classifier for engineering colleges. "
                "Answer ONLY 'YES' or 'NO'. "
                "Is the following branch related to Computer Science, "
                "Information Technology, AI/ML, Data Science, Robotics, "
                "or Cyber Security?"
            )
        ),
        HumanMessage(content=f"Branch: {branch_name}"),
    ]
    response = llm.invoke(messages)
    answer = response.content.strip().upper()
    return "YES" in answer


def is_cs_related(branch_name: str) -> bool:
    """Check if a branch is CS-related (keyword first, then LLM fallback)."""
    fast_result = is_cs_related_fast(branch_name)
    if fast_result is not None:
        return fast_result
    # Fallback to LLM for ambiguous branches
    print(f"    🤖 Asking LLM about: {branch_name}")
    result = is_cs_related_llm(branch_name)
    print(f"    🤖 LLM says: {'YES' if result else 'NO'}")
    return result


def extract_cutoffs_from_pdf(
    pdf_path: Path,
    seat_type_groups: dict[str, list[str]],
) -> list[dict]:
    """
    Extract cutoff data from a single CAP round PDF.

    Returns a list of dicts with:
        branch_code, branch_name, cutoffs (dict of category -> min_marks)
    """
    results: list[dict] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if len(tables) < 2:
                    continue

                # Table 0: header info [['Course', '100219110 - Civil Engineering'], ...]
                header_table = tables[0]
                course_info = ""
                for row in header_table:
                    if row and row[0] and "Course" in str(row[0]):
                        course_info = str(row[1]) if len(row) > 1 and row[1] else ""
                        break

                if not course_info:
                    continue

                # Parse branch code and name
                # Format: "100219110 - Civil Engineering"
                match = re.match(r"(\d+)\s*-\s*(.+)", course_info.strip())
                if not match:
                    continue

                branch_code = match.group(1).strip()
                branch_name = match.group(2).strip()

                # Check if CS-related
                if not is_cs_related(branch_name):
                    continue

                # Table 1: student allotment data
                student_table = tables[1]
                if len(student_table) < 2:
                    continue

                # Find column indices from header
                header_row = student_table[0]
                col_map: dict[str, int] = {}
                for idx, col in enumerate(header_row):
                    col_text = str(col).strip().lower() if col else ""
                    if "marks" in col_text:
                        col_map["marks"] = idx
                    elif "seat type" in col_text or "seat" in col_text:
                        col_map["seat_type"] = idx

                if "marks" not in col_map or "seat_type" not in col_map:
                    continue

                # Collect marks per seat type
                seat_marks: dict[str, list[float]] = {}
                for row in student_table[1:]:
                    try:
                        marks_str = str(row[col_map["marks"]]).strip()
                        seat_type = str(row[col_map["seat_type"]]).strip().upper()

                        if not marks_str or not seat_type:
                            continue

                        # Parse marks (remove % sign)
                        marks_val = float(marks_str.replace("%", "").strip())
                        seat_marks.setdefault(seat_type, []).append(marks_val)
                    except (ValueError, IndexError):
                        continue

                # Compute cutoffs per category (only for selected categories)
                cutoffs: dict[str, float | None] = {}
                for category, seat_types in seat_type_groups.items():
                    all_marks: list[float] = []
                    for st in seat_types:
                        all_marks.extend(seat_marks.get(st, []))
                    cutoffs[category] = min(all_marks) if all_marks else None

                results.append(
                    {
                        "branch_code": branch_code,
                        "branch_name": branch_name,
                        "cutoffs": cutoffs,
                        "all_seat_marks": seat_marks,  # for debugging
                    }
                )

    except Exception as e:
        print(f"    ❌ Error reading {pdf_path.name}: {e}")

    return results


def run_phase2(categories: list[str] | None = None) -> Path:
    """
    Main entry point for Phase 2.

    Args:
        categories: List of category names to extract. If None, the user
                    will be prompted to choose interactively.

    Returns the path to the generated cutoffs_raw.csv.
    """
    # Determine which categories to extract
    if categories is None:
        categories = prompt_categories()

    # Build the seat type groups dict for only the selected categories
    seat_type_groups = {
        cat: ALL_SEAT_TYPE_GROUPS[cat]
        for cat in categories
        if cat in ALL_SEAT_TYPE_GROUPS
    }

    if not seat_type_groups:
        raise ValueError("No valid categories selected!")

    print(f"[Phase 2] Extracting cutoffs for: {', '.join(seat_type_groups.keys())}")

    # Load college info
    colleges: list[dict] = []
    with open(COLLEGES_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            colleges.append(row)

    print(
        f"[Phase 2] Processing {len(colleges)} colleges × {len(CAP_ROUNDS)} CAP rounds"
    )

    all_cutoffs: list[dict] = []

    for college in colleges:
        code = college["code"]
        name = college["name"]
        print(f"\n[Phase 2] 📄 {code} - {name}")

        for cap_round in CAP_ROUNDS:
            pdf_path = PDF_DIR / f"cap{cap_round}" / f"{code}_cap{cap_round}.pdf"

            if not pdf_path.exists():
                print(f"  CAP {cap_round}: PDF not found, skipping")
                continue

            branches = extract_cutoffs_from_pdf(pdf_path, seat_type_groups)
            print(f"  CAP {cap_round}: Found {len(branches)} CS-related branch(es)")

            for branch in branches:
                cutoffs = branch["cutoffs"]
                row_data = {
                    "college_code": code,
                    "college_name": name,
                    "cap_round": cap_round,
                    "branch_code": branch["branch_code"],
                    "branch_name": branch["branch_name"],
                }
                # Dynamically add cutoff columns for each selected category
                for cat in seat_type_groups:
                    row_data[f"cutoff_{cat.lower()}"] = cutoffs.get(cat)

                all_cutoffs.append(row_data)

    # Build fieldnames dynamically
    fieldnames = [
        "college_code",
        "college_name",
        "cap_round",
        "branch_code",
        "branch_name",
    ]
    for cat in seat_type_groups:
        fieldnames.append(f"cutoff_{cat.lower()}")

    # Save to CSV
    with open(CUTOFFS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_cutoffs:
            writer.writerow(row)

    print(f"\n[Phase 2] ✅ Extracted {len(all_cutoffs)} cutoff records")
    print(f"[Phase 2] Saved to {CUTOFFS_CSV}")

    return CUTOFFS_CSV


if __name__ == "__main__":
    run_phase2()
