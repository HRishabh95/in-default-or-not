"""Observation panel and primary units for the linked cases. This script prints counts only; it does not
tabulate default or arrears flags or prices (outcome.py does, after the protocol is frozen).

obs_versions.parquet: every version of every fund report holding an in-scope CUSIP (for amendment checks).
obs.parquet: latest version, one row per fund x CUSIP x report date (lots summed), for every linked
    non-ambiguous CUSIP; IN_SCOPE marks prepetition corporate debt (the others detect exchanges).
units.parquet: primary units = (case, CUSIP, fund) at the fund's first report date RD with
    PUBLIC_DATE < RD <= EVENT_DATE + 120 days and RD < CASE_NEXT_103_PUBLIC (when present).
    SPLIT = DEV if the case has any version of an in-window report (RD in (PUBLIC_DATE, PUBLIC_DATE + 365 days])
    contained in the 2025q4 bulk data set, else CONF.
fund_dates.parquet: every latest-version report date per fund (to tell exits from missing reports).
Family: the series' Part C "Advisor" from the most recent N-CEN (CRD), else the N-PORT registrant.

Usage: python src/late_flags/units.py
"""
import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "data/interim/late_flags/extract"
PA = ROOT / "data/interim/late_flags/panel"
LI = ROOT / "data/interim/late_flags/link"
OUT = ROOT / "data/interim/late_flags/units"
DEV_DATASET = "2025q4"
COLS = ["ACCESSION_NUMBER", "ISSUER_CUSIP", "ISSUER_NAME", "ISSUER_TITLE", "BALANCE", "UNIT", "CURRENCY_CODE",
        "CURRENCY_VALUE", "PERCENTAGE", "ASSET_CAT", "FAIR_VALUE_LEVEL", "IS_DEFAULT", "ARE_ANY_INTEREST_PAYMENT",
        "IS_ANY_PORTION_INTEREST_PAID", "PAYOFF_PROFILE"]


def families():
    a = pd.concat(pd.read_parquet(p) for p in glob.glob(str(ROOT / "data/interim/nport/ncen_adviser_*.parquet")))
    a = a[(a.ADVISER_TYPE == "Advisor") & (a.SOURCE == "Part C")].copy()
    a["SERIES_ID"] = a.FUND_ID.str.split("_").str[-1]
    a = a.sort_values(["SERIES_ID", "quarter"]).drop_duplicates("SERIES_ID", keep="last")
    return a.set_index("SERIES_ID")[["CRD_NUM", "ADVISER_NAME"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s_all = pd.read_parquet(LI / "securities.parquet")
    s_all = s_all[~s_all.AMBIGUOUS]  # all linked CUSIPs (incl. post-petition ones, for exchange detection)
    s = s_all[s_all.IN_SCOPE]
    ev = pd.read_parquet(LI / "events.parquet")
    ev = ev[ev.VERIFY == "PETITION"][["CASE_ID", "NAME", "EVENT_DATE", "PUBLIC_DATE", "CASE_NEXT_103_PUBLIC"]]
    fm = pd.read_parquet(PA / "filings_master.parquet",
                         columns=["ACCESSION_NUMBER", "FUND_KEY", "SERIES_ID", "CIK", "REGISTRANT_NAME", "SERIES_NAME",
                                  "RD", "FD", "SUB_TYPE", "VERSION", "N_VERSIONS", "LATEST", "DATASET", "NET_ASSETS"])
    want = set(s_all.CUSIP)
    parts = []
    for p in sorted(EX.glob("*_debt.parquet")):
        d = pd.read_parquet(p, columns=COLS)
        d["CUSIP"] = d.ISSUER_CUSIP.str.strip().str.upper()
        parts.append(d[d.CUSIP.isin(want)])
    d = pd.concat(parts, ignore_index=True).merge(fm, on="ACCESSION_NUMBER")
    for c in ["BALANCE", "CURRENCY_VALUE", "PERCENTAGE"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d.to_parquet(OUT / "obs_versions.parquet")

    L = d[d.LATEST]
    o = L.groupby(["FUND_KEY", "CUSIP", "RD"]).agg(
        ACCESSION_NUMBER=("ACCESSION_NUMBER", "first"), FD=("FD", "first"), DATASET=("DATASET", "first"),
        SERIES_ID=("SERIES_ID", "first"), CIK=("CIK", "first"), REGISTRANT_NAME=("REGISTRANT_NAME", "first"),
        SERIES_NAME=("SERIES_NAME", "first"), NET_ASSETS=("NET_ASSETS", "first"), SUB_TYPE=("SUB_TYPE", "first"),
        LOTS=("CUSIP", "size"), BALANCE=("BALANCE", "sum"), VALUE=("CURRENCY_VALUE", "sum"),
        UNIT=("UNIT", lambda x: ",".join(sorted(set(x)))), CUR=("CURRENCY_CODE", lambda x: ",".join(sorted(set(x)))),
        PAYOFF=("PAYOFF_PROFILE", lambda x: ",".join(sorted(set(x)))), FVL=("FAIR_VALUE_LEVEL", "first"),
        ASSET_CAT=("ASSET_CAT", "first"),
        DEF=("IS_DEFAULT", lambda x: ",".join(sorted(set(x)))),
        ARR=("ARE_ANY_INTEREST_PAYMENT", lambda x: ",".join(sorted(set(x)))),
        PIK=("IS_ANY_PORTION_INTEREST_PAID", lambda x: ",".join(sorted(set(x))))).reset_index()
    fam = families()
    o["FAMILY"] = o.SERIES_ID.map(fam.CRD_NUM).fillna("REG" + o.CIK.astype(str))
    o["FAMILY_NAME"] = o.SERIES_ID.map(fam.ADVISER_NAME).fillna(o.REGISTRANT_NAME)
    o["IN_SCOPE"] = o.CUSIP.isin(set(s.CUSIP))
    o["CASE_ID"] = o.CUSIP.map(s_all.drop_duplicates("CUSIP").set_index("CUSIP").CASE_ID)
    o.to_parquet(OUT / "obs.parquet")
    fm[fm.LATEST][["FUND_KEY", "RD", "FD", "DATASET"]].to_parquet(OUT / "fund_dates.parquet")

    x = o[o.IN_SCOPE].merge(ev, on="CASE_ID")
    inwin = (x.RD > x.PUBLIC_DATE) & (x.RD <= x.EVENT_DATE + pd.Timedelta(days=120)) & \
        (x.CASE_NEXT_103_PUBLIC.isna() | (x.RD < x.CASE_NEXT_103_PUBLIC))
    u = x[inwin].sort_values("RD").drop_duplicates(["CASE_ID", "CUSIP", "FUND_KEY"], keep="first")

    v = d.merge(s[["CUSIP", "CASE_ID"]], on="CUSIP").merge(ev, on="CASE_ID")
    dev_cases = set(v[(v.DATASET == DEV_DATASET) & (v.RD > v.PUBLIC_DATE) &
                      (v.RD <= v.PUBLIC_DATE + pd.Timedelta(days=365))].CASE_ID)
    u["SPLIT"] = u.CASE_ID.isin(dev_cases).map({True: "DEV", False: "CONF"})
    u.to_parquet(OUT / "units.parquet")

    for sp, g in u.groupby("SPLIT"):
        per_case = g.groupby("CASE_ID").size().sort_values(ascending=False)
        print(sp, "units", len(g), "cases", g.CASE_ID.nunique(), "CUSIPs", g.CUSIP.nunique(), "funds",
              g.FUND_KEY.nunique(), "families", g.FAMILY.nunique(),
              "top case share", round(per_case.iloc[0] / len(g), 3), "top-5 case share",
              round(per_case.head(5).sum() / len(g), 3), "median units/case", float(per_case.median()))
    print("in-scope cases with no unit", len(set(s.CASE_ID) - set(u.CASE_ID)))


if __name__ == "__main__":
    main()
