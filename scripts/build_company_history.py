"""Download all ATO corporate-transparency releases and build a sourced history."""
import argparse
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import build_company_data as companies

HISTORY_COLUMNS = ["release_year", "source_workbook", *companies.SOURCE_COLUMNS]
SECTIONS = {"income_tax": companies.INCOME_COLUMNS, "prrt": companies.PRRT_COLUMNS,
            "mrrt": companies.MRRT_COLUMNS}
MIRROR_PACKAGE_URL = "https://data.gov.au/data/api/3/action/package_show?id=2019-20_report_of_entity_tax_information"


def latest_observations(frame):
    """Prefer the newest release and its Combined sheet; never fill old values."""
    ordered = frame.copy()
    ordered["_identity"] = [f"abn:{abn}" if pd.notna(abn) else f"name:{name}"
                            for abn, name in zip(ordered["abn"], ordered["company_name"])]
    ordered["_priority"] = ordered["source_sheet"].eq("Combined").astype(int)
    ordered = ordered.sort_values(["release_year", "_priority", "source_row"], kind="stable")
    keys = ["_identity", "income_year", "release_year", "_priority"]
    preferred = ordered.loc[ordered.groupby(["_identity", "income_year", "release_year"])["_priority"].transform("max").eq(ordered["_priority"])]
    values = [column for column in companies.AMOUNT_COLUMNS if column in frame]
    conflicts = preferred.groupby(keys, dropna=False)[values].nunique(dropna=False)
    if (conflicts > 1).any().any():
        raise ValueError("Conflicting amounts for one entity/year in the same source release")
    result = ordered.drop_duplicates(["_identity", "income_year"], keep="last")
    return result.drop(columns=["_identity", "_priority"]).sort_values(
        ["income_year", "company_name"], kind="stable").reset_index(drop=True)


def history_summary(frames):
    rows = []
    for kind, frame in frames.items():
        for year, group in frame.groupby("income_year", sort=True):
            for column in companies.AMOUNT_COLUMNS:
                if column in group:
                    rows.append({"tax_type": kind, "income_year": year, "records": len(group),
                                 "abn_blank_records": int(group["abn"].isna().sum()),
                                 "amount_column": column, "reported_records": int(group[column].count()),
                                 "reported_sum": companies.amount_sum(group[column]),
                                 "blank_records": int(group[column].isna().sum())})
    return pd.DataFrame(rows)


def build_history(package, raw_dir, out_dir, download=True):
    collected = {kind: [] for kind in SECTIONS}
    releases = []
    workbooks = out_dir / "workbooks"
    workbooks.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    resources = []
    for resource in package["resources"]:
        try:
            year, _ = companies.select_resource({"resources": [resource]})
            resources.append((year, resource))
        except ValueError:
            continue
    for year, resource in sorted(resources):
        path = raw_dir / Path(resource["url"]).name
        if download:
            with urllib.request.urlopen(resource["url"], timeout=40) as response:
                path.write_bytes(response.read())
        copied = workbooks / path.name
        shutil.copyfile(path, copied)
        source = companies.read_source_records(path, year)
        release = {"release_year": year, "resource": {key: resource.get(key) for key in
                   ("id", "name", "url", "last_modified")},
                   "workbook": {"file": f"workbooks/{path.name}", "sha256": companies.file_hash(copied)},
                   "source_sections": {kind: companies.controls(frame) for kind, frame in source.items()}}
        releases.append(release)
        # Keep per-release exports available alongside the combined history.
        manifest = companies.build(path, out_dir, year, package, resource)
        companies.validate(manifest, path)
        for kind, frame in source.items():
            frame = frame.copy()
            frame["release_year"] = pd.array([year] * len(frame), dtype="string")
            frame["source_workbook"] = pd.array([path.name] * len(frame), dtype="string")
            collected[kind].append(frame[SECTIONS[kind] + HISTORY_COLUMNS])
        print(f"Verified {year}: {len(source['income_tax']):,} source income rows, "
              f"{len(source['prrt'])} PRRT, {len(source['mrrt'])} MRRT")
    files = {}
    histories = {}
    for kind, pieces in collected.items():
        all_rows = pd.concat(pieces, ignore_index=True)
        history = latest_observations(all_rows)
        histories[kind] = history
        for name, frame in ((f"{kind}_all_source_rows.csv", all_rows), (f"{kind}_history.csv", history)):
            path = out_dir / name
            frame.to_csv(path, index=False)
            files[name] = {"sha256": companies.file_hash(path), **companies.controls(frame)}
            reread = companies.read_csv(path, list(frame.columns))
            pd.testing.assert_frame_equal(reread, frame, check_dtype=False, check_exact=True)
    summary = out_dir / "history_summary.csv"
    history_summary(histories).to_csv(summary, index=False)
    files[summary.name] = {"sha256": companies.file_hash(summary)}
    alternate_workbooks = []
    mirror_metadata = raw_dir / "2019-20-mirror-package.json"
    if download:
        with urllib.request.urlopen(MIRROR_PACKAGE_URL, timeout=40) as response:
            mirror_package = json.load(response)["result"]
        mirror_metadata.write_text(json.dumps(mirror_package, indent=2) + "\n")
    if mirror_metadata.exists():
        mirror_package = json.loads(mirror_metadata.read_text())
        for resource in mirror_package["resources"]:
            name = "2019-20-mirror-" + Path(resource["url"]).name
            path = raw_dir / name
            if download:
                with urllib.request.urlopen(resource["url"], timeout=40) as response:
                    path.write_bytes(response.read())
            copied = workbooks / name
            shutil.copyfile(path, copied)
            canonical = next(release for release in releases if release["release_year"] == "2019-20")
            source = companies.read_source_records(workbooks / Path(canonical["workbook"]["file"]).name, "2019-20")
            alternate = companies.read_source_records(copied, "2019-20")
            for kind in SECTIONS:
                pd.testing.assert_frame_equal(source[kind], alternate[kind], check_dtype=False, check_exact=True)
            alternate_workbooks.append({"file": f"workbooks/{name}", "sha256": companies.file_hash(copied),
                                       "url": resource["url"], "metadata_url": MIRROR_PACKAGE_URL,
                                       "source_licence": mirror_package["license_title"],
                                       "note": "Separately catalogued 2019-20 workbook. All income-tax, PRRT and MRRT table rows match the canonical release; not counted twice."})
    manifest = {
        "publisher": "Australian Taxation Office, Commonwealth of Australia",
        "data_kind": "real public corporate disclosures, not synthetic",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_url": companies.DATASET_URL, "metadata_url": companies.PACKAGE_URL,
        "licence_url": package["license_url"], "source_licence": package["license_title"],
        "release_count": len(releases), "releases": releases, "alternate_workbooks": alternate_workbooks, "files": files,
        "amount_units": "annual Australian dollars; original fractional dollars retained",
        "history_selection": "Latest release for each ABN and income year. Missing ABN uses exact published name, without fuzzy matching. Combined supersedes December/March income snapshots in the first workbook. Entire rows are selected; blanks are not filled from older rows.",
        "all_source_rows": "All table rows, including repeated 2013-14 December, March and Combined income snapshots. These files are publication archives and must not be summed without selecting a snapshot.",
    }
    (out_dir / "source_history.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def validate_history(out_dir):
    manifest = json.loads((out_dir / "source_history.json").read_text())
    histories = {}
    for info in manifest.get("alternate_workbooks", []):
        if companies.file_hash(out_dir / info["file"]) != info["sha256"]:
            raise ValueError(f"Alternate workbook checksum mismatch: {info['file']}")
    for release in manifest["releases"]:
        workbook = out_dir / release["workbook"]["file"]
        if companies.file_hash(workbook) != release["workbook"]["sha256"]:
            raise ValueError(f"Workbook checksum mismatch: {workbook.name}")
        companies.validate(out_dir / f"source_{release['release_year'].replace('-', '_')}.json", workbook)
    for kind, columns in SECTIONS.items():
        frames = {}
        for suffix in ("all_source_rows", "history"):
            name = f"{kind}_{suffix}.csv"
            path = out_dir / name
            info = manifest["files"][name]
            if companies.file_hash(path) != info["sha256"]:
                raise ValueError(f"CSV checksum mismatch: {name}")
            frame = companies.read_csv(path, columns + HISTORY_COLUMNS)
            if any(companies.controls(frame)[key] != info[key] for key in companies.controls(frame)):
                raise ValueError(f"Source controls mismatch: {name}")
            frames[suffix] = frame
        source_pieces = []
        for release in manifest["releases"]:
            workbook = out_dir / release["workbook"]["file"]
            frame = companies.read_source_records(workbook, release["release_year"])[kind]
            frame["release_year"] = release["release_year"]
            frame["source_workbook"] = workbook.name
            source_pieces.append(frame[columns + HISTORY_COLUMNS])
        expected = pd.concat(source_pieces, ignore_index=True)
        pd.testing.assert_frame_equal(frames["all_source_rows"], expected, check_dtype=False, check_exact=True)
        pd.testing.assert_frame_equal(frames["history"], latest_observations(frames["all_source_rows"]), check_dtype=False, check_exact=True)
        histories[kind] = frames["history"]
    summary = out_dir / "history_summary.csv"
    if companies.file_hash(summary) != manifest["files"][summary.name]["sha256"]:
        raise ValueError("Summary checksum mismatch")
    pd.testing.assert_frame_equal(pd.read_csv(summary), history_summary(histories), check_dtype=False)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=companies.ROOT / "data/raw")
    parser.add_argument("--out-dir", type=Path, default=companies.ROOT / "data/companies")
    parser.add_argument("--metadata", type=Path, help="use cached package JSON and workbooks offline")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        manifest = validate_history(args.out_dir)
    else:
        if args.metadata:
            package = json.loads(args.metadata.read_text())
        else:
            with urllib.request.urlopen(companies.PACKAGE_URL, timeout=40) as response:
                package = json.load(response)["result"]
            args.raw_dir.mkdir(parents=True, exist_ok=True)
            (args.raw_dir / "corporate-transparency.json").write_text(json.dumps(package, indent=2) + "\n")
        build_history(package, args.raw_dir, args.out_dir, download=args.metadata is None)
        manifest = validate_history(args.out_dir)
    print(f"Verified all {manifest['release_count']} ATO releases")
    for kind in SECTIONS:
        info = manifest["files"][f"{kind}_history.csv"]
        print(f"{kind}_history.csv: {info['records']:,} entity-year records")


if __name__ == "__main__":
    main()
