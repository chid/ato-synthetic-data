import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_company_data as companies


class CompanyDataTests(unittest.TestCase):
    def workbook(self):
        income = MagicMock()
        income.iter_rows.return_value = iter([
            companies.INCOME_HEADERS,
            ("NA", 94600082111, 108996236, 10603699, 3181110, "2024-25"),
            ("26 RYDE PTY LTD", None, 154334997, 178056693, 47989151, "2024-25"),
            ("LOSS COMPANY PTY LTD", 95650096094, 602173980, None, None, "2024-25"),
            ("LATE COMPANY PTY LTD", 83114980880, 319135614, 18129064, 5438719, "2023-24"),
        ])
        prrt = MagicMock()
        prrt.iter_rows.return_value = iter([
            companies.PRRT_HEADERS,
            ("CHEVRON AUSTRALIA PTY LTD", 29086197757, 166500753),
        ])
        book = MagicMock()
        book.__getitem__.side_effect = {"Income tax details": income, "PRRT details": prrt}.__getitem__
        return book

    def test_latest_release_uses_income_year_not_resource_order(self):
        package = {"resources": [
            {"name": "2023-24 Report of Entity Tax Information"},
            {"name": "2024-25 Report of Entity Tax Information"},
            {"name": "2013-14 Report of Entity Tax Information"},
        ]}
        self.assertEqual(companies.select_resource(package)[0], "2024-25")
        self.assertEqual(companies.select_resource(package, "2023-24")[0], "2023-24")
        with self.assertRaisesRegex(ValueError, "No ATO company release"):
            companies.select_resource(package, "2025-26")

    def test_source_years_and_blanks_are_preserved(self):
        with patch.object(companies.openpyxl, "load_workbook", return_value=self.workbook()):
            frames = companies.read_workbook(Path("source.xlsx"), "2024-25")
        current = frames["companies"]
        self.assertEqual(current["company_name"].tolist(), ["NA", "26 RYDE PTY LTD", "LOSS COMPANY PTY LTD"])
        self.assertEqual(current.loc[0, "abn"], "94600082111")
        self.assertTrue(pd.isna(current.loc[1, "abn"]))
        self.assertEqual(current.loc[1, "taxable_income"], 178056693)
        self.assertTrue(pd.isna(current.loc[2, "taxable_income"]))
        self.assertTrue(pd.isna(current.loc[2, "tax_payable"]))
        self.assertEqual(frames["late_returns"]["income_year"].tolist(), ["2023-24"])
        self.assertEqual(frames["prrt"].iloc[0].to_dict(), {
            "company_name": "CHEVRON AUSTRALIA PTY LTD", "abn": "29086197757",
            "prrt_payable": 166500753, "income_year": "2024-25",
        })
        summary = companies.summary_frame(frames, "2024-25").set_index("income_year")
        self.assertEqual(summary.loc["2024-25", "tax_payable_reported_sum"], 51170261)
        self.assertEqual(summary.loc["2024-25", "tax_payable_blank_records"], 1)
        self.assertEqual(summary.loc["2023-24", "records"], 1)

    def test_csv_roundtrip_and_tampering_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "source.xlsx"
            workbook.write_bytes(b"fixture source")
            with patch.object(companies.openpyxl, "load_workbook", return_value=self.workbook()):
                manifest_path = companies.build(workbook, root, "2024-25")
            manifest = companies.validate(manifest_path)
            path = root / manifest["files"]["companies"]["file"]
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["company_name"], "NA")
            self.assertEqual(rows[2]["tax_payable"], "")
            self.assertEqual(rows[0]["total_income"], "108996236")
            self.assertEqual(manifest["files"]["companies"]["records"], 3)
            self.assertEqual(manifest["files"]["companies"]["reported_amount_sums"]["tax_payable"], 51170261)
            path.write_text(path.read_text().replace("LOSS COMPANY", "ALTERED COMPANY"))
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                companies.validate(manifest_path)

    def test_rejects_source_schema_changes_and_noninteger_abns(self):
        with self.assertRaisesRegex(ValueError, "Unexpected source columns"):
            companies.records_frame([], ["Changed"], companies.INCOME_HEADERS, companies.INCOME_COLUMNS)
        with self.assertRaisesRegex(ValueError, "11 digits"):
            companies.records_frame([("Company", "123", 100, None, None, "2024-25")],
                                    companies.INCOME_HEADERS, companies.INCOME_HEADERS, companies.INCOME_COLUMNS)
        with self.assertRaisesRegex(ValueError, "not an integer"):
            companies.records_frame([("Company", 123.5, 100, None, None, "2024-25")],
                                    companies.INCOME_HEADERS, companies.INCOME_HEADERS, companies.INCOME_COLUMNS)


if __name__ == "__main__":
    unittest.main()
