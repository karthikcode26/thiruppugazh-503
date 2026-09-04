#!/usr/bin/env python3
"""
Extract the embedded hyperlinks (Google Drive video links) from the
Thiruppugazh master-list PDF.

Usage:
    pip3 install pymupdf
    python3 tools/extract_links.py masterlist.pdf

Output:
    links.csv  ->  rows of:  song_text_near_link , url
    Also prints a summary so you can sanity-check the count (expect ~503).

Notes:
- Each PDF link has a rectangle (its position). We grab the text sitting
  inside/near that rectangle, which is the song name in that row.
- You'll still want to eyeball links.csv to confirm the song<->link pairing,
  because PDFs don't store "which row" a link belongs to -- only coordinates.
"""

import sys
import csv

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF is not installed. Run:  pip3 install pymupdf")
    sys.exit(1)


def main(pdf_path):
    doc = fitz.open(pdf_path)
    rows = []
    for page_index in range(len(doc)):
        page = doc[page_index]
        links = page.get_links()
        for link in links:
            uri = link.get("uri")
            if not uri:
                continue  # skip internal/non-URL links
            rect = fitz.Rect(link["from"])
            # Grab the text under the link's rectangle (the song name in that row)
            # Expand the rectangle a little to catch the whole word.
            words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,wordno)
            near = []
            for w in words:
                wx0, wy0, wx1, wy1, word = w[0], w[1], w[2], w[3], w[4]
                wrect = fitz.Rect(wx0, wy0, wx1, wy1)
                # keep words whose vertical center is within the link's row band
                cy = (wy0 + wy1) / 2
                if rect.y0 - 3 <= cy <= rect.y1 + 3:
                    near.append((wx0, word))
            near.sort()
            label = " ".join(w for _, w in near).strip()
            rows.append((page_index + 1, label, uri))

    with open("links.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["page", "text_in_row", "url"])
        writer.writerows(rows)

    print(f"Found {len(rows)} links across {len(doc)} pages.")
    print("Wrote links.csv")
    print("Expected ~503 links. If the count is very different, tell Kiro.")
    # show a small preview
    for r in rows[:5]:
        print("  ", r)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 tools/extract_links.py <path-to-pdf>")
        sys.exit(1)
    main(sys.argv[1])
