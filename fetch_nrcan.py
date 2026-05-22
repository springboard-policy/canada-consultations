"""
Natural Resources Canada — Public Consultations Fetcher
=======================================================
Scrapes the NRCan public consultations and engagements page and visits
each ongoing consultation to extract its title, deadline, and summary.

Source: https://natural-resources.canada.ca/corporate/transparency/public-consultations-engagements

Run it like this (after activating your virtual environment):
    python fetch_nrcan.py
"""

import re
import time
import sys
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = "https://natural-resources.canada.ca"
MAIN_URL = f"{BASE_URL}/corporate/transparency/public-consultations-engagements"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; canada-consultations-bot/1.0; "
        "for personal research)"
    ),
}

_DEADLINE_RE = re.compile(
    r"(?:until|by|before|deadline[:\s]|closing date[:\s]|due\s+(?:date[:\s]|by\s)|"
    r"comments?\s+(?:must\s+be\s+)?(?:received|submitted|due)[:\s]+(?:by\s+)?)"
    r"((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(url: str, session: requests.Session) -> BeautifulSoup | None:
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [warning] Could not fetch {url}: {e}", file=sys.stderr)
        return None


def _find_deadline(text: str) -> tuple[date | None, str]:
    m = _DEADLINE_RE.search(text)
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
    return None, "Not specified — check the NRCan website"


def _get_summary(soup: BeautifulSoup) -> str:
    skip_phrases = {"date modified", "report a problem", "government of canada",
                    "share this page", "page details"}
    main = soup.find("main") or soup.find(id="wb-main") or soup
    for p in main.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) < 60:
            continue
        if any(s in text.lower() for s in skip_phrases):
            continue
        return text[:500]
    return ""


# ── Main scraping logic ───────────────────────────────────────────────────────

def _fetch_ongoing_links(soup: BeautifulSoup) -> list[tuple[str, str, bool]]:
    """
    Find the 'Ongoing consultations' section and return a list of
    (title, url, has_detail_page) for each item.

    - Linked items use their own URL; detail page will be visited.
    - Unlinked plain-text items fall back to MAIN_URL; no detail visit.
    - Links to gazette.gc.ca are skipped — those items are already
      covered (with proper deadlines) by the Gazette scraper.
    """
    items = []
    for heading in soup.find_all(["h2", "h3"]):
        if "ongoing" in heading.get_text(strip=True).lower():
            node = heading.find_next_sibling()
            while node:
                if node.name == "ul":
                    for li in node.find_all("li"):
                        a = li.find("a", href=True)
                        if a:
                            href = a["href"].strip()
                            if not href or href.startswith("#"):
                                continue
                            if not href.startswith("http"):
                                href = BASE_URL + href
                            # Skip links already covered by the Gazette scraper
                            if "gazette.gc.ca" in href:
                                continue
                            title = a.get_text(" ", strip=True)
                            if title:
                                items.append((title, href, True))
                        else:
                            # Unlinked plain-text item — capture with fallback URL
                            title = li.get_text(" ", strip=True)
                            if title:
                                items.append((title, MAIN_URL, False))
                    break
                if node.name in ("h2", "h3"):
                    break
                node = node.find_next_sibling()
            break
    return items


def _fetch_detail(title: str, url: str, session: requests.Session) -> dict:
    """Visit a consultation page and return deadline and summary."""
    soup = _get(url, session)
    if soup is None:
        return {"title": title, "deadline_obj": None, "deadline_str": "Not specified — check the NRCan website", "summary": ""}

    # Prefer the page's own <h1> as the title if available
    h1 = soup.find("h1")
    if h1:
        page_title = h1.get_text(" ", strip=True)
        if page_title:
            title = page_title

    body_text = soup.get_text(" ", strip=True)
    deadline_obj, deadline_str = _find_deadline(body_text)
    summary = _get_summary(soup)

    return {
        "title":        title,
        "deadline_obj": deadline_obj,
        "deadline_str": deadline_str,
        "summary":      summary,
    }


def fetch() -> list[dict]:
    """Fetch all ongoing Natural Resources Canada consultations."""
    print("Fetching Natural Resources Canada consultations ...")
    today   = date.today()
    session = requests.Session()

    soup = _get(MAIN_URL, session)
    if soup is None:
        raise RuntimeError("Could not fetch NRCan consultations page.")

    items = _fetch_ongoing_links(soup)
    if not items:
        print("  No ongoing consultation links found.")
        return []

    print(f"  Found {len(items)} ongoing item(s). Visiting detail pages ...")

    results = []
    for list_title, url, has_detail in items:
        if has_detail:
            time.sleep(0.3)
            detail = _fetch_detail(list_title, url, session)
        else:
            detail = {
                "title":        list_title,
                "deadline_obj": None,
                "deadline_str": "Not specified — check the NRCan website",
                "summary":      "",
            }

        deadline_obj = detail["deadline_obj"]
        if deadline_obj is not None and deadline_obj < today:
            continue

        results.append({
            "source":     "Natural Resources Canada — Consultations",
            "title":      detail["title"],
            "department": "Natural Resources Canada (NRCan)",
            "summary":    detail["summary"],
            "deadline":   detail["deadline_str"],
            "url":        url,
        })

    print(f"  Found {len(results)} active NRCan consultation(s).")
    return results


# ── Standalone output ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    items = fetch()
    if not items:
        print("No active NRCan consultations found.")
    else:
        print(f"\nFound {len(items)} active consultation(s):\n")
        for i, item in enumerate(items, 1):
            print(f"[{i}] {item['title']}")
            print(f"    Deadline : {item['deadline']}")
            print(f"    URL      : {item['url']}")
            if item["summary"]:
                print(f"    Summary  : {item['summary'][:200]}")
            print()
