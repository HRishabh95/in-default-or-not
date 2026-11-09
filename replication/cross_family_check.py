"""Independent cross-family cell check (does not read src/late_flags or analysis outputs).

Step 1: final unit set = replication units.pkl (count_units.py primary) filtered by audit labels:
        LABEL == DEBTOR, RD < END_DATE where known, LOAN_CLASS != ROLLED_UP (unlisted CUSIPs = BOND).
Step 2: cells = distinct (CUSIP, RD) in final units; every fund (latest version per FUND, RD) reporting the
        CUSIP on that RD, DBT/LON lots only (same lot filter as count_units.py primary); fund flag from lots.
Step 3: family = adviser CRD (N-CEN Part C, ADVISER_TYPE == 'Advisor') from the most recent N-CEN filing
        (by FILING_DATE, then accession) listing the series; else 'REG' + N-PORT registrant CIK.
Step 4: classify cells with >= 2 families into A/B/C/D.
"""
import glob
import io
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = os.environ.get("REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REP = os.path.join(ROOT, "data/interim/late_flags/replication")
AUD = os.path.join(ROOT, "data/interim/late_flags/audit")
sys.path.insert(0, REP)
from count_units import latest_versions  # noqa: E402  (replication's own latest-version rule)

READ = dict(dtype=str, sep="\t", quoting=3, keep_default_na=False)


def final_units():
    u = pd.read_pickle(os.path.join(REP, "units.pkl"))
    u["RD"] = pd.to_datetime(u["RD"])
    lab = pd.read_csv(os.path.join(AUD, "cusip_labels_final.csv"), dtype=str)
    end = pd.read_csv(os.path.join(AUD, "case_end_dates_final.csv"), dtype=str)
    lc = pd.read_csv(os.path.join(AUD, "loan_classes.csv"), dtype=str)
    end["END"] = pd.to_datetime(end["END_DATE"], errors="coerce")
    x = u.merge(lab[["CASE_ID", "CUSIP", "LABEL"]], on=["CASE_ID", "CUSIP"], how="left")
    x = x[x["LABEL"] == "DEBTOR"]
    x = x.merge(end[["CASE_ID", "END"]], on="CASE_ID", how="left")
    x = x[x["END"].isna() | (x["RD"] < x["END"])]
    x = x.merge(lc[["CASE_ID", "CUSIP", "LOAN_CLASS"]], on=["CASE_ID", "CUSIP"], how="left")
    x["LOAN_CLASS"] = x["LOAN_CLASS"].fillna("BOND")
    check = {"asset_cat_x_loan_class": pd.crosstab(x["ASSET_CAT"], x["LOAN_CLASS"]).to_dict()}
    x = x[x["LOAN_CLASS"] != "ROLLED_UP"].copy()
    s = {"units": int(len(x)), "unflagged": int((x["FLAG"] == "UNFLAGGED").sum()),
         "flagged": int((x["FLAG"] == "FLAGGED").sum()), "cases": int(x["CASE_ID"].nunique()),
         "by_class": x["LOAN_CLASS"].value_counts().to_dict(), **check}
    return x, s


def ncen_advisers():
    rows = []
    for z in sorted(glob.glob(os.path.join(ROOT, "data/raw/ncen/*_ncen.zip"))):
        with zipfile.ZipFile(z) as zf:
            rd = lambda n, c: pd.read_csv(io.TextIOWrapper(zf.open(n), encoding="utf-8", errors="replace"),
                                          usecols=c, **READ)
            sub = rd("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE"])
            fri = rd("FUND_REPORTED_INFO.tsv", ["FUND_ID", "ACCESSION_NUMBER", "SERIES_ID"])
            adv = rd("ADVISER.tsv", ["FUND_ID", "SOURCE", "ADVISER_TYPE", "CRD_NUM", "ADVISER_NAME"])
        adv = adv[(adv["SOURCE"].str.strip() == "Part C") & (adv["ADVISER_TYPE"].str.strip() == "Advisor")]
        fri = fri.merge(sub, on="ACCESSION_NUMBER", how="left")
        fri["ZIP"] = os.path.basename(z)
        rows.append((fri, adv))
    fri = pd.concat([r[0] for r in rows], ignore_index=True)
    adv = pd.concat([r[1] for r in rows], ignore_index=True).drop_duplicates()
    fri["SERIES_ID"] = fri["SERIES_ID"].str.strip()
    fri = fri[fri["SERIES_ID"] != ""]
    fri["FD"] = pd.to_datetime(fri["FILING_DATE"].str.strip(), format="%d-%b-%Y", errors="coerce")
    fri = fri.sort_values(["ZIP"]).drop_duplicates(["FUND_ID"], keep="last")
    fri = fri.sort_values(["SERIES_ID", "FD", "ACCESSION_NUMBER"])
    last = fri.drop_duplicates("SERIES_ID", keep="last")
    adv["CRD"] = adv["CRD_NUM"].str.strip().str.lstrip("0")
    adv = adv[adv["CRD"] != ""]
    a = last[["SERIES_ID", "FUND_ID", "ACCESSION_NUMBER"]].merge(adv[["FUND_ID", "CRD", "ADVISER_NAME"]],
                                                                    on="FUND_ID", how="left")
    multi = a.dropna(subset=["CRD"]).groupby("SERIES_ID")["CRD"].nunique()
    # several distinct advisers in the latest filing: take the lowest CRD (deterministic), reported below
    a = a.dropna(subset=["CRD"]).sort_values(["SERIES_ID", "CRD"]).drop_duplicates("SERIES_ID")
    # sensitivity: most recent filing that lists the series WITH an Advisor row
    b = fri.merge(adv[["FUND_ID", "CRD"]], on="FUND_ID").sort_values(["SERIES_ID", "FD", "ACCESSION_NUMBER", "CRD"])
    b = b.drop_duplicates("SERIES_ID", keep="last")
    return (a.set_index("SERIES_ID")["CRD"], set(multi[multi > 1].index), set(last["SERIES_ID"]),
            b.set_index("SERIES_ID")["CRD"])


def classify(cf, fam_col):
    fam = cf.groupby(["CUSIP", "RD", "LOAN_CLASS", fam_col])["FLAG"].agg(
        lambda s: "Y" if (s == "FLAGGED").all() else ("N" if (s == "UNFLAGGED").all() else "MIXED"))
    fam = fam.rename("FF").reset_index()
    c = fam.groupby(["CUSIP", "RD", "LOAN_CLASS"])["FF"].agg(
        nfam="size", y=lambda s: (s == "Y").sum(), n=lambda s: (s == "N").sum(), m=lambda s: (s == "MIXED").sum())
    c = c.reset_index()
    c = c[c["nfam"] >= 2].copy()
    c["CLS"] = np.select([(c.y > 0) & (c.n > 0), c.y == c.nfam, c.n == c.nfam], ["A", "B", "C"], "D")
    return c


def table(c):
    out = {}
    for k, g in c.groupby("LOAN_CLASS"):
        out[k] = {"eligible": int(len(g)), **{x: int((g["CLS"] == x).sum()) for x in "ABCD"},
                  "with_mixed": int((g["m"] > 0).sum())}
    return out


def main():
    units, s1 = final_units()
    f = pd.read_pickle(os.path.join(REP, "filings.pkl"))
    h = pd.read_pickle(os.path.join(REP, "holdings.pkl"))
    lv, _, _, _ = latest_versions(f)
    hh = h.merge(lv[["ZIP", "ACCESSION_NUMBER", "FUND", "RD", "CIK", "SERIES_ID"]], on=["ZIP", "ACCESSION_NUMBER"])
    cells = units[["CUSIP", "RD", "LOAN_CLASS"]].drop_duplicates()
    assert not cells.duplicated(["CUSIP", "RD"]).any()

    def cell_funds(lots):
        x = lots.merge(cells, on=["CUSIP", "RD"])
        x["DEF"] = x["IS_DEFAULT"].str.strip().str.upper()
        g = x.groupby(["CUSIP", "RD", "LOAN_CLASS", "FUND", "CIK", "SERIES_ID"])["DEF"]
        cf = g.agg(ANY_Y=lambda s: (s == "Y").any(), ALL_N=lambda s: (s == "N").all()).reset_index()
        cf["FLAG"] = np.where(cf.ANY_Y, "FLAGGED", np.where(cf.ALL_N, "UNFLAGGED", "BLANK"))
        return cf

    debt = hh["ASSET_CAT"].str.strip().isin(["DBT", "LON"])
    cf_all = cell_funds(hh[debt])
    assert not cf_all.duplicated(["CUSIP", "RD", "FUND"]).any()
    n_blank = int((cf_all.FLAG == "BLANK").sum())
    cf = cf_all[cf_all.FLAG != "BLANK"].copy()

    crd, multi, ncen_series, crd_any = ncen_advisers()
    sid = cf["SERIES_ID"].str.strip()
    cf["CRD"] = sid.map(crd)
    cf["FAMILY"] = np.where(cf["CRD"].notna(), "CRD" + cf["CRD"].fillna(""), "REG" + cf["CIK"].str.strip())
    cf["FAMILY_ALT"] = np.where(sid.map(crd_any).notna(), "CRD" + sid.map(crd_any).fillna(""),
                                "REG" + cf["CIK"].str.strip())
    fam_stats = {"cell_funds_nonblank": int(len(cf)), "cell_funds_blank_dropped": n_blank,
                 "with_crd": int(cf["CRD"].notna().sum()), "fallback_reg": int(cf["CRD"].isna().sum()),
                 "fallback_no_series_id": int((sid == "").sum()),
                 "fallback_series_not_in_ncen": int(((sid != "") & ~sid.isin(ncen_series)).sum()),
                 "fallback_series_in_ncen_no_advisor": int((cf["CRD"].isna() & sid.isin(ncen_series)).sum()),
                 "cell_funds_series_with_multiple_advisers_latest_filing": int(sid.isin(multi).sum()),
                 "distinct_families": int(cf["FAMILY"].nunique())}

    c = classify(cf, "FAMILY")
    res = {"step1_final_units": s1, "step3_families": fam_stats, "cells_total": int(len(cells)),
           "cells_by_class": cells["LOAN_CLASS"].value_counts().to_dict(), "step4": table(c)}
    bond = c[c.LOAN_CLASS == "BOND"]
    case_of = units[["CUSIP", "RD", "CASE_ID"]].drop_duplicates()
    ce = bond.merge(case_of, on=["CUSIP", "RD"])
    bu = units[(units.LOAN_CLASS == "BOND") & (units.FLAG == "UNFLAGGED")]
    res["bond_extra"] = {
        "cases_eligible_bond_cells": int(ce["CASE_ID"].nunique()),
        "cases_A_bond_cells": int(ce[ce.CLS == "A"]["CASE_ID"].nunique()),
        "unflagged_final_bond_units_in_A_cells": int(len(bu.merge(bond[bond.CLS == "A"][["CUSIP", "RD"]],
                                                                  on=["CUSIP", "RD"]))),
        "cusips_spanning_multiple_cases": int(case_of.groupby(["CUSIP", "RD"])["CASE_ID"].nunique().gt(1).sum())}
    # sensitivities
    res["sens_family_from_latest_filing_with_advisor"] = table(classify(cf, "FAMILY_ALT"))
    cfa = cell_funds(hh)
    cfa = cfa[cfa.FLAG != "BLANK"].copy()
    s2 = cfa["SERIES_ID"].str.strip()
    cfa["FAMILY"] = np.where(s2.map(crd).notna(), "CRD" + s2.map(crd).fillna(""), "REG" + cfa["CIK"].str.strip())
    res["sens_all_asset_cats"] = table(classify(cfa, "FAMILY"))
    # detail for D and MIXED cells
    det = []
    for _, r in c[(c.CLS == "D") | (c.m > 0)].iterrows():
        g = cf[(cf.CUSIP == r.CUSIP) & (cf.RD == r.RD)]
        det.append({"CUSIP": r.CUSIP, "RD": str(r.RD.date()), "class": r.LOAN_CLASS, "cell": r.CLS,
                    "funds": [f"{a}:{b}:{x}" for a, b, x in zip(g.FUND, g.FAMILY, g.FLAG)]})
    res["mixed_or_D_cells"] = det
    c.assign(RD=c.RD.dt.date.astype(str)).to_csv(os.path.join(REP, "cross_family_check_cells.csv"), index=False)
    with open(os.path.join(REP, "cross_family_check.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
