"""Amendment 1 (post hoc): audited estimate restricted to DEBTOR issuer groups, with UNCLEAR as a bound.
Uses the frozen estimators from outcome.py unchanged.

Usage: python src/late_flags/amendment1.py
"""
import json
from pathlib import Path

import pandas as pd

from outcome import boot_case_weighted, boot_share, verdict
from panel import norm_name

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "data/interim/late_flags"


def main():
    w = pd.read_parquet(R / "outcome/CONF_units_scored.parquet")
    per = pd.read_parquet(R / "outcome/CONF_persistence.parquet")
    g = pd.read_csv(R / "audit/issuer_groups.csv")
    lab = pd.read_csv(R / "audit/labels.csv")[["GROUP_ID", "LABEL", "IDENTIFIED_ISSUER"]]
    g = g.merge(lab, on="GROUP_ID", how="left")
    m = g.assign(CUSIP=g.CUSIPS.str.split(",")).explode("CUSIP")[["CASE_ID", "CUSIP", "LABEL", "GROUP_ID"]]
    w = w.merge(m, on=["CASE_ID", "CUSIP"], how="left")
    w = w[w.F != "BLANK"]
    res = {"labels_groups": g.LABEL.value_counts(dropna=False).to_dict(),
           "units_by_label": w.groupby("LABEL").agg(units=("F", "size"),
                                                    unflagged=("F", lambda f: int((f == "UNFLAGGED").sum()))).to_dict("index")}
    for name, keep in [("debtor_only", {"DEBTOR"}), ("debtor_plus_unclear", {"DEBTOR", "UNCLEAR"})]:
        s = w[w.LABEL.isin(keep)]
        p = boot_share(s)
        un = s[s.F == "UNFLAGGED"]
        ps = per.merge(s[["CASE_ID", "CUSIP", "FUND_KEY"]], on=["CASE_ID", "CUSIP", "FUND_KEY"])
        res[name] = {"primary": {**p, "verdict_post_hoc": verdict(p)},
                     "case_weighted": boot_case_weighted(s),
                     "value_weighted": boot_share(s, w="VALUE"),
                     "by_asset": {a: boot_share(x) for a, x in s.groupby("ASSET_CAT")},
                     "unflagged_value_usd": float(un.VALUE.sum()),
                     "persistence": ps.STATUS.value_counts().to_dict(),
                     "median_days_public_to_flag": float(ps.DAYS_PUBLIC_TO_FLAG.median()),
                     "cases_no_unit_flagged": int((s.groupby("CASE_ID").F.agg(lambda f: (f == "FLAGGED").sum()) == 0).sum()),
                     "top5_case_unflagged_share": round(float(un.groupby("CASE_ID").size().nlargest(5).sum() / max(len(un), 1)), 4),
                     "top5_family_unflagged_share": round(float(un.groupby("FAMILY").size().nlargest(5).sum() / max(len(un), 1)), 4),
                     "by_year": s.assign(Y=s.EVENT_DATE.dt.year).groupby("Y").F.agg(
                         lambda f: [int(len(f)), round(float((f == "UNFLAGGED").mean()), 4)]).to_dict()}
    (R / "outcome/CONF_amendment1.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
