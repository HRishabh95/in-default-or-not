"""Independent replication, step 3: check EVENT_DATE against EDGAR 8-K text for 10 random cases (seed 7)."""
import html
import json
import os
import re
import time
import urllib.request
from datetime import date, datetime, timedelta

import pandas as pd

ROOT = os.environ.get("REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data/interim/late_flags/replication")
UA = {"User-Agent": os.environ["SEC_USER_AGENT"]}
_last = [0.0]


def get(url):
    wait = 0.25 - (time.time() - _last[0])  # <= 4 requests per second
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"\b({MONTHS})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", re.I)
NUM_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def text_of(doc):
    doc = re.sub(r"(?is)<(script|style).*?</\1>", " ", doc)
    doc = re.sub(r"(?s)<[^>]+>", " ", doc)
    doc = html.unescape(doc).replace("\xa0", " ")
    return re.sub(r"\s+", " ", doc)


def dates_in(s):
    out = []
    for m in DATE_RE.finditer(s):
        try:
            out.append(datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date())
        except ValueError:
            pass
    for m in NUM_RE.finditer(s):
        try:
            out.append(date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
        except ValueError:
            pass
    return out


PET_RE = re.compile(r"chapter\s+(11|7)\b", re.I)
VERB_RE = re.compile(r"\b(filed|commenced)\b", re.I)


def item103_sections(text):
    """Text of each 'Item 1.03' occurrence up to the next 'Item N.NN' heading."""
    out = []
    for m in re.finditer(r"Item\s*1\.03", text, re.I):
        nxt = re.search(r"Item\s*\d\.\d\d", text[m.end() + 20:], re.I)
        end = m.end() + 20 + nxt.start() if nxt else m.end() + 4000
        out.append(text[m.start():end])
    return out


def petition_date(text, filing_date):
    """First sentence (Item 1.03 body first, else whole document) mentioning Chapter 11/7 with 'filed' or
    'commenced' and a date; returns (latest date in it not after the 8-K filing date, sentence)."""
    for scope in item103_sections(text) + [text]:
        for sent in re.split(r"(?<!Inc\.)(?<!Corp\.)(?<!Co\.)(?<!No\.)(?<!U\.S\.)(?<=[.;])\s+(?=[A-Z])", scope):
            if PET_RE.search(sent) and VERB_RE.search(sent):
                ds = [d for d in dates_in(sent) if d <= filing_date]
                if ds:
                    return max(ds), sent[:300]
    return None, ""


def filings_of(cik10):
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik10}.json"))
    frames = [pd.DataFrame(sub["filings"]["recent"])]
    for f in sub["filings"].get("files", []):
        frames.append(pd.DataFrame(json.loads(get("https://data.sec.gov/submissions/" + f["name"]))))
    return pd.concat(frames, ignore_index=True)


def main():
    cases = pd.read_csv(os.path.join(ROOT, "data/interim/late_flags/replication_inputs/cases.csv"), dtype=str)
    pick = cases.sample(10, random_state=7)
    rows = []
    for _, c in pick.iterrows():
        ev = date.fromisoformat(c.EVENT_DATE)
        cik10 = c.CIK.zfill(10)
        res = dict(CASE_ID=c.CASE_ID, NAME=c.NAME, EVENT_DATE=c.EVENT_DATE, STATUS="NOT_FOUND",
                   PETITION_DATE_8K="", ACCESSION="", EVIDENCE="")
        try:
            fl = filings_of(cik10)
        except Exception as e:  # noqa: BLE001
            res["EVIDENCE"] = f"submissions fetch failed: {e}"
            rows.append(res)
            continue
        fl = fl[fl["form"].isin(["8-K", "8-K/A"])].copy()
        fl["fd"] = pd.to_datetime(fl["filingDate"]).dt.date
        win = fl[(fl["fd"] >= ev - timedelta(days=5)) & (fl["fd"] <= ev + timedelta(days=60))]
        # Item 1.03-tagged 8-Ks first, then untagged, each in filing-date order; first one yielding a date decides
        win = win.assign(not103=~win["items"].fillna("").str.contains("1.03", regex=False))
        win = win.sort_values(["not103", "fd"])
        for _, f in win.head(8).iterrows():
            acc = f["accessionNumber"]
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(c.CIK)}/{acc.replace('-', '')}/"
                   f"{f['primaryDocument']}")
            try:
                t = text_of(get(url))
            except Exception as e:  # noqa: BLE001
                res["EVIDENCE"] += f" fetch failed {acc}: {e};"
                continue
            d, sent = petition_date(t, f["fd"])
            if d is not None:
                ok = abs((d - ev).days) <= 1
                res.update(STATUS="MATCH" if ok else "MISMATCH", PETITION_DATE_8K=d.isoformat(), ACCESSION=acc,
                           FILING_DATE_8K=f["filingDate"], ITEMS=f["items"], EVIDENCE=sent)
                break
        rows.append(res)
        print(res["CASE_ID"], res["STATUS"], res["PETITION_DATE_8K"], flush=True)
    out = pd.DataFrame(rows)
    out.to_json(os.path.join(OUT, "event_check.json"), orient="records", indent=1)
    print(out[["CASE_ID", "NAME", "EVENT_DATE", "PETITION_DATE_8K", "STATUS", "ACCESSION"]].to_string())


if __name__ == "__main__":
    main()
