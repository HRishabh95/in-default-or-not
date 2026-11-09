"""Development pilot (2025q4 bulk data set only): reconcile the 2025q4 quick count at identical CUSIP and
report date.

Steps, each counted:
1. Filings: NPORT-P and NPORT-P/A; keep the latest filing per fund (series) and report date within this data set.
2. Holdings: 9-character CUSIPs that are not placeholders; one row per fund x CUSIP x report date (lots are
   summed; a fund is Y if any lot is Y and "mixed" if its own lots disagree).
3. Cells: CUSIP x report date with at least 3 funds.

Usage: python src/late_flags/pilot.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "data/interim/late_flags/extract"
OUT = ROOT / "data/interim/late_flags/pilot"
BAD_CUSIP = {"000000000", "999999999", "N/A", "NONE"}


def fund_rows(q):
    f = pd.read_parquet(EX / f"{q}_filings.parquet")
    f["RD"] = pd.to_datetime(f.REPORT_DATE, format="%d-%b-%Y", errors="coerce")
    f["FD"] = pd.to_datetime(f.FILING_DATE, format="%d-%b-%Y", errors="coerce")
    f["FUND_KEY"] = f.SERIES_ID.fillna("").str.strip()
    f.loc[f.FUND_KEY == "", "FUND_KEY"] = "CIK" + f.CIK.fillna("")
    f = f.sort_values(["FUND_KEY", "RD", "FD", "ACCESSION_NUMBER"])
    n0 = len(f)
    f["N_VERSIONS"] = f.groupby(["FUND_KEY", "RD"]).ACCESSION_NUMBER.transform("size")
    f = f.drop_duplicates(["FUND_KEY", "RD"], keep="last")
    return f, {"filings": n0, "fund_report_dates": len(f),
               "superseded": n0 - len(f), "amended_kept": int((f.SUB_TYPE == "NPORT-P/A").sum())}


def holdings(q, f):
    d = pd.read_parquet(EX / f"{q}_debt.parquet")
    n0 = len(d)
    d = d[d.ACCESSION_NUMBER.isin(set(f.ACCESSION_NUMBER))]
    n1 = len(d)
    c = d.ISSUER_CUSIP.str.strip().str.upper()
    ok = (c.str.len() == 9) & ~c.isin(BAD_CUSIP) & ~c.str.fullmatch(r"0+|9+|N/?A.*")
    d = d[ok].assign(CUSIP=c[ok])
    d = d.merge(f[["ACCESSION_NUMBER", "FUND_KEY", "RD", "FD", "CIK", "REGISTRANT_NAME", "NET_ASSETS"]],
                on="ACCESSION_NUMBER")
    for col in ["BALANCE", "CURRENCY_VALUE", "NET_ASSETS"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["Y"] = (d.IS_DEFAULT == "Y").astype(int)
    d["ARR"] = (d.ARE_ANY_INTEREST_PAYMENT == "Y").astype(int)
    g = d.groupby(["CUSIP", "RD", "FUND_KEY"]).agg(
        CIK=("CIK", "first"), REG=("REGISTRANT_NAME", "first"), FD=("FD", "first"), NAV=("NET_ASSETS", "first"),
        lots=("Y", "size"), y_any=("Y", "max"), y_min=("Y", "min"), arr_any=("ARR", "max"),
        value=("CURRENCY_VALUE", "sum"), balance=("BALANCE", "sum"), unit=("UNIT", "first"),
        cur=("CURRENCY_CODE", "first"), issuer=("ISSUER_NAME", "first"), title=("ISSUER_TITLE", "first"),
        fvl=("FAIR_VALUE_LEVEL", "first"), maturity=("MATURITY_DATE", "first"),
        rate=("ANNUALIZED_RATE", "first")).reset_index()
    g["own_lots_disagree"] = g.y_any != g.y_min
    return g, {"debt_rows": n0, "in_kept_filings": n1, "valid_cusip_rows": int(ok.sum()),
               "fund_cusip_dates": len(g), "own_lots_disagree": int(g.own_lots_disagree.sum())}


def cells(g, min_holders=3):
    c = g.groupby(["CUSIP", "RD"]).agg(n=("FUND_KEY", "size"), y=("y_any", "sum"),
                                       arr=("arr_any", "sum")).reset_index()
    c = c[c.n >= min_holders]
    any_y = c[c.y > 0]
    split = any_y[any_y.y < any_y.n]
    return c, {"cells_ge3": len(c), "cusips_ge3": int(c.CUSIP.nunique()),
               "cells_any_y": len(any_y), "cusips_any_y": int(any_y.CUSIP.nunique()),
               "cells_split": len(split), "cusips_split": int(split.CUSIP.nunique()),
               "split_share_of_any_y_cells": round(len(split) / max(len(any_y), 1), 4),
               "median_y_share_in_split": float((split.y / split.n).median()),
               "cells_any_arrears": int((c.arr > 0).sum()),
               "cells_y_without_arrears_any": int(((c.y > 0) & (c.arr == 0)).sum())}


def main(q="2025q4"):
    OUT.mkdir(parents=True, exist_ok=True)
    f, s1 = fund_rows(q)
    g, s2 = holdings(q, f)
    c, s3 = cells(g)
    rd = f.RD.dt.strftime("%Y-%m").value_counts().head(8).to_dict()
    # within-file check of the original quick count: same CUSIP but different report dates
    multi_rd = g.groupby("CUSIP").RD.nunique()
    s = {"dataset": q, "filings": s1, "holdings": s2, "cells": s3, "report_months_top": rd,
         "cusips_spanning_several_report_dates": int((multi_rd > 1).sum())}
    g.to_parquet(OUT / f"{q}_fund_cusip.parquet")
    c.to_parquet(OUT / f"{q}_cells.parquet")
    (OUT / f"{q}_pilot.json").write_text(json.dumps(s, indent=1, default=str))
    print(json.dumps(s, indent=1, default=str))


if __name__ == "__main__":
    main()
