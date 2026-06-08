"""
Phase 1: Scrape the DSE 2025 CAP allotment page and download PDFs.

Uses BeautifulSoup to parse the institute-wise allotment page,
extracts PDF download URLs for the 21 colleges in institudes.csv,
and downloads all 4 CAP round PDFs for each — in parallel.
"""

import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
INSTITUTES_CSV = BASE_DIR / "institudes.csv"
PDF_DIR = BASE_DIR / "pdfs"
COLLEGES_CSV = BASE_DIR / "colleges_links.csv"

ALLOTMENT_URL = (
    "https://dse2025.mahacet.org.in/dse25/index.php/hp_controller/instwiseallotment"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

CAP_ROUNDS = [1, 2, 3, 4]
MAX_WORKERS = 8  # parallel download threads

# Regex to extract PDF URL from onclick attribute
# Pattern: MM_openBrWindow4('https://...cap1/1002_4.pdf','1','1')
ONCLICK_RE = re.compile(r"MM_openBrWindow4\('([^']+\.pdf)'")


def load_target_codes() -> set[str]:
    """Load the college codes from institudes.csv."""
    codes: set[str] = set()
    with open(INSTITUTES_CSV, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if row and row[0].strip():
                codes.add(row[0].strip())
    print(f"[Phase 1] Loaded {len(codes)} target college codes from institudes.csv")
    return codes


def scrape_allotment_page() -> list[dict]:
    """
    Scrape the institute-wise allotment page.

    Returns a list of dicts, each with:
        sr_no, code, name, cap1_url, cap2_url, cap3_url, cap4_url
    """
    print(f"[Phase 1] Fetching allotment page: {ALLOTMENT_URL}")
    resp = requests.get(ALLOTMENT_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # The main table is the one with class 'table-striped'
    table = soup.find("table", class_="table-striped")
    if not table:
        raise RuntimeError("Could not find the institute table on the page")

    rows = table.find_all("tr")
    print(f"[Phase 1] Found {len(rows) - 1} institutes on the page")

    institutes: list[dict] = []
    for row in rows[1:]:  # skip header row
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        sr_no = cells[0].get_text(strip=True)
        code = cells[1].get_text(strip=True)
        name = cells[2].get_text(strip=True)

        # Extract PDF URLs from CAP round columns (indices 3-6)
        cap_urls: dict[str, str] = {}
        for i, cap_round in enumerate(CAP_ROUNDS, start=3):
            cell = cells[i]
            link = cell.find("a", onclick=True)
            if link:
                match = ONCLICK_RE.search(link.get("onclick", ""))
                if match:
                    cap_urls[f"cap{cap_round}_url"] = match.group(1)

        institutes.append(
            {
                "sr_no": sr_no,
                "code": code,
                "name": name,
                **{f"cap{r}_url": cap_urls.get(f"cap{r}_url", "") for r in CAP_ROUNDS},
            }
        )

    return institutes


def download_single_pdf(
    url: str, save_path: Path, label: str, retries: int = 3
) -> tuple[str, bool]:
    """Download a single PDF. Returns (label, success)."""
    if save_path.exists():
        return label, True

    save_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                return label, True
        except requests.RequestException:
            pass
        if attempt < retries:
            time.sleep(1)

    return label, False


def run_phase1() -> Path:
    """
    Main entry point for Phase 1.

    Returns the path to the generated colleges_links.csv.
    """
    target_codes = load_target_codes()
    all_institutes = scrape_allotment_page()

    # Filter to only target colleges
    filtered = [inst for inst in all_institutes if inst["code"] in target_codes]
    print(f"[Phase 1] Matched {len(filtered)} / {len(target_codes)} target colleges")

    # Report any codes not found on the page
    found_codes = {inst["code"] for inst in filtered}
    missing = target_codes - found_codes
    if missing:
        print(f"[Phase 1] ⚠ Codes not found on page: {sorted(missing)}")

    # Build download jobs
    jobs: list[tuple[str, Path, str]] = []  # (url, save_path, label)
    for inst in filtered:
        code = inst["code"]
        name = inst["name"]
        for cap_round in CAP_ROUNDS:
            url = inst.get(f"cap{cap_round}_url", "")
            if url:
                save_path = PDF_DIR / f"cap{cap_round}" / f"{code}_cap{cap_round}.pdf"
                label = f"{code} CAP-{cap_round}"
                jobs.append((url, save_path, label))

    print(
        f"[Phase 1] Downloading {len(jobs)} PDFs with {MAX_WORKERS} parallel threads..."
    )

    # Parallel download
    downloaded = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(download_single_pdf, url, path, label): label
            for url, path, label in jobs
        }
        for future in as_completed(futures):
            label, success = future.result()
            if success:
                downloaded += 1
                print(f"  ✅ {label}")
            else:
                failed += 1
                print(f"  ❌ {label}")

    print(f"\n[Phase 1] Download complete: {downloaded}/{len(jobs)} success, {failed} failed")

    # Save colleges_links.csv
    with open(COLLEGES_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["code", "name", "cap1_url", "cap2_url", "cap3_url", "cap4_url"],
        )
        writer.writeheader()
        for inst in filtered:
            writer.writerow(
                {
                    "code": inst["code"],
                    "name": inst["name"],
                    "cap1_url": inst.get("cap1_url", ""),
                    "cap2_url": inst.get("cap2_url", ""),
                    "cap3_url": inst.get("cap3_url", ""),
                    "cap4_url": inst.get("cap4_url", ""),
                }
            )
    print(f"[Phase 1] Saved college links to {COLLEGES_CSV}")

    return COLLEGES_CSV


if __name__ == "__main__":
    run_phase1()
