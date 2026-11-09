"""Cross-data-set filing master and issuer dictionary. Reads no default or arrears flag.

1. filings_master.parquet: every NPORT-P / NPORT-P/A filing in every bulk data set, with FUND_KEY (series id,
   else registrant CIK), report date, filing date, and LATEST = the version kept for that fund and report date
   (latest filing date, then accession). Amendments filed in later data sets supersede earlier versions.
2. issuers.parquet: distinct issuer name, LEI and CUSIP-6 over all debt holdings, with holding counts, for
   linking independent events to securities.

Usage: python src/late_flags/panel.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "data/interim/late_flags/extract"
OUT = ROOT / "data/interim/late_flags/panel"


def datasets():
    return sorted(p.name.split("_")[0] for p in EX.glob("*_filings.parquet"))


def filings_master():
    f = pd.concat((pd.read_parquet(EX / f"{q}_filings.parquet") for q in datasets()), ignore_index=True)
    f["RD"] = pd.to_datetime(f.REPORT_DATE, format="%d-%b-%Y", errors="coerce")
    f["FD"] = pd.to_datetime(f.FILING_DATE, format="%d-%b-%Y", errors="coerce")
    f["FUND_KEY"] = f.SERIES_ID.fillna("").str.strip()
    f.loc[f.FUND_KEY == "", "FUND_KEY"] = "CIK" + f.CIK.fillna("").str.strip()
    f = f.drop_duplicates("ACCESSION_NUMBER").sort_values(["FUND_KEY", "RD", "FD", "ACCESSION_NUMBER"])
    g = f.groupby(["FUND_KEY", "RD"])
    f["N_VERSIONS"] = g.ACCESSION_NUMBER.transform("size")
    f["VERSION"] = g.cumcount() + 1
    f["LATEST"] = f.VERSION == f.N_VERSIONS
    f["NET_ASSETS"] = pd.to_numeric(f.NET_ASSETS, errors="coerce")
    return f


def norm_name(s):
    s = s.fillna("").str.upper().str.replace(r"[^A-Z0-9 ]", " ", regex=True)
    s = s.str.replace(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LLC|LP|LTD|PLC|HOLDINGS?|GROUP|THE|L P|L L C|SA|NV|AG)\b",
                      " ", regex=True)
    return s.str.split().str.join(" ")


def issuers():
    parts = []
    for q in datasets():
        d = pd.read_parquet(EX / f"{q}_debt.parquet", columns=["ISSUER_NAME", "ISSUER_LEI", "ISSUER_CUSIP"])
        d["CUSIP6"] = d.ISSUER_CUSIP.str.strip().str.upper().str[:6]
        parts.append(d.groupby(["ISSUER_NAME", "ISSUER_LEI", "CUSIP6"]).size().rename("n").reset_index())
    x = pd.concat(parts).groupby(["ISSUER_NAME", "ISSUER_LEI", "CUSIP6"]).n.sum().reset_index()
    x["NAME_N"] = norm_name(x.ISSUER_NAME)
    return x


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = filings_master()
    f.to_parquet(OUT / "filings_master.parquet")
    print("filings", len(f), "fund-report dates", int(f.LATEST.sum()), "with >1 version", int((f.N_VERSIONS > 1).sum()))
    x = issuers()
    x.to_parquet(OUT / "issuers.parquet")
    print("issuer name/LEI/CUSIP6 rows", len(x))


if __name__ == "__main__":
    main()
