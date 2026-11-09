"""Independent event list: 8-K filings that report Item 1.03 (bankruptcy or receivership) or Item 2.04
(triggering events that accelerate a financial obligation), found through EDGAR full-text search.

Nothing here reads N-PORT. Dates are kept apart:
- EVENT_DATE: the 8-K "date of report" (date of earliest event reported), `period_ending` in the index;
- PUBLIC_DATE: the 8-K filing date, when the event became public on EDGAR.

Output: data/interim/late_flags/events/8k_hits.parquet (one row per 8-K filing).
Usage: SEC_USER_AGENT="Name email" python src/late_flags/fetch_events.py
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/interim/late_flags/events"
UA = os.environ["SEC_USER_AGENT"]
QUERIES = ['"Chapter 11"', '"Chapter 7"', '"acceleration"']  # forms filter "8-K,8-K/A" silently drops hits: use "8-K" only
ITEMS = {"1.03", "2.04"}


def get(params):
    url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception:
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(url)


def months(start="2019-07", end="2026-10"):
    p = pd.period_range(start, end, freq="M")
    return [(str(x.start_time.date()), str(x.end_time.date())) for x in p]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for q in QUERIES:
        for s, e in months():
            frm = 0
            while True:
                d = get({"q": q, "forms": "8-K", "startdt": s, "enddt": e, "from": frm})
                hits = d["hits"]["hits"]
                for x in hits:
                    src = x["_source"]
                    items = set(src.get("items") or [])
                    if items & ITEMS:
                        rows.append({"ADSH": src["adsh"], "FILE": x["_id"].split(":")[1], "CIK": src["ciks"][0],
                                     "NAME": src["display_names"][0], "FORM": src["form"],
                                     "EVENT_DATE": src.get("period_ending"), "PUBLIC_DATE": src["file_date"],
                                     "ITEMS": ",".join(sorted(items)), "QUERY": q,
                                     "ALL_CIKS": ",".join(src["ciks"])})
                frm += len(hits)
                total = d["hits"]["total"]["value"]
                time.sleep(0.15)
                if not hits or frm >= min(total, 10000):
                    if total >= 10000:
                        print("WARNING truncated", q, s, total)
                    break
            print(q, s, len(rows), flush=True)
    df = pd.DataFrame(rows).drop_duplicates(["ADSH", "FILE"])
    df.to_parquet(OUT / "8k_hits.parquet")
    print("filings", df.ADSH.nunique(), "issuers", df.CIK.nunique())


if __name__ == "__main__":
    main()
