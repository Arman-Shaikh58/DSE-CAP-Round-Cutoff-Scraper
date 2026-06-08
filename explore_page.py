"""Quick script to explore the page structure of the CAP allotment page."""
import requests
from bs4 import BeautifulSoup

url = "https://dse2025.mahacet.org.in/dse25/index.php/hp_controller/instwiseallotment"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

resp = requests.get(url, headers=headers, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('Content-Type')}")
print(f"Content length: {len(resp.text)}")

soup = BeautifulSoup(resp.text, "html.parser")

# 1. Find tabs (CAP rounds)
print("\n=== TABS/NAV ===")
for tab in soup.select(".nav-tabs li, .nav-link, .nav-item, [role='tab']"):
    print(f"  Tag={tab.name}, Text={tab.get_text(strip=True)[:80]}, id={tab.get('id')}, href={tab.get('href')}")

# 2. Find tab panes
print("\n=== TAB PANES ===")
for pane in soup.select(".tab-pane"):
    print(f"  id={pane.get('id')}, class={pane.get('class')}")

# 3. Find tables
print("\n=== TABLES ===")
for i, table in enumerate(soup.find_all("table")):
    rows = table.find_all("tr")
    print(f"\n  Table {i}: {len(rows)} rows, class={table.get('class')}")
    for j, row in enumerate(rows[:4]):
        cells = row.find_all(["th", "td"])
        cell_texts = [c.get_text(strip=True)[:60] for c in cells]
        print(f"    Row {j}: {cell_texts}")
    # Check for download buttons in this table
    btns = table.find_all(["a", "button"], string=lambda t: t and "download" in t.lower() if t else False)
    if not btns:
        btns = table.select("[onclick]")
    if btns:
        print(f"    Download buttons found: {len(btns)}")
        for b in btns[:3]:
            print(f"      onclick={b.get('onclick')}, href={b.get('href')}, text={b.get_text(strip=True)[:50]}")

# 4. Find all onclick handlers related to download
print("\n=== DOWNLOAD ONCLICK HANDLERS ===")
onclick_elements = soup.select("[onclick]")
print(f"Total elements with onclick: {len(onclick_elements)}")
seen = set()
for el in onclick_elements[:20]:
    oc = el.get("onclick", "")
    if oc not in seen:
        seen.add(oc)
        print(f"  {oc[:200]}")

# 5. Find script tags with download-related content
print("\n=== SCRIPT CONTENT (download-related) ===")
for script in soup.find_all("script"):
    if script.string and ("download" in script.string.lower() or "pdf" in script.string.lower()):
        content = script.string
        print(f"  Script length: {len(content)}")
        print(f"  Content: {content[:2000]}")
        print("  ---")

# 6. Save full HTML for reference
with open("/home/arman/testing/collage_scrapping/page_source.html", "w") as f:
    f.write(resp.text)
print("\nFull HTML saved to page_source.html")
