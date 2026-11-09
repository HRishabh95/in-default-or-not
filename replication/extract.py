"""Independent replication, step 1: extract filings and in-scope holdings from raw N-PORT bulk zips.

Writes (in this folder):
  filings.pkl   one row per (zip, accession) for NPORT-P / NPORT-P/A: FILING_DATE, REPORT_DATE, SUB_TYPE, CIK,
                SERIES_ID, FUND
  holdings.pkl  every FUND_REPORTED_HOLDING row whose normalised ISSUER_CUSIP is in cusips.csv, joined to
                DEBT_SECURITY (IS_DEFAULT, ARE_ANY_INTEREST_PAYMENT), with ZIP tag
"""
import glob
import io
import os
import sys
import zipfile
from multiprocessing import Pool

import pandas as pd

ROOT = os.environ.get("REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data/interim/late_flags/replication")
INP = os.path.join(ROOT, "data/interim/late_flags/replication_inputs")
READ = dict(dtype=str, sep="\t", quoting=3, keep_default_na=False, on_bad_lines="warn")
CHUNK = 2_000_000

CUSIPS = set(pd.read_csv(os.path.join(INP, "cusips.csv"), dtype=str)["CUSIP"].str.strip().str.upper())


def read_table(zf, name, usecols):
    with zf.open(name) as fh:
        return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"), usecols=usecols, **READ)


def filings_for(path):
    tag = os.path.basename(path).split("_")[0]
    with zipfile.ZipFile(path) as zf:
        sub = read_table(zf, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "SUB_TYPE", "REPORT_DATE"])
        reg = read_table(zf, "REGISTRANT.tsv", ["ACCESSION_NUMBER", "CIK"])
        fri = read_table(zf, "FUND_REPORTED_INFO.tsv", ["ACCESSION_NUMBER", "SERIES_ID", "NET_ASSETS"])
    sub = sub[sub["SUB_TYPE"].str.strip().isin(["NPORT-P", "NPORT-P/A"])]
    reg = reg.drop_duplicates("ACCESSION_NUMBER")
    fri = fri.drop_duplicates("ACCESSION_NUMBER")
    df = sub.merge(reg, on="ACCESSION_NUMBER", how="left").merge(fri, on="ACCESSION_NUMBER", how="left")
    df = df.fillna("")
    df["ZIP"] = tag
    return df


def holdings_for(path):
    tag = os.path.basename(path).split("_")[0]
    parts = []
    with zipfile.ZipFile(path) as zf:
        with zf.open("FUND_REPORTED_HOLDING.tsv") as fh:
            it = pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                             usecols=["ACCESSION_NUMBER", "HOLDING_ID", "ISSUER_CUSIP", "BALANCE", "UNIT",
                                      "CURRENCY_CODE", "CURRENCY_VALUE", "PAYOFF_PROFILE", "ASSET_CAT"],
                             chunksize=CHUNK, **READ)
            for ch in it:
                c = ch["ISSUER_CUSIP"].str.strip().str.upper()
                m = c.isin(CUSIPS)
                if m.any():
                    sel = ch[m].copy()
                    sel["CUSIP"] = c[m]
                    parts.append(sel)
        h = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        ids = set(h["HOLDING_ID"]) if len(h) else set()
        dparts = []
        with zf.open("DEBT_SECURITY.tsv") as fh:
            it = pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                             usecols=["HOLDING_ID", "IS_DEFAULT", "ARE_ANY_INTEREST_PAYMENT"],
                             chunksize=CHUNK, **READ)
            for ch in it:
                m = ch["HOLDING_ID"].isin(ids)
                if m.any():
                    dparts.append(ch[m])
    d = pd.concat(dparts, ignore_index=True) if dparts else pd.DataFrame(
        columns=["HOLDING_ID", "IS_DEFAULT", "ARE_ANY_INTEREST_PAYMENT"])
    ndup = int(d["HOLDING_ID"].duplicated().sum())
    d = d.drop_duplicates("HOLDING_ID")
    if len(h):
        h = h.merge(d, on="HOLDING_ID", how="left")
        h["HAS_DEBT_ROW"] = h["IS_DEFAULT"].notna()
        h = h.fillna({"IS_DEFAULT": "", "ARE_ANY_INTEREST_PAYMENT": ""})
        h["ZIP"] = tag
    print(f"{tag}: {len(h)} holdings rows, {ndup} duplicate debt rows", flush=True)
    return h


if __name__ == "__main__":
    zips = sorted(glob.glob(os.path.join(ROOT, "data/raw/nport/*_nport.zip")))
    print(len(zips), "zips", flush=True)
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 4) as pool:
        f = pd.concat(pool.map(filings_for, zips), ignore_index=True)
        f.to_pickle(os.path.join(OUT, "filings.pkl"))
        print("filings", len(f), flush=True)
        h = pd.concat(pool.map(holdings_for, zips), ignore_index=True)
        h.to_pickle(os.path.join(OUT, "holdings.pkl"))
        print("holdings", len(h), flush=True)
