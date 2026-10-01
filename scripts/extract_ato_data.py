"""
Extract the ATO / ABS source workbooks in data/raw/ into tidy CSVs in data/processed/.

This is the "make a copy of the ato statistics" step: nothing here is invented,
every processed CSV is a straight reshape of the published tables so it can be
diffed back against the source workbook.

Sources (2022-23 income year, released 2025):
  ATO Taxation Statistics 2022-23, Individuals:
    Table 3A - Selected items by sex, taxable status, age range, taxable income range
    Table 16B - Percentile distribution of taxable income (median/average) by sex
    Table 19  - "If Australia was 100 people" summary
    Table 18  - Deductions claimed by state / occupation / gender
    Table 1   - Individuals key aggregates by year (2000-01 to 2022-23)
  ABS Personal Income in Australia, 2022-23:
    Table 3.1 - National/regional total-income distribution summary stats (Gini-adjacent
                 percentile ratios, median, mean) - used only to sanity-check/calibrate,
                 since it covers ALL personal income (incl. non-lodgers), not just taxable
                 individuals.
"""
import re
from pathlib import Path

import openpyxl
import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def clean_header(h):
    if h is None:
        return ""
    return re.sub(r"\s+", " ", str(h)).strip()


def load_sheet_rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    return list(ws.iter_rows(values_only=True))


def extract_table3a():
    """Table 3A: 1320 rows x 84 items (count + $) by sex/taxable status/age/income range."""
    rows = load_sheet_rows(RAW / "ts23individual03.xlsx", "Table 3A")
    header = [clean_header(h) for h in rows[1]]
    dim_cols = header[:5]
    # column 5 ("Individuals no.") is a standalone count with no paired dollar column
    item_cols = header[6:]
    # pair up "<item> no." / "<item> $" into one base name
    bases = []
    for i in range(0, len(item_cols), 2):
        no_col = item_cols[i]
        base = re.sub(r"\s*no\.?$", "", no_col).strip()
        bases.append(base)

    records = []
    for r in rows[2:]:
        if r[0] is None:
            continue
        rec = dict(zip(dim_cols, r[:5]))
        rec["Individuals | count"] = r[5]
        for i, base in enumerate(bases):
            count_val = r[6 + 2 * i]
            dollar_val = r[6 + 2 * i + 1] if 6 + 2 * i + 1 < len(r) else None
            rec[f"{base} | count"] = count_val
            rec[f"{base} | dollars"] = dollar_val
        records.append(rec)

    df = pd.DataFrame(records)
    df.to_csv(OUT / "ato_table3a_items_by_bracket.csv", index=False)
    print(f"Table 3A -> {len(df)} rows, {len(df.columns)} columns")
    return df


def extract_table16b():
    rows = load_sheet_rows(RAW / "ts23individual16.xlsx", "Table 16B")
    header = [clean_header(h) for h in rows[1]]
    df = pd.DataFrame(rows[2:], columns=header)
    df = df.dropna(how="all")
    df.to_csv(OUT / "ato_table16b_percentiles.csv", index=False)
    print(f"Table 16B -> {len(df)} rows")
    return df


def extract_table16a():
    rows = load_sheet_rows(RAW / "ts23individual16.xlsx", "Table 16A")
    header = [clean_header(h) for h in rows[1]]
    df = pd.DataFrame(rows[2:], columns=header)
    df = df.dropna(how="all")
    df.to_csv(OUT / "ato_table16a_percentiles_by_state_sex.csv", index=False)
    print(f"Table 16A -> {len(df)} rows")
    return df


def extract_table19():
    rows = load_sheet_rows(RAW / "ts23individual19.xlsx", "Table 19")
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "ato_table19_100_people.csv", index=False, header=False)
    print(f"Table 19 -> {len(df)} rows (raw dump)")


def extract_table18():
    wb = openpyxl.load_workbook(RAW / "ts23individual18.xlsx", read_only=True, data_only=True)
    sheet = [s for s in wb.sheetnames if s.lower().startswith("table 18")][0]
    rows = load_sheet_rows(RAW / "ts23individual18.xlsx", sheet)
    header = [clean_header(h) for h in rows[1]]
    df = pd.DataFrame(rows[2:], columns=header)
    df = df.dropna(how="all")
    df.to_csv(OUT / "ato_table18_deductions.csv", index=False)
    print(f"Table 18 -> {len(df)} rows")


def extract_table1():
    wb = openpyxl.load_workbook(RAW / "ts23individual01.xlsx", read_only=True, data_only=True)
    sheet = [s for s in wb.sheetnames if s.lower().startswith("table 1")][0]
    rows = load_sheet_rows(RAW / "ts23individual01.xlsx", sheet)
    header = [clean_header(h) for h in rows[1]]
    df = pd.DataFrame(rows[2:], columns=header)
    df = df.dropna(how="all")
    df.to_csv(OUT / "ato_table1_by_year.csv", index=False)
    print(f"Table 1 -> {len(df)} rows")


def extract_abs_table3_1():
    rows = load_sheet_rows(RAW / "abs_table3_distribution.xlsx", "Table 3.1")
    label_row, unit_row = rows[5], rows[6]
    header = [clean_header(a) or clean_header(b) for a, b in zip(label_row, unit_row)]
    df = pd.DataFrame(rows[7:], columns=header)
    df = df.dropna(how="all")
    df.to_csv(OUT / "abs_table3_1_income_by_gccsa.csv", index=False)
    print(f"ABS Table 3.1 -> {len(df)} rows")


def extract_abs_table2():
    wb = openpyxl.load_workbook(RAW / "abs_table2_age_sex.xlsx", read_only=True, data_only=True)
    sheet = [s for s in wb.sheetnames if s.startswith("Table 2.1")]
    sheet = sheet[0] if sheet else "Table 2.1"
    rows = load_sheet_rows(RAW / "abs_table2_age_sex.xlsx", sheet)
    for i, r in enumerate(rows[:12]):
        pass
    # header row detection: find the row that starts with 'Age group' or similar
    header_idx = None
    for i, r in enumerate(rows):
        if r and any(c and "age" in str(c).lower() for c in r):
            header_idx = i
            break
    header = [clean_header(h) for h in rows[header_idx]] if header_idx is not None else []
    df = pd.DataFrame(rows[header_idx + 1 :], columns=header) if header_idx is not None else pd.DataFrame(rows)
    df = df.dropna(how="all")
    df.to_csv(OUT / "abs_table2_1_income_by_age_sex.csv", index=False)
    print(f"ABS Table 2.1 -> {len(df)} rows")


if __name__ == "__main__":
    extract_table3a()
    extract_table16b()
    extract_table16a()
    extract_table19()
    extract_table18()
    extract_table1()
    extract_abs_table3_1()
    extract_abs_table2()
    print("\nDone. Processed CSVs in", OUT)
