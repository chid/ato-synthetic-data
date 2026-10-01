"""
Extract the real data needed to make the static synthetic population move forward in
time: ABS Life Tables (mortality, for aging/death) and ABS population components
(births/deaths/net overseas migration, for new entrants).

Sources:
  ABS Life Tables, 2021-2023 (abs.gov.au) - Table 9: national life table by age (0-100)
    and sex. qx = probability of death within that year of age.
  ABS National, state and territory population (abs.gov.au) - Table 1: quarterly
    national births, deaths, interstate/overseas arrivals & departures, 1981-present.
"""
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def extract_life_table():
    wb = openpyxl.load_workbook(RAW / "abs_life_tables_2021_2023.xlsx", read_only=True, data_only=True)
    ws = wb["Table 9"]  # Australia, all states are Tables 1-8
    rows = list(ws.iter_rows(values_only=True))
    records = []
    for r in rows[7:108]:  # ages 0-100
        if r[0] is None:
            break
        age = int(r[0])
        records.append({"age": age, "sex": "Male", "qx": r[2]})
        records.append({"age": age, "sex": "Female", "qx": r[6]})
    df = pd.DataFrame(records)
    df.to_csv(OUT / "abs_life_table_national.csv", index=False)
    print(f"ABS Life Table (national, age 0-100 x sex) -> {len(df)} rows")


def extract_population_components():
    wb = openpyxl.load_workbook(RAW / "abs_pop_310101.xlsx", read_only=True, data_only=True)
    ws = wb["Data1"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data = [r[:8] for r in rows[10:]]  # first 10 rows are metadata (unit, series type, etc.)
    df = pd.DataFrame(data, columns=["quarter", "births", "deaths", "natural_increase",
                                       "interstate_arrivals", "interstate_departures",
                                       "overseas_arrivals", "overseas_departures"])
    df = df.dropna(subset=["quarter"])
    df["quarter"] = pd.to_datetime(df["quarter"])
    df["year"] = df["quarter"].dt.year
    df["net_overseas_migration"] = df["overseas_arrivals"] - df["overseas_departures"]
    # annual sums over the last 4 available quarters (rolling year, in '000s as published)
    annual = df.tail(4)[["births", "deaths", "net_overseas_migration"]].sum() * 1000
    annual_df = pd.DataFrame([annual])
    annual_df.insert(0, "period", f"{df['quarter'].iloc[-4].date()} to {df['quarter'].iloc[-1].date()}")
    annual_df.to_csv(OUT / "abs_population_components_latest_year.csv", index=False)
    df[["quarter", "year", "births", "deaths", "net_overseas_migration"]].to_csv(
        OUT / "abs_population_components_quarterly.csv", index=False
    )
    print(f"ABS population components -> {len(df)} quarterly rows, latest-year summary:\n{annual_df}")


def extract_population_totals():
    wb = openpyxl.load_workbook(RAW / "abs_pop_310104.xlsx", read_only=True, data_only=True)
    rows = list(wb["Data1"].iter_rows(values_only=True))
    records = [
        {"quarter": row[0].date().isoformat(), "population": row[27]}
        for row in rows[10:]
        if hasattr(row[0], "date") and row[27] is not None
    ]
    df = pd.DataFrame(records)
    df.to_csv(OUT / "abs_population_total_quarterly.csv", index=False)
    print(f"ABS national population totals -> {len(df)} quarterly rows")


if __name__ == "__main__":
    extract_life_table()
    extract_population_components()
    extract_population_totals()
    print("\nDone. Processed CSVs in", OUT)
