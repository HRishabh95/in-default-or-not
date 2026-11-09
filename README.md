# In Default or Not? How Funds Report Bonds of Bankrupt Issuers in SEC Form N-PORT

Code for the working paper of the same name (Rishabh Gyanendra Upadhyay, Inception42, November 2026).

Form N-PORT asks each registered fund whether each debt security it holds is "currently in default", and the
SEC leaves the meaning of default to each fund's own methodology. This code measures how far those answers
diverge for debt of issuers that have filed for bankruptcy:

- Among bankruptcy-linked bond-dates (the same bond on the same report date) held by funds of at least two
  different advisers, the fund families give opposite answers in **141 of 305 (46.2%)**.
- At each fund's first report after the petition became public, **18.8% of 3,783 bond holdings** are reported
  as not in default.

These are not error rates: the form permits methodologies to differ. See the paper for scope and caveats.

**This repository holds code and documentation only. It contains no data.** Every input is public and can be
downloaded from the SEC as described below.

## Repository layout

| Path | What it does |
|---|---|
| `src/late_flags/fetch_events.py` | Finds 8-K filings reporting Item 1.03 (bankruptcy) through EDGAR full-text search |
| `src/late_flags/verify_events.py` | Reads each case's 8-K and takes the petition date from its text |
| `src/late_flags/extract.py` | Extracts debt holdings and filing metadata from one N-PORT quarterly data set |
| `src/late_flags/panel.py` | Keeps the latest filing per fund and report date across data sets; builds the issuer dictionary |
| `src/late_flags/link.py` | Links bankruptcy cases to the prepetition debt securities funds held (names, LEIs, CUSIPs) |
| `src/late_flags/units.py` | Builds the observation panel and the analysis units; adds fund families from N-CEN |
| `src/late_flags/outcome.py` | Pre-registered primary and secondary analyses (`DEV` or `CONF`) |
| `src/late_flags/amendment1.py`, `amendment2.py` | Post-hoc audited estimates (see `docs/AMENDMENT_*.md`) |
| `src/late_flags/final.py` | Produces every number in the paper (`outcome/FINAL.json`) |
| `src/late_flags/pilot.py` | Development pilot on the 2025q4 data set |
| `src/late_flags/PROTOCOL.md` | The frozen protocol. `outcome.py CONF` checks its hash |
| `src/ncen/extract_ncen.py` | Extracts the N-CEN adviser table used to define fund families |
| `replication/` | Independent re-implementation written without access to `src/` (extraction, unit counts, event check, cross-family table) |
| `paper/` | LaTeX source, figure and table script, numbers audit (`numbers_check.py` matches every quoted number to the outputs) |
| `docs/` | Amendments, legal scope memo, obligor check, prior-art memo, protocol hashes |

## Data to download (all public, from the SEC)

Put the files in these folders (they are git-ignored):

| Data | Source | Files | Folder |
|---|---|---|---|
| Form N-PORT data sets | [sec.gov: Form N-PORT Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets) | `2019q4_nport.zip` to `2026q3_nport.zip` (28 files, very large) | `data/raw/nport/` |
| Form N-CEN data sets | [sec.gov: Form N-CEN Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets) | `2019q4_ncen.zip` to `2026q2_ncen.zip` | `data/raw/ncen/` |
| 8-K filings | EDGAR full-text search and archives | fetched by the scripts | `data/interim/late_flags/events/` |

Direct file URLs follow the pattern
`https://www.sec.gov/files/dera/data/form-n-port-data-sets/2026q3_nport.zip` and
`https://www.sec.gov/files/dera/data/form-n-cen-data-sets/2026q2_ncen.zip`.

The SEC requires automated clients to identify themselves and limits request rates (see
[SEC: Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)).
Set your own contact details before running anything that calls EDGAR:

```sh
export SEC_USER_AGENT="Your Name your.email@example.com"
```

Example download (one file; keep requests well under the SEC's rate limit):

```sh
mkdir -p data/raw/nport data/raw/ncen
curl -A "$SEC_USER_AGENT" -o data/raw/nport/2025q4_nport.zip \
  https://www.sec.gov/files/dera/data/form-n-port-data-sets/2025q4_nport.zip
```

## Running the pipeline

Python 3.9+ with `pip install -r requirements.txt`. Run from the repository root.

```sh
python src/late_flags/fetch_events.py                 # 8-K Item 1.03 / 2.04 hits
python src/late_flags/verify_events.py                # petition dates from the 8-K text
python src/late_flags/extract.py 2019q4 2020q1 ...    # every N-PORT data set you downloaded
python src/ncen/extract_ncen.py 2019q4 2020q1 ...     # every N-CEN data set you downloaded
python src/late_flags/panel.py
python src/late_flags/link.py
python src/late_flags/units.py
python src/late_flags/outcome.py DEV
python src/late_flags/outcome.py CONF                 # needs the protocol hash file, see below
python src/late_flags/amendment1.py
python src/late_flags/amendment2.py
python src/late_flags/final.py
sh paper/build.sh                                     # figures, tables and the PDF (needs tectonic)
python paper/numbers_check.py
```

`outcome.py CONF` runs only if `data/interim/late_flags/PROTOCOL_SHA256` exists and matches
`src/late_flags/PROTOCOL.md`. The hashes recorded when the protocol and amendments were frozen
(29 October 2026) are in `docs/PROTOCOL_SHA256.txt`; copy that file to `data/interim/late_flags/PROTOCOL_SHA256`
to run the confirmation.

### Inputs not included

The amendments and final sample use the issuer and CUSIP debtor labels, the case end dates and the loan
classes produced by the audit (`data/interim/late_flags/audit/*.csv`), and the replication uses the case and
CUSIP lists in `data/interim/late_flags/replication_inputs/`. These were produced from public filings during
the research and are not part of this code release. The audit procedure and the sources for each label are
described in the paper (Appendix A) and in `docs/OBLIGOR_CHECK.md`, `docs/AMENDMENT_1.md` and
`docs/AMENDMENT_2.md`. Everything up to and including `outcome.py` runs from SEC data alone.

## Research record

The frozen pre-registered confirmation gave 30.3%. A source-based audit after the run removed securities of
unrelated companies and non-filing affiliates; all estimates after the audit are post hoc and labelled as such
in the paper. Both stages are kept side by side in `final.py`.

## Licence

MIT. See `LICENSE`. The SEC data are public; check the SEC's terms before redistributing them.
