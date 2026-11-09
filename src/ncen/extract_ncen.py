"""Form N-CEN ADVISER table per data set -> data/interim/nport/ncen_adviser_{q}.parquet (used by src/late_flags/units.py).

Download the SEC N-CEN data sets ({q}_ncen.zip) into data/raw/ncen/ first.
Usage: python src/ncen/extract_ncen.py 2019q4 ...
"""
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/ncen"
OUT = ROOT / "data/interim/nport"


def run(q, out=OUT):
    z = zipfile.ZipFile(RAW / f"{q}_ncen.zip")
    name = next(n for n in z.namelist() if n.upper().endswith("ADVISER.TSV"))
    a = pd.read_csv(z.open(name), sep="\t", dtype=str, keep_default_na=False, quoting=3,
                    encoding_errors="replace", on_bad_lines="warn")
    a["quarter"] = q
    out.mkdir(parents=True, exist_ok=True)
    a.to_parquet(out / f"ncen_adviser_{q}.parquet")
    print(q, len(a))


if __name__ == "__main__":
    for q in sys.argv[1:]:
        run(q)
