# Canadian Consultations Digest

A daily briefing tool that monitors eight Canadian government sources for open public consultations and automatically publishes a summary webpage every morning.

**Live site:** https://springboard-policy.github.io/canada-consultations/

---

## What it does

Every morning at 5:00 AM ET, the tool automatically:

1. Checks eight government sources for open consultations (see list below)
2. Filters out technical/scientific items that aren't relevant to a policy consultant
3. Generates a clean HTML page with all active consultations, colour-coded by urgency
4. Publishes the page to a public website (GitHub Pages)

The result is a single webpage you can open each morning to see everything that's currently open for public comment across federal and Ontario governments — sorted, filtered, and ready to act on.

---

## The sources

| Code | Source | What it tracks |
|------|--------|----------------|
| HC | House of Commons Committees | Open calls for written briefs, with submission deadlines |
| CG | Canada Gazette Part I | Proposed federal regulations open for public comment |
| FED | Canada.ca | Federal government consultations from the Open Government Portal |
| ON | Ontario Regulatory Registry | Ontario regulatory proposals open for comment |
| ONT | Ontario.ca | Ontario government consultations directory |
| OLA | Ontario Legislature | Committee hearings notices with submission deadlines |
| SEN | Senate of Canada | Committee studies referred in the last 30 days |
| FIN | Department of Finance Canada | Active Finance Canada consultations |

---

## How it was built

This project was built iteratively through a conversation with Claude Code (Anthropic's AI coding assistant). The instructions below follow the same sequence.

### The starting idea

The goal was a single daily briefing that pulls together consultations from multiple government sources — the kind of thing a policy consultant would otherwise spend an hour assembling manually each morning. The key requirements were:

- Monitor multiple sources (federal and Ontario)
- Filter out technical/scientific consultations not relevant to policy work
- Show urgency clearly (closing soon vs. plenty of time)
- Update automatically every morning without any manual action
- Be readable in a browser, not a spreadsheet

### Step 1: One scraper per source

Each source has its own Python file (`fetch_*.py`). They were built one at a time, tested individually, then combined. Each scraper returns a standard list of dictionaries with fields like `title`, `deadline`, `department`, `summary`, and `url`.

**Key decisions made along the way:**

- **Canada Gazette** (`fetch_gazette.py`): Scrapes the year index page, finds the most recent weekly issue, then visits each proposed regulation page to extract the comment deadline. The deadline is calculated by adding the "within X days" number from the text to the issue publication date.

- **Canada.ca** (`fetch_canada_ca.py`): Downloads a CSV file published by the Open Government Portal. Filters to open consultations with future deadlines only — the raw data includes many stale "open" rows with past deadlines.

- **House of Commons** (`fetch_hoc.py`): Starts from the [Participate page](https://www.ourcommons.ca/Committees/en/Participate), which lists every committee study currently accepting briefs. Visits each study page to extract the deadline from the "Participate" section. Studies without a "Participate" section (no open call) are excluded.

- **Senate** (`fetch_senate.py`): The Senate doesn't publish formal call-for-briefs deadlines the way the House of Commons does. The scraper calls an internal API that powers the Senate's Studies & Bills table, filtered to studies referred in the last 30 days (recently started = most likely actively relevant). Briefs can be emailed to ctm@sen.parl.gc.ca at any time during a study.

- **Ontario Regulatory Registry** (`fetch_ontario.py`): The Ontario Registry runs on a Spring Boot backend with a public API key (fetched dynamically from the site's config endpoint each run). The scraper queries the API for proposals with open comment periods.

- **Ontario.ca** (`fetch_ontario_ca.py`): Scrapes the Ontario.ca consultations directory page for items marked as Open or Ongoing, skipping any with past end dates.

- **Ontario Legislature** (`fetch_ola.py`): Checks the OLA committee hearings notices page. Returns an empty list when the standard "no notices" message is shown.

- **Department of Finance** (`fetch_finance.py`): Fetches the Finance Canada consultations page, then visits each active consultation page individually to extract the deadline (looking for patterns like "until April 13, 2026" or "by March 13, 2026").

### Step 2: Keyword filter

Many consultations are too technical to be relevant to a policy generalist — things like proposed livestock feed ingredient approvals or recovery strategies for specific fish species. Rather than filtering by department (which would cut legitimate policy consultations from the same departments), the tool filters by **title keywords**.

The blocklist is defined in `generate_digest.py` under `BLOCKLIST`. Items whose titles match any of the ~50 phrases are hidden from the main view but shown in a collapsed "X items not shown" note at the bottom of each section, so you can still check what's being filtered.

**Categories filtered out:** species at risk, pesticides and agrochemicals, fisheries and wildlife biology, marine technical, food safety technical, drug and health product approvals, pharmaceutical technical, medical devices, chemical and substance registration, environmental remediation and contamination, mining and geology, engineering and infrastructure, forestry, nuclear, transport technical, technical standards and measurement, and Gazette housekeeping items.

### Step 3: HTML digest with Jinja2

`generate_digest.py` imports all eight scrapers, runs them, and uses a Jinja2 template to render a styled HTML file (`digest_YYYY-MM-DD.html`).

Items are colour-coded by urgency:
- **Red** — closes within 7 days
- **Orange** — closes within 30 days
- **Green** — closes in 30+ days (or no specified deadline with a date)
- **Purple** — Senate studies (no fixed deadline)

### Step 4: Automatic daily updates via GitHub Actions

The digest is published using **GitHub Pages** (free static website hosting from GitHub). A workflow file (`.github/workflows/daily_digest.yml`) runs every morning at 10:00 UTC (5:00 AM ET), generates the digest, and commits the result to `docs/index.html` — which GitHub Pages serves as the website.

The workflow also includes:
- A `paths-ignore` rule so committing the output file doesn't re-trigger the workflow
- A `workflow_dispatch` trigger so you can manually run it from the GitHub website
- A `push` trigger so changes to the code are reflected immediately

### Step 5: UI features

- **Sticky bar** — the section tabs (HC, CG, FED, etc.) and urgency filter buttons stay visible as you scroll
- **Urgency filter buttons** — toggle which urgency levels are shown (closes <7 days, <30 days, 30+ days, no fixed deadline)
- **Collapsible sections** — click any section header to collapse it
- **Keyword search** — type in the search box to filter items live across all sections
- **"NEW" badges** — items that weren't in yesterday's digest are marked with a green NEW pill. The tool saves a list of item keys in `previous_items.json` after each run and compares against it the next day
- **Change summary** — the page header shows how many items are new since yesterday and how many are closing within 7 days

---

## File structure

```
canada-consultations/
├── fetch_gazette.py        # Canada Gazette Part I scraper
├── fetch_canada_ca.py      # Canada.ca federal consultations scraper
├── fetch_hoc.py            # House of Commons committees scraper
├── fetch_senate.py         # Senate of Canada committees scraper
├── fetch_ontario.py        # Ontario Regulatory Registry scraper
├── fetch_ontario_ca.py     # Ontario.ca consultations scraper
├── fetch_ola.py            # Ontario Legislature hearings scraper
├── fetch_finance.py        # Department of Finance Canada scraper
├── generate_digest.py      # Combines all scrapers, renders HTML template
├── requirements.txt        # Python dependencies
├── previous_items.json     # Item keys from last run (for NEW badge tracking)
├── run_digest.bat          # Windows batch file for local Task Scheduler runs
├── task_definition.xml     # Windows Task Scheduler config (optional local runner)
├── docs/
│   └── index.html          # Published website (auto-generated, committed by workflow)
└── .github/
    └── workflows/
        └── daily_digest.yml    # GitHub Actions workflow
```

---

## How to set it up yourself

### Prerequisites

- A GitHub account
- Python 3.12 or later installed locally (for testing)
- Basic comfort with the command line

### Local setup (for testing)

```bash
# Clone the repo
git clone https://github.com/springboard-policy/canada-consultations.git
cd canada-consultations

# Create and activate a virtual environment
python -m venv venv
source venv/Scripts/activate   # Windows
# source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Run the digest
python generate_digest.py

# Open the result
start digest_$(date +%Y-%m-%d).html   # Windows
# open digest_$(date +%Y-%m-%d).html  # Mac
```

### Publishing to your own GitHub Pages site

1. Fork this repository on GitHub
2. Go to your fork's **Settings → Pages**
3. Set source to **Deploy from a branch**, branch **main**, folder **/docs**
4. Save — your site will be live at `https://YOUR-USERNAME.github.io/canada-consultations/`

The GitHub Actions workflow will run automatically every morning. You can also trigger it manually from the **Actions** tab on GitHub.

---

## How to extend it

### Adding a new source

1. Create a new `fetch_sourcename.py` file. The file must have a `fetch()` function that returns a list of dictionaries. Each dictionary should include at minimum:
   - `source` — name of the source (string)
   - `title` — consultation title (string)
   - `deadline` — deadline string, e.g. `"April 30, 2026 (57 days remaining)"` (string or None)
   - `url` — link to the consultation (string)
   - Optionally: `department`, `committee`, `summary`

2. In `generate_digest.py`, add `import fetch_sourcename` at the top and add a new entry to the `sources` list in `collect_all()` following the same pattern as the existing entries.

3. Update the subtitle ("Eight sources checked") and footer accordingly.

### Adjusting the keyword filter

Edit the `BLOCKLIST` list in `generate_digest.py`. Each entry is a phrase (case-insensitive) that, if found anywhere in a consultation's title, will hide it from the main view.

### Changing the Senate lookback window

Edit `RECENT_DAYS = 30` in `fetch_senate.py`. Increase to see more (older) studies, decrease to see fewer.

---

## Dependencies

```
requests          # HTTP requests to government websites
beautifulsoup4    # HTML parsing
python-dateutil   # Date parsing
jinja2            # HTML templating
```

Note: `lxml` is listed as an alternative HTML parser but is not used — it requires a C compiler to install on Windows. All scrapers use `html.parser` instead, which is built into Python.
