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

# Seat type groupings for cutoff categories
SEAT_TYPE_GROUPS = {
    "Open": ["GOPEN", "LOPEN"],
    "EWS": ["EWS"],
    "SEBC": ["GSEBC", "LSEBC"],
}

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


def extract_cutoffs_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract cutoff data from a single CAP round PDF.

    Returns a list of dicts with:
        branch_code, branch_name, seat_type -> min_marks
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

                # Compute cutoffs per category
                cutoffs: dict[str, float | None] = {}
                for category, seat_types in SEAT_TYPE_GROUPS.items():
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


def run_phase2() -> Path:
    """
    Main entry point for Phase 2.

    Returns the path to the generated cutoffs_raw.csv.
    """
    # Load college info
    colleges: list[dict] = []
    with open(COLLEGES_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            colleges.append(row)

    print(f"[Phase 2] Processing {len(colleges)} colleges × {len(CAP_ROUNDS)} CAP rounds")

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

            branches = extract_cutoffs_from_pdf(pdf_path)
            print(
                f"  CAP {cap_round}: Found {len(branches)} CS-related branch(es)"
            )

            for branch in branches:
                cutoffs = branch["cutoffs"]
                all_cutoffs.append(
                    {
                        "college_code": code,
                        "college_name": name,
                        "cap_round": cap_round,
                        "branch_code": branch["branch_code"],
                        "branch_name": branch["branch_name"],
                        "cutoff_open": cutoffs.get("Open"),
                        "cutoff_ews": cutoffs.get("EWS"),
                        "cutoff_sebc": cutoffs.get("SEBC"),
                    }
                )

    # Save to CSV
    fieldnames = [
        "college_code",
        "college_name",
        "cap_round",
        "branch_code",
        "branch_name",
        "cutoff_open",
        "cutoff_ews",
        "cutoff_sebc",
    ]
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
