"""
Extract the geography/industry ATO tables and the genuine ABS Census 2021 tables into
tidy CSVs, to add state/postcode/industry to the synthetic generator and to
cross-check it against an independent (non-tax) data source.

ATO Taxation Statistics 2022-23 (data.gov.au), admin tax data:
  Table 5  (ts23individual05.xlsx) - sex x state x broad industry, ~80 items (count+$)
  Table 6A (ts23individual06.xlsx) - taxable status x state x SA4 x postcode, ~80 items

ABS Census of Population and Housing 2021 (abs.gov.au datapacks), independent survey data:
  G02 - Medians and averages (incl. median total personal income, weekly) by POA/STE/AUS
  G54 - Industry of employment by age by sex, by STE (parts A-D)
"""
import re
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

STE_CODE_TO_ABBR = {
    "1": "NSW", "2": "VIC", "3": "QLD", "4": "SA",
    "5": "WA", "6": "TAS", "7": "NT", "8": "ACT", "9": "OT",
}

AGE_BANDS_CENSUS = ["15_19", "20_24", "25_34", "35_44", "45_54", "55_64", "65_74", "75_84", "85ov"]

INDUSTRY_ATO_TO_CENSUS = {
    "a. Agriculture, Forestry and Fishing": "Ag_For_Fshg",
    "b. Mining": "Mining",
    "c. Manufacturing": "Manufact",
    "d. Electricity, Gas, Water and Waste Services": "El_Gas_Wt_Waste",
    "e. Construction": "Constru",
    "f. Wholesale Trade": "WhlesaleTde",
    "g. Retail Trade": "RetTde",
    "h. Accommodation and Food Services": "Accom_food",
    "i. Transport, Postal and Warehousing": "Trans_post_wrehsg",
    "j. Information Media and Telecommunications": "Info_media_teleco",
    "k. Financial and Insurance Services": "Fin_Insur",
    "l. Rental, Hiring and Real Estate Services": "RtnHir_REst",
    "m. Professional, Scientific and Technical Services": "Pro_scien_tec",
    "n. Administrative and Support Services": "Admin_supp",
    "o. Public Administration and Safety": "Public_admin_sfty",
    "p. Education and Training": "Educ_trng",
    "q. Health Care and Social Assistance": "HlthCare_SocAs",
    "r. Arts and Recreation Services": "Art_recn",
    "s. Other Services": "Oth_scs",
    "z. Other": "ID_NS",  # not an exact concept match - see APPROACH.md
}


def clean_header(h):
    if h is None:
        return ""
    return re.sub(r"\s+", " ", str(h)).strip()


def load_sheet_rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return list(wb[sheet].iter_rows(values_only=True))


def pair_items(rows, header_row_idx, dim_count):
    """Generic ATO table parser: first `dim_count` columns are dimensions, the next
    is a standalone "Individuals no." count, and the rest are (item no., item $) pairs
    sharing one base name each (same layout as Table 3A)."""
    header = [clean_header(h) for h in rows[header_row_idx]]
    dim_cols = header[:dim_count]
    item_cols = header[dim_count + 1 :]
    bases = [re.sub(r"\s*no\.?$", "", item_cols[i]).strip() for i in range(0, len(item_cols), 2)]

    records = []
    for r in rows[header_row_idx + 1 :]:
        if r[0] is None:
            continue
        rec = dict(zip(dim_cols, r[:dim_count]))
        rec["Individuals | count"] = r[dim_count]
        for i, base in enumerate(bases):
            c = dim_count + 1 + 2 * i
            rec[f"{base} | count"] = r[c] if c < len(r) else None
            rec[f"{base} | dollars"] = r[c + 1] if c + 1 < len(r) else None
        records.append(rec)
    return pd.DataFrame(records)


def extract_table5_industry():
    rows = load_sheet_rows(RAW / "ts23individual05.xlsx", "Table 5")
    df = pair_items(rows, header_row_idx=1, dim_count=3)
    df.to_csv(OUT / "ato_table5_items_by_industry.csv", index=False)
    print(f"Table 5 (industry) -> {len(df)} rows, {len(df.columns)} cols")
    return df


def extract_table6a_postcode():
    rows = load_sheet_rows(RAW / "ts23individual06.xlsx", "Table 6A")
    df = pair_items(rows, header_row_idx=1, dim_count=4)
    df.to_csv(OUT / "ato_table6a_items_by_postcode.csv", index=False)
    print(f"Table 6A (postcode) -> {len(df)} rows, {len(df.columns)} cols")
    return df


def extract_census_g01():
    path = RAW / "census2021_gcp_aus" / "2021 Census GCP Australia for AUS" / "2021Census_G01_AUS_AUS.csv"
    df = pd.read_csv(path, usecols=["Tot_P_M", "Tot_P_F"])
    df.to_csv(OUT / "census_g01_counts_national.csv", index=False)
    print(f"Census G01 (national population by sex) -> {len(df)} rows")


def extract_census_g02():
    for geo, fname_in, fname_out in [
        ("POA", "census2021_gcp_poa/2021 Census GCP Postal Areas for AUS/2021Census_G02_AUST_POA.csv", "census_g02_medians_by_postcode.csv"),
        ("STE", "census2021_gcp_ste/2021 Census GCP States and Territories for AUS/2021Census_G02_AUST_STE.csv", "census_g02_medians_by_state.csv"),
        ("AUS", "census2021_gcp_aus/2021 Census GCP Australia for AUS/2021Census_G02_AUS_AUS.csv", "census_g02_medians_national.csv"),
    ]:
        df = pd.read_csv(RAW / fname_in)
        code_col = df.columns[0]
        if geo == "POA":
            df["postcode"] = df[code_col].str.replace("POA", "", regex=False).astype(int)
        elif geo == "STE":
            df["state"] = df[code_col].astype(str).map(STE_CODE_TO_ABBR)
        df.to_csv(OUT / fname_out, index=False)
        print(f"Census G02 ({geo}) -> {len(df)} rows -> {fname_out}")


def extract_census_g54_industry():
    """Industry of employment by age by sex, by state - long format."""
    base = RAW / "census2021_gcp_ste" / "2021 Census GCP States and Territories for AUS"
    frames = [pd.read_csv(base / f"2021Census_G54{p}_AUST_STE.csv") for p in "ABCD"]
    wide = frames[0]
    for f in frames[1:]:
        wide = wide.merge(f, on="STE_CODE_2021")
    wide["state"] = wide["STE_CODE_2021"].astype(str).map(STE_CODE_TO_ABBR)

    records = []
    industries = sorted(INDUSTRY_ATO_TO_CENSUS.values())
    for _, row in wide.iterrows():
        for sex_prefix, sex in [("M", "Male"), ("F", "Female")]:
            for industry in industries:
                total_col = f"{sex_prefix}_{industry}_Tot"
                if total_col not in wide.columns:
                    continue
                for age in AGE_BANDS_CENSUS:
                    col = f"{sex_prefix}_{industry}_{age}"
                    if col not in wide.columns:
                        continue
                    records.append(
                        {
                            "state": row["state"],
                            "sex": sex,
                            "age_band_census": age,
                            "industry_census_code": industry,
                            "persons": row[col],
                        }
                    )
    df = pd.DataFrame(records)
    df.to_csv(OUT / "census_g54_industry_by_age_sex_state.csv", index=False)
    print(f"Census G54 (industry) -> {len(df)} rows (long format)")


def extract_abs_hiw_percentiles():
    """ABS Household Income and Wealth 2019-20, Table 1.1: equivalised disposable
    HOUSEHOLD income percentile points (P10-P90), weekly. Different concept/population
    from ATO's individual taxable income (household, equivalised, disposable, survey-
    based, 2019-20 vintage) -- kept as an independent order-of-magnitude/shape check
    only, not a calibration input. See APPROACH.md."""
    rows = load_sheet_rows(RAW / "abs_hiw_table1_income_distribution.xlsx", "Table 1.1")
    year_col = rows[4].index("2019–20")
    records = []
    for r in rows[16:25]:
        label = clean_header(r[0])
        m = re.search(r"P(\d+)", label)
        if not m:
            continue
        pct = int(m.group(1))
        records.append({"percentile": pct, "weekly_dollars": r[year_col], "annual_dollars": r[year_col] * 52})
    df = pd.DataFrame(records)
    df.to_csv(OUT / "abs_hiw_equivalised_household_income_percentiles.csv", index=False)
    print(f"ABS HIW Table 1.1 (household income percentiles) -> {len(df)} rows")


if __name__ == "__main__":
    extract_table5_industry()
    extract_table6a_postcode()
    extract_census_g01()
    extract_census_g02()
    extract_census_g54_industry()
    extract_abs_hiw_percentiles()
    print("\nDone. Processed CSVs in", OUT)
