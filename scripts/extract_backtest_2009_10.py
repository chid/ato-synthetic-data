"""
Extract the ORIGINAL Taxation Statistics 2009-10 release's individual-level table for
a second, longer-horizon backtest (2009-10 -> 2022-23, 13 years).

This release predates ATO's move to the tidy long-format "one row per cell" layout
used from ~2012-13 onward. Table PER11 ("Selected items, by age, sex, taxable status
and taxable income") is a cross-tab: income brackets run across columns, and each
age x sex combination is a stacked block of item rows. Taxable status isn't a separate
dimension here -- "Non-taxable" is folded in as one column alongside the taxable
income brackets. This script reshapes that cross-tab into the same tidy
bracket-per-row format used elsewhere in this project.

Table PER9 (percentile distribution) was also pulled but turned out to publish only
COUNTS per percentile bucket, no dollar totals -- there's no average to calibrate a
within-bucket power transform against, unlike Table 16B for 2012-13/2022-23. So this
vintage's income draw uses the plain 22-bracket power-transform only, no percentile
refinement. A real, documented reduction in fidelity for this earlier backtest.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "taxstats2009_bundle" / "TaxStats" / "docs"
OUT = ROOT / "data" / "processed" / "backtest_2009_10"
OUT.mkdir(parents=True, exist_ok=True)

AGE_LABEL_MAP = {
    "Under 18": "a. Under 18", "18-24": "b. 18 - 24", "25-29": "c. 25 - 29",
    "30-34": "d. 30 - 34", "35-39": "e. 35 - 39", "40-44": "f. 40 - 44",
    "45-49": "g. 45 - 49", "50-54": "h. 50 - 54", "55-59": "i. 55 - 59",
    "60-64": "j. 60 - 64", "65-69": "k. 65 - 69", "70-74": "l. 70 - 74",
    "75 & over": "m. 75 and over",
}

ITEMS_2009_10 = ["Total income or loss3", "Taxable income (excluding losses)", "Pension income2"]


def extract_per11():
    df = pd.read_excel(RAW / "cor00305922_2010PER11.xls", sheet_name="Personal tax table 11", engine="xlrd", header=None)
    bracket_labels = list(df.iloc[0, 3:26])  # col3=Non-taxable, col4-25=22 taxable brackets

    records = []
    current_age, current_sex = None, None
    for i in range(1, len(df)):
        col0 = df.iat[i, 0]
        col1 = df.iat[i, 1]
        if pd.notna(col0):
            label = str(col0).strip()
            if label in ("Male", "Female"):
                current_sex = label
            elif label == "Total":
                current_sex = None  # skip the Male+Female "Total" sub-block
            else:
                current_age = label
        elif pd.notna(col1) and current_sex is not None:
            item = str(col1).strip()
            if item not in ITEMS_2009_10 and item != "Total individuals":
                continue
            for b_idx, bracket in enumerate(bracket_labels):
                col = 3 + b_idx
                records.append({
                    "age_range": AGE_LABEL_MAP[current_age],
                    "sex": current_sex,
                    "bracket_raw": bracket,
                    "item": "Individuals" if item == "Total individuals" else item,
                    "value": df.iat[i, col],
                })

    long_df = pd.DataFrame(records)
    wide = long_df.pivot_table(
        index=["age_range", "sex", "bracket_raw"], columns="item", values="value", aggfunc="first"
    ).reset_index()
    wide.columns.name = None
    wide.to_csv(OUT / "per11_2009_10_items_by_bracket.csv", index=False)
    print(f"PER11 2009-10 -> {len(wide)} rows")
    return wide


if __name__ == "__main__":
    extract_per11()
    print("\nDone. Processed CSVs in", OUT)
