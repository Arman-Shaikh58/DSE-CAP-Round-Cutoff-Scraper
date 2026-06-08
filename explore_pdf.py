"""Download and inspect one sample PDF to understand its table structure."""
import requests
import pdfplumber
import os

url = "https://dse2025.mahacet.org.in/dse25/admin/allotment/cap1/1002_4.pdf"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}

os.makedirs("/home/arman/testing/collage_scrapping/sample_pdfs", exist_ok=True)
pdf_path = "/home/arman/testing/collage_scrapping/sample_pdfs/1002_cap1.pdf"

resp = requests.get(url, headers=headers, timeout=30)
print(f"Status: {resp.status_code}, Size: {len(resp.content)} bytes")

if resp.status_code == 200:
    with open(pdf_path, "wb") as f:
        f.write(resp.content)
    print(f"Saved to {pdf_path}")
    
    # Extract text and tables from the PDF
    with pdfplumber.open(pdf_path) as pdf:
        print(f"\nTotal pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages[:3]):
            print(f"\n--- Page {i+1} ---")
            text = page.extract_text()
            if text:
                # Print first 2000 chars
                print(text[:2000])
            
            tables = page.extract_tables()
            if tables:
                print(f"\n  Tables found: {len(tables)}")
                for j, table in enumerate(tables):
                    print(f"\n  Table {j}: {len(table)} rows")
                    for k, row in enumerate(table[:8]):
                        print(f"    Row {k}: {row}")
else:
    print(f"Failed to download: {resp.status_code}")
