"""
Post new consultations to Slack.
Reads new_items.json written by generate_digest.py.
Exits silently if there are no new items.

Requires env var: SLACK_WEBHOOK_URL
"""
import json
import os
import sys
import urllib.request

DIGEST_URL = "https://springboard-policy.github.io/canada-consultations/"

webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
if not webhook_url:
    print("SLACK_WEBHOOK_URL not set — skipping Slack notification.")
    sys.exit(0)

with open("new_items.json", encoding="utf-8") as f:
    data = json.load(f)

items = data.get("items", [])
if not items:
    print("No new items — skipping Slack notification.")
    sys.exit(0)

count    = data["count"]
date_str = data["date"]
plural   = "s" if count != 1 else ""

lines = [f"*{count} new consultation{plural} — {date_str}*"]
for item in items:
    title  = item["title"]
    source = item["source"]
    url    = item.get("url", "")
    lines.append(f"• {'<' + url + '|' + title + '>' if url else title} — _{source}_")
lines.append(f"\n<{DIGEST_URL}|View full digest>")

payload = {"text": "\n".join(lines)}
body    = json.dumps(payload).encode()
req     = urllib.request.Request(
    webhook_url,
    data=body,
    headers={"Content-Type": "application/json"},
)
urllib.request.urlopen(req)
print(f"Slack: posted {count} new item(s).")
