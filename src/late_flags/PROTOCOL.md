# Late Flags or Late Marks: confirmation protocol

Status: FROZEN 2026-10-29 (author decision: Option A, run on the existing 60-case confirmation sample). Freezing writes the sha256 of this file and of the analysis code to
data/interim/late_flags/PROTOCOL_SHA256; `outcome.py CONF` refuses to run without a matching hash. No
default or arrears flag or price of a confirmation case has been read. Development used only cases observed in
the 2025q4 bulk data set (4 cases, 265 units; results in NOTES.md).

## 1. Primary question (one)

**Among registered funds holding prepetition debt of an issuer whose bankruptcy petition was made public in an
8-K, what share of those fund holdings is reported as not in default (`IS_DEFAULT = N`) at the fund's first
report date after the petition became public?**

- Unit: fund (series) x CUSIP at the fund's first report date RD with PUBLIC_DATE < RD <= EVENT_DATE + 120
  days and RD < CASE_NEXT_103_PUBLIC (when present).
- Unit flag: FLAGGED if any lot reports Y; UNFLAGGED if all lots report N; BLANK otherwise (counted, excluded
  from the share).
- Filing version: the latest version per fund and report date across all bulk data sets.
- Estimate: UNFLAGGED / (FLAGGED + UNFLAGGED), equal weight per unit. 95% interval: bootstrap over issuer
  cases (2,000 draws, seed 20261029).
- Verdicts (wording fixed):
  - **OMISSION COMMON**: point estimate >= 10% and lower bound >= 5%.
  - **OMISSION RARE**: upper bound < 5%.
  - **INCONCLUSIVE**: otherwise.

Why a petition is a security-specific external default: filing a bankruptcy petition is an event of default
under standard indentures and credit agreements and accelerates the debtor's prepetition obligations. The date
comes from the issuer's 8-K, not from any fund, and cases where no holder ever flags are included.

Co-reported (no separate verdict): the **case-weighted** share (mean over cases of each case's unflagged
share, bootstrap over cases) and the value-weighted share. The verdict uses the holding-weighted estimate above.

An unflagged holding is **not** by itself a legal reporting error. A petition is an external default signal;
whether a given fund's "N" breaches the form instruction depends on facts this study does not observe (see 6).

## 1a. Revision of the original plan (recorded before freezing)

- The original plan (research_notes/Research plan 2026-10-29/PLAN.md, unchanged) set a Stage 0 feasibility
  target of ">= 300 externally dated default events whose bond has at least 3 holders".
- That target was **not met**. Construction from independent 8-K evidence yielded 312 verified petitions, of
  which 80 link to fund-held prepetition debt and 60 have confirmation units. The sample was therefore narrowed
  to **60 independently identified bankruptcy cases** (206 CUSIPs, 4,692 holdings).
- Reason for proceeding: the primary estimand is a share with fixed, wide verdict thresholds, and inference is
  clustered by case; the author chose this over widening the event definition (Option B) on 2026-10-29.
- The four development cases (265 holdings; 36% unflagged; see NOTES.md) **were observed before freezing**.
  They are excluded from the confirmation estimate.
- The sample will not be widened after confirmation.

## 2. Event sample (`fetch_events.py`, `verify_events.py`, `link.py`)

- EDGAR full-text search, 8-Ks filed 2019-07 to 2026-10 mentioning "Chapter 11" or "Chapter 7" with Item
  1.03 tagged (forms filter "8-K" only; listing "8-K/A" silently drops hits).
- Case: first such 8-K of a CIK; later Item 1.03 8-Ks within 3 years belong to it; the first one more than 7
  days later is CASE_NEXT_103_PUBLIC.
- Verified from the full submission text: the Item 1.03 sentence saying petitions were filed or cases
  commenced gives PETITION_DATE (latest date in that sentence not after the 8-K filing date). Kept only when
  PETITION_DATE is between 30 days before and 1 day after the 8-K filing date. EVENT_DATE = PETITION_DATE.
- Securities: CUSIP-6s from exact normalised-name matches to the 8-K filer (and the LEIs of those matches),
  kept only if the CUSIP-6's own holdings point to the debtor (modal LEI is a debtor LEI, or >= 50% of holding
  rows share a distinctive name token). In scope: asset category DBT or LON, not a pass-through, CMBS or
  "Issuer LLC" securitisation, held by some fund on or before EVENT_DATE, not DIP, not matured before the event,
  CUSIP-6 not reached by two cases.

Counts at freeze: 380 cases -> 312 verified petitions (51 no petition sentence, 17 later-stage filings) -> 80
with in-scope securities (337 CUSIPs) -> 64 with units (4 DEV, 60 CONF); 16 linked cases have no in-window report.

**Gate disclosure.** The 2026-10-29 plan set ">= 300 externally dated default events". At the level of
independent issuer cases the confirmation sample is 60 cases (206 CUSIPs, 4,692 units, 886 funds, 296
families). Inference is clustered by case for that reason. The largest case is 18.5% of units; the top five 53%.

## 3. Dates kept apart

| Date | Source | Meaning |
|---|---|---|
| EVENT_DATE | petition date from the 8-K text | when the petition was filed |
| EVENT_DATE_8K | 8-K date of report | earliest event reported (can be an earlier agreement) |
| PUBLIC_DATE | 8-K filing date | when the petition was public on EDGAR |
| RD | N-PORT report date | the date the fund's holdings and flags describe |
| FD | N-PORT filing date | when the fund filed |
| DATASET | SEC bulk data set | when the report entered the public bulk data |

## 4. Confirmation separation

- DEV: a case with any version of an in-window report (RD in (PUBLIC_DATE, PUBLIC_DATE + 365 days])
  contained in the 2025q4 bulk data set. CONF: all other cases with units.
- DEV is reported separately and never pooled into the primary estimate.

## 5. Secondary analyses (pre-specified, descriptive, no verdicts)

S0 **By asset category** (DBT, LON), same estimator; and per case: cases where no unit is flagged, cases where
all are, median case share.

S0b **Distribution** across issuer cases, fund families and petition years: units, unflagged units, value,
unflagged share per group (CSV tables), and quartiles of the group shares for groups with >= 5 units.

S0c **Unresolved security-level obligations.** Every in-scope CUSIP of the split's cases is listed with its
resolution: RESOLVED, NO_IN_WINDOW_REPORT, ALL_BLANK; plus unpriced units. Nothing is dropped silently.

S1 **Persistence.** For each unflagged unit, the fund's later reports up to min(EVENT_DATE + 365 days,
CASE_NEXT_103_PUBLIC): FLAGGED_LATER (first later Y; days from PUBLIC_DATE), EXCHANGED_LINKED (CUSIP gone
and the fund newly holds another CUSIP linked to the case), EXITED_OR_UNLINKED_EXCHANGE (CUSIP gone, no linked
replacement; sale and exchange into unlinked new securities cannot be told apart), FUND_GONE (no later report),
WINDOW_ENDED_UNFLAGGED.

S2 **Concentration.** Share of unflagged units and their value in the top 5 cases and top 5 fund families
(N-CEN Part C adviser of the series, by CRD; registrant when unmatched); among groups with >= 10 units, how many
flag none and how many flag all.

S3 **Flag disagreement.** At the units' CUSIP x report-date cells with >= 2 holders: split, all unflagged, all
flagged.

S4 **Valuation disagreement.** Price = value / balance x 100 for USD, principal-amount, long holdings. In
split cells: median of (unflagged median price - flagged median price); each holder's gap to the median of the
other holders. Holder consensus is a comparator, never ground truth.

S5 **Independently supported stale marking.** Unit price within 0.01 points of the same fund's own last
pre-event price for the CUSIP; for these, the fund's own price change at its next report, in points, $ and
basis points of NAV.

S6 **Economic magnitude.** Value of unflagged units ($; % of fund NAV, median and 90th percentile);
comparator gap in $ (labelled as such).

S7 **Arrears flag** crossed with the default flag.

S8 **Amendments.** Units with more than one version; units whose flag differs between versions.

## 6. Known limits (stated in any write-up)

- Coverage: issuers that file 8-Ks and whose securities link by name, LEI or CUSIP-6; private-company
  bankruptcies and non-filing subsidiaries are not in the sample.
- Construct: a fund may read "currently in default" as payment default only, or treat debt that a prepackaged
  plan leaves unimpaired as not in default. The study measures what is reported against the petition, and
  reports the arrears flag alongside.
- Quarterly granularity: public N-PORT reports are quarter-end months.

## 6a. Execution

- Confirmation is run once (`outcome.py CONF`); all outputs are retained whatever they show.
- An independent reconstruction of the headline counts (units, flagged, unflagged, cases) is commissioned from
  the raw N-PORT bulk files and this protocol, without access to the analysis code or its outputs.

## 7. Wording rules

- "Not flagged" or "reported not in default", never "misreported" or "error", unless a registrant has said so
  (NOTES.md). The petition is a default signal, not a legal finding about any fund's report.
- Valuation results (S4-S6) are secondary. No conclusion of stale NAVs is drawn from label differences or
  peer-price comparisons alone; S5 is the only stale-mark evidence and is described as "own price carried
  forward", with its own later change.
- Prior SEC correspondence already shows omissions exist; the contribution claimed is prevalence, persistence
  and valuation consequences.
- Submission is conditional on the evidence; an OMISSION RARE or INCONCLUSIVE result is reported as such.
