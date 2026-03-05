"""
Senate of Canada Committees — Active Studies Fetcher
=====================================================
Uses the Senate website's internal API to find committee studies that
have shown real meeting activity recently (last 45 days) or have a
meeting scheduled in the next 14 days.

This filters out studies that were referred long ago but haven't been
actively worked on — solving the problem where the Order of Reference
date is a poor proxy for actual committee activity.

Urgency is based on when the committee next meets:
  - Meeting within 7 days  → urgent (submit a brief soon)
  - Meeting within 30 days → soon
  - No upcoming meeting but met recently → open (still active)

To submit a brief: email ctm@sen.parl.gc.ca with the study title
and committee name, or contact the committee clerk directly.
"""

import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL      = "https://sencanada.ca"
SESSION       = "45-1"
SESSION_START = date(2025, 5, 26)

MEETINGS_API = f"{BASE_URL}/umbraco/surface/CommitteesAjax/GetTablePartialView"

UPCOMING_DAYS = 14   # show studies with meetings scheduled within this window
PAST_DAYS     = 45   # show studies that met within this many days

EXCLUDED_COMMITTEES = {"CIBA", "SELE", "HRRH", "LTVP", "SEBS"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; canada-consultations-bot/1.0; "
        "for personal research)"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

# ── Study-to-meeting matching ──────────────────────────────────────────────────

# Words that are too generic to be useful for matching
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "have",
    "been", "will", "shall", "into", "upon", "under", "over",
    "within", "which", "their", "they", "them", "these", "those",
    "such", "also", "any", "all", "per", "senate", "examine",
    "pursuant", "committee", "matter", "matters", "relating",
    "related", "certain", "respecting", "amend", "amending",
    "consideration", "witnesses", "witness", "report", "draft",
    "camera", "study", "order", "reference",
}


def _keywords(text: str) -> set:
    words = re.findall(r"[a-z][a-z0-9-]+", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def _matches(study_title: str, meeting_topic: str) -> bool:
    """
    True if a meeting topic plausibly corresponds to a study.
    Uses bill-number exact match first, then keyword overlap.
    """
    # Bill number is a highly specific identifier (e.g. "C-12", "S-205")
    bill_nums = re.findall(r"\b[CScs]-\d+\b", study_title)
    for bn in bill_nums:
        if bn.lower() in meeting_topic.lower():
            return True

    # Keyword overlap: require >= 40% of study's significant words to appear
    study_kw  = _keywords(study_title)
    topic_kw  = _keywords(meeting_topic)
    if not study_kw:
        return False
    return len(study_kw & topic_kw) / len(study_kw) >= 0.40


# ── API helpers ────────────────────────────────────────────────────────────────

def _fetch_meetings_tab(tab: str) -> list[tuple]:
    """
    Fetch one tab (UPCOMING or PAST) from the Senate meetings API.
    Returns list of (date, acronym, topic_text).
    """
    resp = requests.get(
        MEETINGS_API,
        params={
            "tableName":   "Meetings",
            "committeeId": 0,
            "pageSize":    250,
            "session":     SESSION,
            "TabSelected": tab,
        },
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()

    soup    = BeautifulSoup(resp.text, "html.parser")
    entries = []

    for row in soup.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Parse date from first cell
        date_raw = cells[0].get_text(" ", strip=True)[:12].strip()
        try:
            d = datetime.strptime(date_raw, "%b %d, %Y").date()
        except ValueError:
            continue

        # Committee acronym from links
        acronym = ""
        for a in row.find_all("a", href=True):
            m = re.search(r"/committees/([A-Z]+)/", a["href"])
            if m:
                acronym = m.group(1).upper()
                break
        if not acronym or acronym in EXCLUDED_COMMITTEES:
            continue

        topic = cells[2].get_text(" ", strip=True)
        entries.append((d, acronym, topic))

    return entries


def fetch_meeting_activity() -> dict:
    """
    Fetch recent past and upcoming meetings.
    Returns: { acronym: { "upcoming": [(date, topic)], "past": [(date, topic)] } }
    """
    today    = date.today()
    activity = {}

    past_entries     = _fetch_meetings_tab("PAST")
    upcoming_entries = _fetch_meetings_tab("UPCOMING")

    for d, acronym, topic in past_entries:
        if (today - d).days > PAST_DAYS:
            continue
        activity.setdefault(acronym, {"upcoming": [], "past": []})
        activity[acronym]["past"].append((d, topic))

    for d, acronym, topic in upcoming_entries:
        if (d - today).days > UPCOMING_DAYS:
            continue
        activity.setdefault(acronym, {"upcoming": [], "past": []})
        activity[acronym]["upcoming"].append((d, topic))

    return activity


def fetch_all_studies() -> list[dict]:
    """
    Fetch all studies from this session via the Studies API.
    No date filtering — that's done later using meeting activity.
    """
    resp = requests.get(
        MEETINGS_API,
        params={
            "tableName":   "Studies",
            "committeeId": 0,
            "pageSize":    250,
            "fromDate":    SESSION_START.isoformat(),
            "toDate":      "",
            "session":     SESSION,
        },
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()

    soup      = BeautifulSoup(resp.text, "html.parser")
    raw_items = soup.find_all("div", class_="cmt-site_v2-studybills-table-study-item")

    studies = []
    today   = date.today()

    for item in raw_items:
        title_tag = item.find(class_="cmt-site_v2-studybills-table-study-item-name")
        title = title_tag.get_text(" ", strip=True) if title_tag else "Untitled"

        committee_div  = item.find(class_="cmt-site_v2-studybills-table-study-item-committee")
        committee_link = committee_div.find("a") if committee_div else None
        committee_name = committee_link.get_text(strip=True) if committee_link else "Unknown"
        committee_href = committee_link["href"] if committee_link else ""
        m              = re.search(r"/committees/([a-zA-Z]+)/?", committee_href)
        acronym        = m.group(1).upper() if m else ""

        if acronym in EXCLUDED_COMMITTEES:
            continue

        oor_div  = item.find(class_="cmt-site_v2-studybills-table-study-item-oof")
        oor_date = None
        if oor_div:
            oor_text = oor_div.get_text(" ", strip=True)
            dm = re.search(r"\d{4}-\d{2}-\d{2}", oor_text)
            if dm:
                try:
                    oor_date = datetime.strptime(dm.group(0), "%Y-%m-%d").date()
                except ValueError:
                    pass

        clean_href = re.sub(r"/#\?.*$", "/", committee_href)
        if not clean_href.startswith("http"):
            clean_href = BASE_URL + clean_href
        studies_url = f"{BASE_URL}/en/committees/{acronym.lower()}/studiesandbills/{SESSION}"

        studies.append({
            "source":        "Senate of Canada Committees",
            "title":         title,
            "committee":     committee_name,
            "acronym":       acronym,
            "oor_date":      oor_date,
            "url":           studies_url,
            "committee_url": clean_href,
        })

    return studies


# ── Main public function ───────────────────────────────────────────────────────

def fetch_studies() -> list[dict]:
    """
    Return studies filtered to those with genuine recent meeting activity
    (met in last 45 days) or an upcoming meeting (next 14 days).
    Each result includes next_meeting and last_meeting date fields.
    """
    print(f"Fetching Senate committee studies (session {SESSION}) ...")
    try:
        all_studies = fetch_all_studies()
    except requests.RequestException as e:
        raise RuntimeError(f"Error fetching Senate studies: {e}")
    print(f"  Found {len(all_studies)} total studies in session.")

    print(f"  Fetching meeting activity (past {PAST_DAYS} days + next {UPCOMING_DAYS} days) ...")
    try:
        activity = fetch_meeting_activity()
    except requests.RequestException as e:
        raise RuntimeError(f"Error fetching Senate meeting schedule: {e}")

    today   = date.today()
    results = []

    for study in all_studies:
        acronym = study["acronym"]
        cmte    = activity.get(acronym, {"upcoming": [], "past": []})

        # Find the soonest upcoming meeting that matches this study
        next_meeting = None
        for d, topic in sorted(cmte["upcoming"], key=lambda x: x[0]):
            if _matches(study["title"], topic):
                next_meeting = d
                break

        # Find the most recent past meeting that matches this study
        last_meeting = None
        for d, topic in sorted(cmte["past"], key=lambda x: x[0], reverse=True):
            if _matches(study["title"], topic):
                last_meeting = d
                break

        if next_meeting is None and last_meeting is None:
            continue  # No meeting activity — skip

        study["next_meeting"] = next_meeting
        study["last_meeting"] = last_meeting

        if next_meeting:
            days = (next_meeting - today).days
            study["next_meeting_str"] = (
                f"{next_meeting.strftime('%B %d, %Y')}  ({days} day{'s' if days != 1 else ''} away)"
            )
        else:
            study["next_meeting_str"] = None

        if last_meeting:
            days_ago = (today - last_meeting).days
            study["last_meeting_str"] = (
                f"{last_meeting.strftime('%B %d, %Y')}  ({days_ago} day{'s' if days_ago != 1 else ''} ago)"
            )
        else:
            study["last_meeting_str"] = None

        results.append(study)

    # Sort: upcoming meeting soonest first, then most recent past meeting first
    def sort_key(s):
        if s["next_meeting"]:
            return (0, s["next_meeting"].toordinal())
        return (1, -s["last_meeting"].toordinal())

    results.sort(key=sort_key)
    print(f"  {len(results)} studies with recent or upcoming meeting activity.\n")
    return results


# ── Backwards-compat alias ────────────────────────────────────────────────────
fetch = fetch_studies


# ── Standalone output ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    studies = fetch_studies()
    if not studies:
        print("No studies with recent meeting activity found.")
        sys.exit(0)

    print(f"\n{'=' * 72}")
    print(f"  SENATE — STUDIES WITH RECENT/UPCOMING MEETING ACTIVITY ({SESSION})")
    print(f"  {len(studies)} studies  |  To submit: ctm@sen.parl.gc.ca")
    print(f"{'=' * 72}\n")

    for i, s in enumerate(studies, 1):
        print(f"[{i}] {s['title']}")
        print(f"    Committee   : {s['committee']} ({s['acronym']})")
        if s.get("next_meeting_str"):
            print(f"    Next meeting: {s['next_meeting_str']}  <-- submit brief before this")
        if s.get("last_meeting_str"):
            print(f"    Last met    : {s['last_meeting_str']}")
        print()
