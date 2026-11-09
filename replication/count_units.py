"""Independent replication, step 2: build units from extracted filings/holdings and write counts.json."""
import json
import os
from datetime import timedelta

import numpy as np
import pandas as pd

ROOT = os.environ.get("REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data/interim/late_flags/replication")
INP = os.path.join(ROOT, "data/interim/late_flags/replication_inputs")


def ddmon(s):
    return pd.to_datetime(s.str.strip(), format="%d-%b-%Y", errors="coerce")


def latest_versions(f):
    f = f.copy()
    f["SERIES_ID"] = f["SERIES_ID"].str.strip()
    f["CIK"] = f["CIK"].str.strip()
    f["FUND"] = np.where(f["SERIES_ID"] != "", f["SERIES_ID"], "CIK" + f["CIK"])
    f["FD"] = ddmon(f["FILING_DATE"])
    f["RD"] = ddmon(f["REPORT_DATE"])
    n_bad = int(f["RD"].isna().sum() + f["FD"].isna().sum())
    # same accession in more than one bulk zip: keep the latest zip's copy
    f = f.sort_values("ZIP").drop_duplicates("ACCESSION_NUMBER", keep="last")
    f = f.dropna(subset=["RD", "FD"])
    f = f.sort_values(["FUND", "RD", "FD", "ACCESSION_NUMBER"])
    n_versions = f.groupby(["FUND", "RD"]).size()
    lv = f.drop_duplicates(["FUND", "RD"], keep="last")
    return lv, f, n_bad, n_versions


def build_units(cases, cus, h, lv, lots_filter=None, first_report_overall=False):
    hh = h.merge(lv[["ZIP", "ACCESSION_NUMBER", "FUND", "RD", "FD"]], on=["ZIP", "ACCESSION_NUMBER"], how="inner")
    if lots_filter is not None:
        hh = hh[lots_filter(hh)]
    x = cus.merge(cases, on="CASE_ID").merge(hh, on="CUSIP", how="inner")
    lo = x["PUBLIC_DATE"]
    hi = x["EVENT_DATE"] + timedelta(days=120)
    ok = (x["RD"] > lo) & (x["RD"] <= hi) & (x["NEXT103"].isna() | (x["RD"] < x["NEXT103"]))
    x = x[ok]
    if first_report_overall:
        # alternative: the fund's first in-window report date overall (any filing), and it must hold the CUSIP
        fr = lv[["FUND", "RD"]].merge(cases[["CASE_ID", "PUBLIC_DATE", "EVENT_DATE", "NEXT103"]], how="cross")
        w = (fr["RD"] > fr["PUBLIC_DATE"]) & (fr["RD"] <= fr["EVENT_DATE"] + timedelta(days=120)) & (
            fr["NEXT103"].isna() | (fr["RD"] < fr["NEXT103"]))
        first = fr[w].groupby(["CASE_ID", "FUND"])["RD"].min().rename("FIRST_RD").reset_index()
        x = x.merge(first, on=["CASE_ID", "FUND"])
        x = x[x["RD"] == x["FIRST_RD"]]
    else:
        first = x.groupby(["CASE_ID", "CUSIP", "FUND"])["RD"].transform("min")
        x = x[x["RD"] == first]
    x = x.copy()
    x["HID"] = pd.to_numeric(x["HOLDING_ID"], errors="coerce")
    x = x.sort_values(["CASE_ID", "CUSIP", "FUND", "HID"])
    x["DEF"] = x["IS_DEFAULT"].str.strip().str.upper()
    x["ARR"] = x["ARE_ANY_INTEREST_PAYMENT"].str.strip().str.upper()
    g = x.groupby(["CASE_ID", "CUSIP", "FUND"], sort=False)
    u = g.agg(RD=("RD", "first"), N_LOTS=("DEF", "size"), ANY_Y=("DEF", lambda s: (s == "Y").any()),
              ALL_N=("DEF", lambda s: (s == "N").all()), ARR_Y=("ARR", lambda s: (s == "Y").any()),
              ASSET_CAT=("ASSET_CAT", "first"), ACCESSION=("ACCESSION_NUMBER", "first")).reset_index()
    u["FLAG"] = np.where(u["ANY_Y"], "FLAGGED", np.where(u["ALL_N"], "UNFLAGGED", "BLANK"))
    return u, x


def share(u):
    f = int((u["FLAG"] == "FLAGGED").sum())
    n = int((u["FLAG"] == "UNFLAGGED").sum())
    return {"flagged": f, "unflagged": n, "blank": int((u["FLAG"] == "BLANK").sum()),
            "unflagged_share": (n / (f + n)) if f + n else None}


def summarise(u):
    out = {"units": int(len(u)), "cases_with_units": int(u["CASE_ID"].nunique()),
           "cusips": int(u["CUSIP"].nunique()), "funds": int(u["FUND"].nunique())}
    out.update(share(u))
    nb = u[u["FLAG"] != "BLANK"]
    per = nb.groupby("CASE_ID")["FLAG"].apply(lambda s: (s == "UNFLAGGED").mean())
    out["case_weighted_share"] = float(per.mean()) if len(per) else None
    out["cases_in_case_weighted"] = int(len(per))
    out["by_asset_cat"] = {k: dict(units=int(len(v)), **share(v)) for k, v in u.groupby("ASSET_CAT")}
    a = u[u["ARR_Y"]]
    out["arrears_Y_any_lot"] = {"units": int(len(a)), **{k.lower(): int((a["FLAG"] == k).sum())
                                                         for k in ["FLAGGED", "UNFLAGGED", "BLANK"]}}
    return out


def main():
    cases = pd.read_csv(os.path.join(INP, "cases.csv"), dtype=str, keep_default_na=False)
    cases["EVENT_DATE"] = pd.to_datetime(cases["EVENT_DATE"])
    cases["PUBLIC_DATE"] = pd.to_datetime(cases["PUBLIC_DATE"])
    cases["NEXT103"] = pd.to_datetime(cases["CASE_NEXT_103_PUBLIC"].replace("", None))
    cus = pd.read_csv(os.path.join(INP, "cusips.csv"), dtype=str)
    cus["CUSIP"] = cus["CUSIP"].str.strip().str.upper()
    cus = cus.drop_duplicates()

    f = pd.read_pickle(os.path.join(OUT, "filings.pkl"))
    h = pd.read_pickle(os.path.join(OUT, "holdings.pkl"))
    lv, allv, n_bad, n_versions = latest_versions(f)

    debt = lambda d: d["ASSET_CAT"].str.strip().isin(["DBT", "LON"])  # "debt holdings" = DBT or LON lots
    u, lots = build_units(cases, cus, h, lv, lots_filter=debt)
    res = {"primary": summarise(u)}

    # diagnostics and sensitivities (not the primary definition)
    diag = {
        "filings_rows_P_and_PA": int(len(f)),
        "filings_unparseable_dates": n_bad,
        "accessions_in_multiple_zips": int(f["ACCESSION_NUMBER"].duplicated().sum()),
        "fund_reportdate_cells": int(len(lv)),
        "fund_reportdate_cells_with_multiple_versions": int((n_versions > 1).sum()),
        "funds_from_CIK_fallback_in_units": int(u["FUND"].str.startswith("CIK").sum()),
        "cusips_in_more_than_one_case": int(cus.groupby("CUSIP")["CASE_ID"].nunique().gt(1).sum()),
        "input_cases": int(len(cases)), "input_cusips": int(cus["CUSIP"].nunique()),
        "unit_lots_total": int(len(lots)),
        "units_with_multiple_lots": int((u["N_LOTS"] > 1).sum()),
        "unit_lots_without_debt_security_row": int((~lots["HAS_DEBT_ROW"]).sum()),
        "unit_lots_asset_cat_counts": lots["ASSET_CAT"].value_counts().to_dict(),
        "unit_lots_payoff_counts": lots["PAYOFF_PROFILE"].value_counts().to_dict(),
        "unit_lots_is_default_values": lots["DEF"].value_counts().to_dict(),
        "units_whose_RD_version_is_amendment": int(
            u.merge(lv[["ACCESSION_NUMBER", "SUB_TYPE"]], left_on="ACCESSION", right_on="ACCESSION_NUMBER")
            ["SUB_TYPE"].eq("NPORT-P/A").sum()),
        "cases_without_units": sorted(set(cases["CASE_ID"]) - set(u["CASE_ID"])),
    }
    res["diagnostics"] = diag
    u_all, lots_all = build_units(cases, cus, h, lv)
    diag["all_cat_unit_lots_asset_cat_counts"] = lots_all["ASSET_CAT"].value_counts().to_dict()
    u_long, _ = build_units(cases, cus, h, lv, lots_filter=lambda d: debt(d) & (d["PAYOFF_PROFILE"].str.strip() != "Short"))
    u_first, _ = build_units(cases, cus, h, lv, lots_filter=debt, first_report_overall=True)
    res["sensitivity"] = {
        "all_asset_categories_not_only_DBT_LON": {k: v for k, v in summarise(u_all).items()
                                                  if k not in ("by_asset_cat", "arrears_Y_any_lot")},
        "excluding_short_lots": {k: v for k, v in summarise(u_long).items()
                                 if k not in ("by_asset_cat", "arrears_Y_any_lot")},
        "RD_is_funds_first_inwindow_report_overall": {k: v for k, v in summarise(u_first).items()
                                                      if k not in ("by_asset_cat", "arrears_Y_any_lot")},
    }
    u.assign(RD=u["RD"].dt.date.astype(str)).to_pickle(os.path.join(OUT, "units.pkl"))
    with open(os.path.join(OUT, "counts.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
