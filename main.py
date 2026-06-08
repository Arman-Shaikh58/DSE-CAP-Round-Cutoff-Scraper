"""
DSE 2025 CAP Round Cutoff Scraper — Main Orchestrator

Runs all 3 phases sequentially:
  Phase 1: Scrape website & download PDFs (BeautifulSoup)
  Phase 2: Extract cutoffs from PDFs (pdfplumber + LangChain/Ollama)
  Phase 3: Generate Excel report (openpyxl)
"""

import sys
import time


def main():
    print("=" * 70)
    print("  DSE 2025 — CAP Round Cutoff Scraper")
    print("=" * 70)
    start = time.time()

    # ---- Phase 1 ----
    print("\n" + "─" * 70)
    print("  PHASE 1: Scraping website & downloading PDFs")
    print("─" * 70)
    from phase1_download import run_phase1

    try:
        colleges_csv = run_phase1()
    except Exception as e:
        print(f"\n❌ Phase 1 failed: {e}")
        sys.exit(1)

    # ---- Phase 2 ----
    print("\n" + "─" * 70)
    print("  PHASE 2: Extracting cutoffs from PDFs")
    print("─" * 70)
    from phase2_extract import run_phase2

    try:
        cutoffs_csv = run_phase2()
    except Exception as e:
        print(f"\n❌ Phase 2 failed: {e}")
        sys.exit(1)

    # ---- Phase 3 ----
    print("\n" + "─" * 70)
    print("  PHASE 3: Generating Excel report")
    print("─" * 70)
    from phase3_excel import run_phase3

    try:
        excel_path = run_phase3()
    except Exception as e:
        print(f"\n❌ Phase 3 failed: {e}")
        sys.exit(1)

    # ---- Summary ----
    elapsed = time.time() - start
    print("\n" + "=" * 70)
    print(f"  ✅ ALL DONE in {elapsed:.1f}s")
    print(f"  📊 Excel report: {excel_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
