import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_company_data as companies
import build_company_history as history
import download_public_cbc as cbc


class CompanyHistoryTests(unittest.TestCase):
    def test_old_sheet_separates_embedded_taxes_and_preserves_row_numbers(self):
        rows = [
            ("Income tax information for 2013-14", None, None, None, None),
            ("Name", "ABN", "Total Income $", "Taxable Income $", "Tax Payable $"),
            ("Company", None, 100000000, None, None),
            (None, None, None, None, None),
            ("PRRT information for 2013-14", None, None, None, None),
            ("Name", "ABN", "PRRT Payable $", None, None),
            ("Petroleum Company", 29086197757, 166500753, None, None),
            ("MRRT information for 2013-14", None, None, None, None),
            ("Name", "ABN", "MRRT Payable $", None, None),
            ("Minerals Company", 94600082111, 500, None, None),
        ]
        result = companies.parse_sheet(rows, "December", "2013-14")
        self.assertEqual(result["income_tax"], [["Company", None, 100000000, None, None, "2013-14", "December", 3]])
        self.assertEqual(result["prrt"], [["Petroleum Company", 29086197757, 166500753, "2013-14", "December", 7]])
        self.assertEqual(result["mrrt"], [["Minerals Company", 94600082111, 500, "2013-14", "December", 10]])

    def test_legacy_year_sheet_retains_late_year_and_fractional_dollars(self):
        rows = [
            ("This list consists of entities whose information was not available", None, None, None, None, None),
            ("Name", "ABN", "Total income $", "Taxable income $", "Tax payable $", None),
            ("Company", 94600082111, 100000000, None, 56171147.58, None),
        ]
        parsed = companies.parse_sheet(rows, "2014-15", "2015-16")["income_tax"]
        self.assertEqual(parsed[0][5], "2014-15")
        columns = companies.INCOME_COLUMNS + companies.SOURCE_COLUMNS
        frame = companies.records_frame(parsed, columns, columns, columns)
        self.assertEqual(frame.loc[0, "tax_payable"], 56171147.58)
        self.assertEqual(companies.controls(frame)["reported_amount_sums"]["tax_payable"], 56171147.58)

    def test_history_prefers_combined_then_latest_release_without_filling_blanks(self):
        columns = companies.INCOME_COLUMNS + history.HISTORY_COLUMNS
        frame = pd.DataFrame([
            ["Old Name", "94600082111", 100, 50, 15, "2013-14", "2013-14", "first.xlsx", "December", 3],
            ["Old Name", "94600082111", 100, 50, 16, "2013-14", "2013-14", "first.xlsx", "Combined", 2],
            ["Renamed Company", "94600082111", 110, 55, pd.NA, "2013-14", "2014-15", "second.xlsx", "2013-14", 2],
            ["No ABN", pd.NA, 200, 100, 30, "2013-14", "2013-14", "first.xlsx", "Combined", 5],
        ], columns=columns)
        first = history.latest_observations(frame.iloc[:2])
        self.assertEqual(first.iloc[0]["tax_payable"], 16)
        result = history.latest_observations(frame)
        self.assertEqual(len(result), 2)
        named = result.loc[result["company_name"].eq("Renamed Company")].iloc[0]
        self.assertTrue(pd.isna(named["tax_payable"]))
        self.assertEqual(named["total_income"], 110)
        self.assertEqual(named["release_year"], "2014-15")

    def test_conflicting_same_release_records_are_not_silently_selected(self):
        columns = companies.INCOME_COLUMNS + history.HISTORY_COLUMNS
        frame = pd.DataFrame([
            ["Company", "94600082111", 100, 50, 15, "2024-25", "2024-25", "source.xlsx", "Income tax details", 2],
            ["Company", "94600082111", 100, 50, 20, "2024-25", "2024-25", "source.xlsx", "Income tax details", 3],
        ], columns=columns)
        with self.assertRaisesRegex(ValueError, "Conflicting amounts"):
            history.latest_observations(frame)

    def test_cbc_discovery_checks_titles_notes_and_resource_names(self):
        self.assertTrue(cbc.is_public_cbc({"title": "Public Country-by-Country reporting"}))
        self.assertTrue(cbc.is_public_cbc({"notes": "CBC reports for public access"}))
        self.assertTrue(cbc.is_public_cbc({"resources": [{"name": "Public CbCR 2025"}]}))
        self.assertFalse(cbc.is_public_cbc({"name": "abc-cbc791e7", "title": "Geology data"}))
        self.assertFalse(cbc.is_public_cbc({"title": "Corporate tax transparency"}))


if __name__ == "__main__":
    unittest.main()
