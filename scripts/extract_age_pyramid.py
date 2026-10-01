"""
Extract ABS's real single-year-of-age population time series (Table 3101059,
"Population - Australia", 1971 onwards, by sex) to replace the uniform-within-band age
assumption used everywhere in this project: generate_synthetic.py's draw_age() and its
copies in both backtest scripts currently draw ages UNIFORMLY within each 5-year ATO
age range (e.g. 25-29), when the real population isn't flat across those 5 years.

This is a genuine, direct download -- no archive/JS problems -- and as a bonus it's a
full historical time series back to 1971, so the SAME file gives period-correct age
pyramids for both backtest years (2009-10, 2012-13) as well as the current model
(2022-23), not just the current one.
"""
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def extract():
    wb = openpyxl.load_workbook(RAW / "abs_pop_age_national.xlsx", read_only=True, data_only=True)
    ws = wb["Data1"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]

    def age_from_header(h):
        part = h.split(";")[2].strip()
        return 100 if part == "100 and over" else int(part)

    male_cols = [(i, age_from_header(h)) for i, h in enumerate(header) if h and "Male" in h]
    female_cols = [(i, age_from_header(h)) for i, h in enumerate(header) if h and "Female" in h]

    records = []
    for r in rows[10:]:
        if r[0] is None:
            continue
        year = r[0].year
        for col, age in male_cols:
            records.append({"year": year, "sex": "Male", "age": age, "population": r[col]})
        for col, age in female_cols:
            records.append({"year": year, "sex": "Female", "age": age, "population": r[col]})

    df = pd.DataFrame(records)
    df.to_csv(OUT / "abs_age_pyramid_by_year.csv", index=False)
    print(f"ABS age pyramid (1971-present, by year x sex x single age) -> {len(df)} rows")


if __name__ == "__main__":
    extract()
    print("\nDone. Processed CSV in", OUT)
