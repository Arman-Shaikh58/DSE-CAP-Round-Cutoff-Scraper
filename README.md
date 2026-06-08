# DSE 2025 — CAP Round Cutoff Scraper

Automated pipeline to scrape, extract, and compile **CS-related branch cutoff data** from the [DSE 2025 MAHACET](https://dse2025.mahacet.org.in) institute-wise allotment page into a styled Excel report.

---

## How It Works

The scraper runs as a **3-phase pipeline**, orchestrated by `main.py`:

### Phase 1 — Scrape & Download (`phase1_download.py`)

1. Reads target college codes from `institudes.csv`.
2. Fetches the institute-wise allotment page from the MAHACET website using **BeautifulSoup**.
3. Parses the HTML table to extract PDF download URLs for all 4 CAP rounds (CAP 1–4).
4. Downloads PDFs **in parallel** (8 threads) into the `pdfs/` directory, organized by round (`pdfs/cap1/`, `pdfs/cap2/`, etc.).
5. Saves a mapping of college codes → PDF URLs to `colleges_links.csv`.

### Phase 2 — Extract Cutoffs (`phase2_extract.py`)

1. Reads the college list from `colleges_links.csv`.
2. Opens each downloaded PDF with **pdfplumber** and extracts tabular data.
3. Identifies CS-related branches using a two-tier classification:
   - **Keyword matching** (fast path) — checks against a curated list of CS/IT/AI/ML/Data Science keywords.
   - **LLM fallback** — for ambiguous branch names, queries a local **Ollama** model (`gemma4:e2b`) via LangChain to classify.
4. Extracts the **lowest cutoff marks** for three categories:
   - **Open** (GOPEN, LOPEN)
   - **EWS**
   - **SEBC** (GSEBC, LSEBC)
5. Saves all extracted cutoffs to `cutoffs_raw.csv`.

### Phase 3 — Generate Excel Report (`phase3_excel.py`)

1. Reads `cutoffs_raw.csv` and pivots the data by college + branch combination.
2. Generates a **styled Excel file** (`dse_cutoffs_2025.xlsx`) using **openpyxl** with:
   - Merged header rows for CAP rounds.
   - Sub-headers for Open / EWS / SEBC categories.
   - Alternating row colors, frozen panes, and auto-fitted column widths.

---

## Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager (recommended)
- **[Ollama](https://ollama.com/)** — Local LLM runtime (required for Phase 2's branch classification fallback)
  - Pull the model: `ollama pull gemma4:e2b`

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd collage_scrapping
```

### 2. Install dependencies

Using **uv** (recommended):

```bash
uv sync
```

Or using **pip**:

```bash
pip install beautifulsoup4 langchain langchain-ollama openpyxl pandas pdfplumber requests
```

### 3. Start Ollama (required for Phase 2)

Make sure the Ollama server is running and the model is pulled:

```bash
ollama serve          # start the server (if not already running)
ollama pull gemma4:e2b  # download the model
```

### 4. Configure target colleges

Edit `institudes.csv` to list the college codes you want to scrape (one code per line):

```csv
code
1002
3012
6005
...
```

---

## Running the Scraper

### Run the full pipeline

```bash
uv run python main.py
```

Or without uv:

```bash
python main.py
```

This runs all 3 phases sequentially and prints progress to the terminal.

### Run individual phases

You can also run each phase independently:

```bash
# Phase 1 only — download PDFs
uv run python phase1_download.py

# Phase 2 only — extract cutoffs (requires Phase 1 output)
uv run python phase2_extract.py

# Phase 3 only — generate Excel (requires Phase 2 output)
uv run python phase3_excel.py
```

---

## Output Files

| File                   | Description                                            |
| ---------------------- | ------------------------------------------------------ |
| `colleges_links.csv`   | College codes, names, and PDF URLs for all CAP rounds  |
| `pdfs/`                | Downloaded PDF files organized by CAP round            |
| `cutoffs_raw.csv`      | Extracted cutoff data (college, branch, category, marks)|
| `dse_cutoffs_2025.xlsx`| Final styled Excel report with all cutoffs consolidated |

---

## Utility Scripts

| Script            | Purpose                                                    |
| ----------------- | ---------------------------------------------------------- |
| `explore_page.py` | Inspect the HTML structure of the MAHACET allotment page   |
| `explore_pdf.py`  | Download and inspect a sample PDF's table structure         |

These are **exploration/debugging** scripts and are not part of the main pipeline.

---

## Project Structure

```
collage_scrapping/
├── main.py               # Orchestrator — runs all 3 phases
├── phase1_download.py    # Phase 1: Scrape website & download PDFs
├── phase2_extract.py     # Phase 2: Extract cutoffs from PDFs
├── phase3_excel.py       # Phase 3: Generate styled Excel report
├── institudes.csv        # Input: target college codes
├── explore_page.py       # Utility: inspect page HTML
├── explore_pdf.py        # Utility: inspect PDF structure
├── pyproject.toml        # Project config & dependencies
├── uv.lock               # Lockfile for uv
└── README.md             # This file
```

---

## Dependencies

| Package            | Purpose                              |
| ------------------ | ------------------------------------ |
| `beautifulsoup4`   | HTML parsing for web scraping        |
| `requests`         | HTTP requests for page & PDF download|
| `pdfplumber`       | PDF table extraction                 |
| `langchain`        | LLM orchestration framework          |
| `langchain-ollama` | Ollama integration for LangChain     |
| `openpyxl`         | Excel file generation & styling      |
| `pandas`           | Data manipulation                    |
