"""Verify each case's first Item 1.03 8-K from its full submission text and take the petition date from it.

Form 8-K Item 1.03 covers the registrant or its parent. From the Item 1.03 section:
  PETITION_DATE: the date in the sentence that says voluntary petitions were filed or commenced (or an
                 involuntary petition was filed);
  VERIFY = PETITION when that date is between 30 days before and 1 day after the 8-K filing date (the 8-K date
           of report can be an earlier event such as a restructuring support agreement); PETITION_DATE is then
           the case's EVENT_DATE;
           LATER_STAGE when the petition date is earlier (the 8-K reports confirmation, sale or exit of a case that
           began before; such cases are unresolved, since their first public date is not observed here);
           NO_PETITION_SENTENCE / NO_TEXT otherwise (unresolved).
Excerpts are kept for audit.

Output: data/interim/late_flags/events/verified.parquet.
Usage: SEC_USER_AGENT="Name email" python src/late_flags/verify_events.py
"""
import html
import os
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

from link import cases

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "data/interim/late_flags/events"
UA = os.environ["SEC_USER_AGENT"]
MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
DATE = re.compile(MONTH + r"\s+\d{1,2},?\s+\d{4}")
PET = re.compile(r"(filed|commenced|file|filing of)\b[^.]{0,200}?\b(petitions?|cases? under chapter|chapter 11 cases?|chapter 7 cases?)\b"
                 r"|\bpetitions?\b[^.]{0,80}\bwere filed|involuntary petition", re.I)
ABBR = re.compile(r"\b(Inc|Corp|Co|Ltd|Cos|Bros|No|U\.S|S\.A|L\.P|N\.V|L\.L\.C|Mr|Ms|Jr|Del)\.")


def fetch(cik, adsh):
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{adsh}.txt"
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90).read()
            t = html.unescape(re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace")))
            return re.sub(r"\s+", " ", t)
        except Exception:
            time.sleep(2 + 3 * attempt)
    return None


def classify(t, public_date):
    m = re.search(r"item\s*1\.03\W{0,5}bankruptcy", t, re.I) or re.search(r"item\s*1\.03", t, re.I)
    seg = t[m.start():m.start() + 3000] if m else t[:20000]
    seg = ABBR.sub(lambda x: x.group(0)[:-1], seg)
    for sent in re.split(r"(?<=[.;])\s", seg):
        if PET.search(sent):
            dates = [pd.to_datetime(d.replace(",", ""), format="%B %d %Y", errors="coerce") for d in
                     (x.group(0) for x in DATE.finditer(sent))]
            dates = [d for d in dates if pd.notna(d) and d <= public_date + pd.Timedelta(days=1)]
            if dates:
                pd_ = max(dates)  # sentences also carry indenture or agreement dates; the petition is the latest
                gap = (public_date - pd_).days
                return ("PETITION" if -1 <= gap <= 30 else "LATER_STAGE"), pd_, sent[:500]
    return "NO_PETITION_SENTENCE", pd.NaT, seg[:500]


def main():
    c = cases()
    rows = []
    for r in c.itertuples():
        t = fetch(r.CIK, r.ADSH)
        time.sleep(0.15)
        if t is None:
            rows.append({"CASE_ID": r.CASE_ID, "VERIFY": "NO_TEXT", "PETITION_DATE": pd.NaT, "EXCERPT": ""})
            continue
        v, d, ex = classify(t, r.PUBLIC_DATE)
        rows.append({"CASE_ID": r.CASE_ID, "VERIFY": v, "PETITION_DATE": d, "EXCERPT": ex})
    v = pd.DataFrame(rows)
    v.to_parquet(EV / "verified.parquet")
    print(v.VERIFY.value_counts().to_dict())


if __name__ == "__main__":
    main()
