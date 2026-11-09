"""Late Flags or Late Marks: extract every debt holding with its filing metadata from one N-PORT bulk data set.

No deduplication here: a bulk data set holds the filings disseminated in that calendar quarter, with
mixed report dates and with amendments (NPORT-P/A) that may supersede filings in earlier data sets.
`panel.py` keeps the latest filing per fund and report date across all data sets.

Outputs data/interim/late_flags/extract/{q}_filings.parquet and {q}_debt.parquet.
Usage: python src/late_flags/extract.py 2025q4 [...]
"""
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/nport"
OUT = ROOT / "data/interim/late_flags/extract"

HCOLS = ["ACCESSION_NUMBER", "HOLDING_ID", "ISSUER_NAME", "ISSUER_LEI", "ISSUER_TITLE", "ISSUER_CUSIP",
         "BALANCE", "UNIT", "CURRENCY_CODE", "CURRENCY_VALUE", "EXCHANGE_RATE", "PERCENTAGE",
         "PAYOFF_PROFILE", "ASSET_CAT", "ISSUER_TYPE", "INVESTMENT_COUNTRY", "FAIR_VALUE_LEVEL"]
DCOLS = ["HOLDING_ID", "MATURITY_DATE", "COUPON_TYPE", "ANNUALIZED_RATE", "IS_DEFAULT",
         "ARE_ANY_INTEREST_PAYMENT", "IS_ANY_PORTION_INTEREST_PAID"]


def read(z, name, usecols=None, chunks=False):
    kw = dict(sep="\t", dtype=str, usecols=usecols, quoting=3, keep_default_na=False,
              on_bad_lines="warn", encoding_errors="replace")
    f = z.open(name + ".tsv")
    return pd.read_csv(f, chunksize=1_000_000, **kw) if chunks else pd.read_csv(f, **kw)


def run(q):
    OUT.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(RAW / f"{q}_nport.zip")
    sub = read(z, "SUBMISSION")
    reg = read(z, "REGISTRANT", ["ACCESSION_NUMBER", "CIK", "REGISTRANT_NAME"])
    fri = read(z, "FUND_REPORTED_INFO", ["ACCESSION_NUMBER", "SERIES_NAME", "SERIES_ID", "NET_ASSETS"])
    f = sub.merge(reg, on="ACCESSION_NUMBER", how="left").merge(fri, on="ACCESSION_NUMBER", how="left")
    f = f[f.SUB_TYPE.str.startswith("NPORT-P")].copy()
    f["DATASET"] = q
    f.to_parquet(OUT / f"{q}_filings.parquet")

    d = pd.concat(ch for ch in read(z, "DEBT_SECURITY", DCOLS, chunks=True))
    ids = set(d.HOLDING_ID)
    h = pd.concat(ch[ch.HOLDING_ID.isin(ids)] for ch in read(z, "FUND_REPORTED_HOLDING", HCOLS, chunks=True))
    isin = pd.concat(ch[ch.HOLDING_ID.isin(ids)] for ch in
                     read(z, "IDENTIFIERS", ["HOLDING_ID", "IDENTIFIER_ISIN"], chunks=True))
    isin = isin[isin.IDENTIFIER_ISIN != ""].drop_duplicates("HOLDING_ID")
    x = h.merge(d, on="HOLDING_ID", how="inner").merge(isin, on="HOLDING_ID", how="left")
    x = x[x.ACCESSION_NUMBER.isin(set(f.ACCESSION_NUMBER))]
    x.to_parquet(OUT / f"{q}_debt.parquet")
    print(q, "filings", len(f), "debt holdings", len(x))


if __name__ == "__main__":
    for q in sys.argv[1:]:
        run(q)
