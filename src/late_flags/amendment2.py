"""Amendment 2 (post hoc): audited estimate with CUSIP-level debtor identity and pre-emergence report dates.
Frozen estimators from outcome.py are used unchanged.

CUSIP label: the reviewer's CUSIP-level label for CUSIPs in influential groups; elsewhere the labeller's group
label. Where both exist and disagree, audit/reconciliation.csv (resolved from the cited documents) decides;
an unresolved disagreement is UNCLEAR.
Report-date status: PRE_EMERGENCE if RD < case END_DATE (or no END_DATE found: NO_END_DATE, kept and listed),
else POST_EMERGENCE (excluded from the audited estimate, reported).

Usage: python src/late_flags/amendment2.py
"""
import json
from pathlib import Path

import pandas as pd

from outcome import boot_case_weighted, boot_share, persistence, verdict

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "data/interim/late_flags"
PERSIST = ["FLAGGED_LATER", "WINDOW_ENDED_UNFLAGGED", "EXCHANGED_LINKED", "EXITED_OR_UNLINKED_EXCHANGE", "FUND_GONE"]


def cusip_labels():
    g = pd.read_csv(R / "audit/issuer_groups.csv")
    lab = pd.read_csv(R / "audit/labels.csv")[["GROUP_ID", "LABEL"]].rename(columns={"LABEL": "GROUP_LABEL"})
    m = g.merge(lab, on="GROUP_ID").assign(CUSIP=lambda d: d.CUSIPS.str.split(",")).explode("CUSIP")
    rv = pd.read_csv(R / "audit/reviewer/cusip_labels.csv")[["CASE_ID", "CUSIP", "LABEL"]].rename(
        columns={"LABEL": "REVIEW_LABEL"})
    m = m.merge(rv, on=["CASE_ID", "CUSIP"], how="left")
    rec_p = R / "audit/reconciliation.csv"
    rec = pd.read_csv(rec_p)[["CASE_ID", "CUSIP", "FINAL_LABEL"]] if rec_p.exists() else pd.DataFrame(
        columns=["CASE_ID", "CUSIP", "FINAL_LABEL"])
    m = m.merge(rec, on=["CASE_ID", "CUSIP"], how="left")
    agree = m.REVIEW_LABEL.isna() | (m.REVIEW_LABEL == m.GROUP_LABEL)
    m["LABEL"] = m.FINAL_LABEL.where(m.FINAL_LABEL.notna(),
                                     m.GROUP_LABEL.where(agree, "UNCLEAR"))
    m.loc[m.REVIEW_LABEL.notna() & agree, "LABEL"] = m.REVIEW_LABEL
    m["DISAGREE"] = ~agree
    return m[["CASE_ID", "CUSIP", "GROUP_ID", "GROUP_LABEL", "REVIEW_LABEL", "FINAL_LABEL", "LABEL", "DISAGREE"]]


def block(s, per):
    un = s[s.F == "UNFLAGGED"]
    # persistence window ends at the earlier of the frozen end and the case END_DATE (Amendment 2)
    s2 = s.copy()
    s2["CASE_NEXT_103_PUBLIC"] = s2[["CASE_NEXT_103_PUBLIC", "END_DATE"]].min(axis=1)
    ps = persistence(s2, OBS, FD, None)
    p = boot_share(s)
    return {"primary": {**p, "verdict_post_hoc": verdict(p)}, "case_weighted": boot_case_weighted(s),
            "value_weighted": boot_share(s, w="VALUE"),
            "by_asset": {a: boot_share(x) for a, x in s.groupby("ASSET_CAT")},
            "flagged": int((s.F == "FLAGGED").sum()), "unflagged": int(len(un)),
            "unflagged_value_usd": float(un.VALUE.sum()), "funds": int(s.FUND_KEY.nunique()),
            "families": int(s.FAMILY.nunique()),
            "persistence": {k: int((ps.STATUS == k).sum()) for k in PERSIST},
            "median_days_public_to_flag": float(ps.DAYS_PUBLIC_TO_FLAG.median()),
            "cases_no_unit_flagged": int((s.groupby("CASE_ID").F.agg(lambda f: (f == "FLAGGED").sum()) == 0).sum()),
            "cases_all_flagged": int((s.groupby("CASE_ID").F.agg(lambda f: (f == "UNFLAGGED").sum()) == 0).sum()),
            "case_share_quartiles_ge5": [round(float(x), 4) for x in s.groupby("CASE_ID").filter(lambda d: len(d) >= 5)
                                         .groupby("CASE_ID").F.agg(lambda f: (f == "UNFLAGGED").mean()).quantile([.25, .5, .75])],
            "top5_case_unflagged_share": round(float(un.groupby("CASE_ID").size().nlargest(5).sum() / max(len(un), 1)), 4),
            "top5_family_unflagged_share": round(float(un.groupby("FAMILY").size().nlargest(5).sum() / max(len(un), 1)), 4),
            "by_year": s.assign(Y=s.EVENT_DATE.dt.year).groupby("Y").F.agg(
                lambda f: [int(len(f)), round(float((f == "UNFLAGGED").mean()), 4)]).to_dict(),
            "arrears_Y_unflagged": int((un.ARR.fillna("").str.contains("Y")).sum())}


def main():
    global OBS, FD
    OBS = pd.read_parquet(R / "units/obs.parquet").dropna(subset=["CASE_ID"])
    FD = pd.read_parquet(R / "units/fund_dates.parquet")
    w = pd.read_parquet(R / "outcome/CONF_units_scored.parquet")
    per = pd.read_parquet(R / "outcome/CONF_persistence.parquet")
    lab = cusip_labels()
    ends = pd.read_csv(R / "audit/case_end_dates_final.csv")  # sale-only end dates -> NOT_FOUND (Amendment 2 text)
    ends["END_DATE"] = pd.to_datetime(ends.END_DATE, errors="coerce")
    w = w[w.F != "BLANK"].merge(lab[["CASE_ID", "CUSIP", "LABEL"]], on=["CASE_ID", "CUSIP"], how="left")
    w = w.merge(ends[["CASE_ID", "END_TYPE", "END_DATE"]], on="CASE_ID", how="left")
    w["RD_STATUS"] = "NO_END_DATE"
    w.loc[w.END_DATE.notna() & (w.RD < w.END_DATE), "RD_STATUS"] = "PRE_EMERGENCE"
    w.loc[w.END_DATE.notna() & (w.RD >= w.END_DATE), "RD_STATUS"] = "POST_EMERGENCE"
    res = {"cusip_labels": lab.LABEL.value_counts().to_dict(), "label_disagreements": int(lab.DISAGREE.sum()),
           "units_by_label_and_rd_status": w.groupby(["LABEL", "RD_STATUS"]).agg(
               units=("F", "size"), unflagged=("F", lambda f: int((f == "UNFLAGGED").sum()))).reset_index().to_dict("records"),
           "end_types": ends.END_TYPE.value_counts().to_dict()}
    base = w.RD_STATUS != "POST_EMERGENCE"
    res["debtor_pre_emergence"] = block(w[base & (w.LABEL == "DEBTOR")], per)
    res["sensitivity_debtor_plus_unclear"] = block(w[base & w.LABEL.isin(["DEBTOR", "UNCLEAR"])], per)
    res["sensitivity_debtor_known_end_only"] = block(w[(w.RD_STATUS == "PRE_EMERGENCE") & (w.LABEL == "DEBTOR")], per)
    lab.to_csv(R / "audit/cusip_labels_final.csv", index=False)
    w.to_parquet(R / "outcome/CONF_amendment2_units.parquet")
    (R / "outcome/CONF_amendment2.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
