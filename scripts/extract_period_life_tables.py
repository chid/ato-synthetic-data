"""
Extract genuinely period-correct mortality tables for the two backtests, replacing the
2016-2018 ABS vintage that both backtest scripts were using as a documented look-ahead
compromise (a 2013 or 2010 forecaster wouldn't have had 2016-2018 outcome data yet).

ABS's own pre-2016 Life Table vintages are archived behind JS-driven navigation on the
deprecated AUSSTATS site with no scrapeable download links (confirmed by a real attempt,
see APPROACH.md). The Australian Government Actuary (aga.gov.au) publishes its own
"Australian Life Tables" on the same ~5-year Census-aligned cycle, as direct-download
.xls files, and these ARE genuinely contemporaneous:
  - Australian Life Tables 2005-07 -> the mortality basis for the 2009-10 backtest.
  - Australian Life Tables 2010-12 -> the mortality basis for the 2012-13 backtest.

These are a different (actuarial, not ABS) source, methodologically close to the ABS
life tables but not identical -- noted as a source-switch, not silently treated as ABS.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

VINTAGES = {
    "2005-07": ("aga_life_table_2005_07_males.xls", "aga_life_table_2005_07_females.xls"),
    "2010-12": ("aga_life_table_2010_12_males.xls", "aga_life_table_2010_12_females.xls"),
}


def extract_vintage(label, male_file, female_file):
    records = []
    for sex, fname, sheet in [("Male", male_file, "Males"), ("Female", female_file, "Females")]:
        df = pd.read_excel(RAW / fname, sheet_name=sheet, engine="xlrd", header=None)
        data = df.iloc[1:]  # row 0 is the sparse "Age" header
        for row in data.itertuples():
            age = row._1  # column 0
            qx = row._5  # column 4 (0=age, 1=lx, 2=dx, 3=px, 4=qx)
            if pd.isna(age) or pd.isna(qx):
                continue
            records.append({"age": int(age), "sex": sex, "qx": float(qx)})
    out = pd.DataFrame(records)
    fname_out = f"aga_life_table_{label.replace('-', '_')}.csv"
    out.to_csv(OUT / fname_out, index=False)
    print(f"AGA Life Table {label} -> {len(out)} rows -> {fname_out}")


if __name__ == "__main__":
    for label, (m, f) in VINTAGES.items():
        extract_vintage(label, m, f)
    print("\nDone. Processed CSVs in", OUT)
