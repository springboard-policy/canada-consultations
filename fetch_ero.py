"""
Environmental Registry of Ontario (ERO) — Open Notices Fetcher
==============================================================
Scrapes the ERO search page for notices whose comment period is currently
open for public input.

Source: https://ero.ontario.ca/search?search=&f[0]=ero_status:open

Each result card on the search page has this structure:
    <div class="notice-teaser small-12 column">
      <h3 class="node-title"><a href="/notice/019-XXXX">Title</a></h3>
      <div class="field-name-field-pars-type">
        <div class="field-items">Policy</div>
      </div>
      <div class="row">
        <div class="field_label">Notice stage</div>
        <div class="field-items">
          <span class="ero-status-indicator">Proposal</span>
          <span class="ero-status-indicator">Open</span>
        </div>
      </div>
      <div class="row">
        <div class="field_label">Comment period</div>
        <div class="field-items">
          May 20, 2026 - June 19, 2026 (30 days) Open
        </div>
      </div>
      ...
    </div>

Run it like this (after activating your virtual environment):
    python fetch_ero.py
"""

import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL   = "https://ero.ontario.ca"
SEARCH_URL = f"{BASE_URL}/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}

# Comment period format: "May 20, 2026 - June 19, 2026 (30 days) Open"
# We want the end date — the date after the dash, before the " ("
_CP_END_RE = re.compile(
    r"-\s*((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4})\s+\(",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_page(page: int = 0) -> BeautifulSoup | None:
    params = {"search": "", "f[0]": "ero_status:open", "page": page}
    try:
        r = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(" ", strip=True).lower()
        if "maintenance" in page_text and "be back soon" in page_text:
            raise RuntimeError("ERO site is under maintenance.")
        return soup
    except requests.RequestException as e:
        print(f"  [warning] Could not fetch ERO page {page}: {e}", file=sys.stderr)
        return None


def _parse_deadline(cp_text: str) -> tuple[date | None, str]:
    """Extract comment period end date from text like 'May 20, 2026 - June 19, 2026 (30 days) Open'."""
    m = _CP_END_RE.search(cp_text)
    if m:
        try:
            d = datetime.strptime(m.group(1), "%B %d, %Y").date()
            days_left = (d - date.today()).days
            if days_left < 0:
                return None, f"{d.strftime('%B %d, %Y')} (closed)"
            elif days_left == 0:
                return d, f"{d.strftime('%B %d, %Y')} (closes TODAY)"
            else:
                return d, f"{d.strftime('%B %d, %Y')} ({days_left} days remaining)"
        except ValueError:
            pass
    return None, "Not specified — check the ERO website"


def _parse_cards(soup: BeautifulSoup) -> list[dict]:
    """Extract open-comment-period notices from a search result page."""
    today   = date.today()
    results = []

    for card in soup.find_all("div", class_="notice-teaser"):
        # Title and URL
        title_el = card.find("h3", class_="node-title")
        if not title_el:
            continue
        a = title_el.find("a", href=True)
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        url   = BASE_URL + a["href"]

        # Only include notices whose comment period is currently Open
        statuses = [s.get_text(strip=True) for s in card.find_all("span", class_="ero-status-indicator")]
        if "Open" not in statuses:
            continue

        # Comment period text (for deadline extraction)
        cp_text = ""
        for row in card.find_all("div", class_="row"):
            label = row.find("div", class_="field_label")
            if label and "Comment period" in label.get_text():
                items = row.find("div", class_="field-items")
                if items:
                    cp_text = items.get_text(" ", strip=True)
                break

        deadline_obj, deadline_str = _parse_deadline(cp_text)

        # Skip if the deadline has already passed
        if deadline_obj is not None and deadline_obj < today:
            continue

        # Notice type (present for policy/regulatory notices; absent for permits/approvals)
        notice_type = ""
        type_field = card.find("div", class_="field-name-field-pars-type")
        if type_field:
            items_el = type_field.find("div", class_="field-items")
            if items_el:
                notice_type = items_el.get_text(strip=True)

        results.append({
            "source":     "Environmental Registry of Ontario",
            "title":      title,
            "department": "Government of Ontario",
            "summary":    notice_type,
            "deadline":   deadline_str,
            "url":        url,
        })

    return results


# ── Main fetch function ───────────────────────────────────────────────────────

def fetch() -> list[dict]:
    """Fetch all ERO notices with a currently open comment period."""
    print("Fetching Environmental Registry of Ontario open notices ...")

    results  = []
    seen_urls = set()

    page = 0
    while True:
        soup = _get_page(page)
        if soup is None:
            if page == 0:
                raise RuntimeError("Could not fetch ERO search page.")
            break

        cards = _parse_cards(soup)
        new_cards = [c for c in cards if c["url"] not in seen_urls]
        for c in new_cards:
            seen_urls.add(c["url"])
        results.extend(new_cards)

        # Check for a next-page link
        next_link = soup.find("a", title="Go to next page") or \
                    soup.find("li", class_="pager-next")
        if not next_link or not new_cards:
            break
        page += 1
        if page > 15:   # safety cap
            break

    print(f"  Found {len(results)} ERO notice(s) with open comment periods.")
    return results


# ── Standalone output ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    items = fetch()
    if not items:
        print("No open ERO notices found.")
    else:
        print(f"\nFound {len(items)} open notice(s):\n")
        for i, item in enumerate(items, 1):
            print(f"[{i}] {item['title']}")
            print(f"    Type     : {item['summary'] or '(instrument/permit)'}")
            print(f"    Deadline : {item['deadline']}")
            print(f"    URL      : {item['url']}")
            print()
