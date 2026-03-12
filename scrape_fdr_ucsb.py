"""
FDR Document Scraper — American Presidency Project (UCSB)
==========================================================
Scrapes ALL Franklin D. Roosevelt documents from presidency.ucsb.edu:
  - Speeches, fireside chats, press conferences, State of the Union,
    messages to Congress, proclamations, executive orders, and more.

Outputs (in ./fdr_ucsb/):
  - txt/          one .txt file per document
  - fdr_ucsb_corpus.txt     single combined file for training
  - fdr_ucsb_metadata.csv   title, date, category, URL, word count

Usage:
    pip install requests beautifulsoup4
    python3 scrape_fdr_ucsb.py

Citation:
    Gerhard Peters and John T. Woolley, The American Presidency Project.
    https://www.presidency.ucsb.edu
"""

import os, re, time, csv, requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = "https://www.presidency.ucsb.edu"
# FDR person page with paginated "Related Documents" list (pages 0–180+)
INDEX_URL   = BASE_URL + "/people/president/franklin-d-roosevelt?page={page}"
OUTPUT_DIR  = "./fdr_ucsb"
TXT_DIR     = os.path.join(OUTPUT_DIR, "txt")
CORPUS_FILE = os.path.join(OUTPUT_DIR, "fdr_ucsb_corpus.txt")
META_FILE   = os.path.join(OUTPUT_DIR, "fdr_ucsb_metadata.csv")
DELAY       = 1.5   # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:80]


# ── Step 1: Collect all document links from the FDR person page ──────────────

def get_all_doc_links():
    """
    Paginate through the FDR person page's "Related Documents" list.
    Returns list of dicts: {title, url, date, category}
    """
    docs = []
    page = 0
    print("Fetching document index pages...")

    while True:
        url = INDEX_URL.format(page=page)
        print(f"  Page {page}  ({len(docs)} docs so far)...")
        try:
            soup = get_soup(url)
        except Exception as e:
            print(f"  ERROR on page {page}: {e}")
            break

        # Document links point to /documents/... — grab all matching anchors
        # Exclude site navigation pages (guidebook, category attributes, etc.)
        SKIP_PREFIXES = (
            "/documents/presidential-documents-archive-guidebook",
            "/documents/category-attributes",
            "/documents/app-categories",
        )
        rows = [
            a for a in soup.select("a[href^='/documents/']")
            if a.get_text(strip=True)
            and not any(a["href"].startswith(p) for p in SKIP_PREFIXES)
        ]

        if not rows:
            print(f"  No document links found on page {page} — stopping pagination.")
            break

        for a in rows:
            href = a["href"]
            title = a.get_text(strip=True)
            full_url = BASE_URL + href
            docs.append({"title": title, "url": full_url, "date": "", "category": ""})

        # Check for a "next page" link
        next_link = (
            soup.select_one("li.pager__item--next a")
            or soup.select_one("a[title='Go to next page']")
            or soup.find("a", string=re.compile(r"next|›"))
        )
        if not next_link:
            print(f"  No next page after page {page}. Done paginating.")
            break

        page += 1
        time.sleep(DELAY)

    # Deduplicate
    seen, unique = set(), []
    for d in docs:
        if d["url"] not in seen:
            seen.add(d["url"])
            unique.append(d)

    print(f"\nTotal unique documents found: {len(unique)}")
    return unique


# ── Step 2: Scrape each document page ────────────────────────────────────────

def scrape_document(doc):
    """Fetch a document page, extract text, date, and category."""
    try:
        soup = get_soup(doc["url"])
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

    # Date — UCSB uses <span class="date-display-single"> or similar
    date_tag = (
        soup.select_one("span.date-display-single")
        or soup.select_one(".field--name-field-docs-start-date-time")
        or soup.select_one("span.documentary-header__date")
        or soup.select_one("div.field--name-field-docs-start-date-time span")
    )
    doc["date"] = date_tag.get_text(strip=True) if date_tag else "Unknown"

    # Category — from .group-meta links, take the most specific (last real one)
    cat_links = [
        a.get_text(strip=True)
        for a in soup.select(".group-meta a")
        if a.get("href", "").startswith("/documents/app-categories")
    ]
    doc["category"] = cat_links[-1] if cat_links else "Unknown"

    # Transcript / body text
    body = (
        soup.select_one("div.field-docs-content")
        or soup.select_one("div.field--name-field-docs-body")
        or soup.select_one("div.field--name-body")
    )

    if body:
        text = body.get_text(separator="\n").strip()
    else:
        # Fallback: largest paragraph-rich div
        divs = soup.find_all("div")
        best = max(divs, key=lambda d: len(d.find_all("p")), default=None)
        text = best.get_text(separator="\n").strip() if best else ""

    # Strip boilerplate footer UCSB appends ("Online by Gerhard Peters...")
    text = re.sub(
        r"(?s)(Franklin D\. Roosevelt|FDR),?\s+"
        r"[\w\s,\.]+Online by Gerhard Peters.*$",
        "",
        text
    ).strip()

    if len(text) < 100:
        print(f"    WARNING: short text ({len(text)} chars) — may be a stub")

    doc["text"] = text
    return doc


# ── Step 3: Save individual file ──────────────────────────────────────────────

def save_doc(doc, index):
    filename = f"{index:04d}_{slugify(doc['title'])}.txt"
    path = os.path.join(TXT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Title:    {doc['title']}\n")
        f.write(f"Date:     {doc['date']}\n")
        f.write(f"Category: {doc['category']}\n")
        f.write(f"URL:      {doc['url']}\n")
        f.write("=" * 72 + "\n\n")
        f.write(doc["text"])
    return filename


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(TXT_DIR, exist_ok=True)

    # --- Collect links ---
    docs = get_all_doc_links()

    if not docs:
        print("\nNo documents found. The index URL may need updating.")
        print("Try opening this in a browser to check:")
        print(INDEX_URL.format(page=0))
        return

    # --- Scrape each doc ---
    print(f"\nScraping {len(docs)} documents (this will take a while)...\n")
    results = []
    for i, doc in enumerate(docs, 1):
        print(f"  [{i:04d}/{len(docs)}] {doc['title'][:65]}")
        scraped = scrape_document(doc)
        if scraped and scraped.get("text"):
            filename = save_doc(scraped, i)
            scraped["filename"] = filename
            results.append(scraped)
        time.sleep(DELAY)

    # --- Combined corpus ---
    print(f"\nWriting combined corpus → {CORPUS_FILE}")
    with open(CORPUS_FILE, "w", encoding="utf-8") as f:
        for s in results:
            f.write(f"\n{'='*72}\n")
            f.write(f"TITLE:    {s['title']}\n")
            f.write(f"DATE:     {s['date']}\n")
            f.write(f"CATEGORY: {s['category']}\n")
            f.write(f"URL:      {s['url']}\n")
            f.write(f"{'='*72}\n\n")
            f.write(s["text"])
            f.write("\n\n")

    # --- Metadata CSV ---
    print(f"Writing metadata → {META_FILE}")
    with open(META_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["filename","title","date","category","url","word_count","char_count"],
            extrasaction="ignore"
        )
        writer.writeheader()
        for s in results:
            s["word_count"]  = len(s.get("text","").split())
            s["char_count"]  = len(s.get("text",""))
            writer.writerow(s)

    # --- Summary ---
    total_words = sum(s.get("word_count", 0) for s in results)
    total_chars = sum(s.get("char_count", 0) for s in results)
    cats = {}
    for s in results:
        cats[s["category"]] = cats.get(s["category"], 0) + 1

    print(f"\n{'='*55}")
    print(f"  Done!  Saved {len(results)} FDR documents")
    print(f"  Total words : {total_words:,}")
    print(f"  Total chars : {total_chars:,}")
    print(f"\n  By category:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {count:4d}  {cat}")
    print(f"\n  Output: {OUTPUT_DIR}/")
    print(f"    ├─ txt/                 ({len(results)} files)")
    print(f"    ├─ fdr_ucsb_corpus.txt")
    print(f"    └─ fdr_ucsb_metadata.csv")
    print(f"{'='*55}")

    # Tip if doc count seems low
    if len(results) < 50:
        print("\n  ⚠️  Low doc count. If this looks wrong, open the index URL")
        print(f"     in a browser and check the page structure:")
        print(f"     {INDEX_URL.format(page=0)}")


if __name__ == "__main__":
    main()