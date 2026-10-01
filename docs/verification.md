# Publication verification

Checked on 1 October 2026 with Python 3.14 and the dependencies pinned in `requirements.txt`.

## Reproducibility

All seven supplied synthetic files matched fresh generation byte for byte with seed 42 and a starting population of 20,000. For the compressed panel, the comparison used its decompressed CSV bytes.

- Static generator: 20,000 rows.
- Longitudinal simulation: ten forward years, 237,808 panel rows and eleven annual summaries.
- 2012-13 backtest: ten forward years, 23,664 final rows and eleven annual summaries.
- 2009-10 backtest: thirteen forward years, 24,669 final rows and fourteen annual summaries.

All four validation scripts completed with exit code zero. They report statistical comparisons; they do not enforce pass/fail thresholds for distribution accuracy. Pandas issued fragmentation performance warnings during generation, without changing the outputs.

The backtest validators compare predicted median income with the current synthetic sample's median. That comparison does not provide an independent official median-income target. Backtests also retain the source release-date limitation described in [SOURCES.md](../SOURCES.md#backtest-source-date-correction).

## Public-copy changes

### Named public company data

All 12 corporate tax-transparency releases, 2013-14 through 2024-25, were downloaded and validated. The combined history contains 33,051 income-tax entity-year rows, 148 PRRT rows and 7 MRRT rows. The income-tax publication archive retains all 34,910 source rows, including the early December/March/Combined snapshots. Original workbook checksums are included. The separately catalogued 2019-20 copy has a different binary checksum but identical tax-table values.

An independent check read every exported archive row using the standard-library CSV reader and compared names, ABNs, financial values, blanks and income years with its original workbook sheet and row. It also accounted for every populated financial source row. The two source amounts containing fractional dollars were preserved. Canonical histories were verified against the declared latest-release selection and source controls.

The CbC download checks covered the complete 43-dataset ATO catalogue, file checksums and every value in the 33,024-row Taxplorer CSV against its Excel counterpart. The JSON website file is separately recorded with 32,964 rows, rounded amounts and no adjustment rows. The bank workbook has 6,587 rows, including 121 labelled computed or modified data. CbC figures were not individually audited against all original company filings. All nineteen repository tests pass.

The latest corporate tax-transparency release was discovered through the official data.gov.au metadata API on 1 October 2026. The downloaded 2024-25 workbook's SHA-256 is recorded in `data/companies/source_2024_25.json`. Every name, published ABN, integer amount, blank and income-year label was compared with the original worksheet rows after CSV export.

The current-year file contains 4,299 records. It matches source sums of $3,342,185,114,932 total income, $349,136,493,123 taxable income and $87,488,527,889 tax payable. All 961 blank taxable-income values, 1,149 blank tax-payable values and 31 blank ABNs are preserved. Separate files retain all 116 late returns and all 21 PRRT records. The PRRT amount sum is $1,872,820,121.

Four company-data tests cover latest-release selection, separating income years, literal source values, blank amounts, missing ABNs, CSV roundtrips, unexpected headers and changed-file detection. All nineteen repository tests pass. The offline validator checks the exported files against the manifest and summary. With `--workbook`, it also compares all source records. These are exact disclosure-data checks, distinct from the synthetic distribution comparisons below.

### Named public company data and CbC sources moved

Moved on review to a separate repo, `ato-company-tax-data`: real, named corporate
disclosures and the CbC download tooling answer a different question from the
synthetic individual population and made it easy to confuse real rows with simulated
ones when both lived in one repo. `scripts/build_company_data.py`,
`build_company_history.py`, `download_public_cbc.py`, `data/companies/`, `data/cbc/`,
`docs/company-data.md`, and their five tests (the four company-data tests above plus
the company-history/CbC-discovery tests) moved with it; none of it runs here anymore.
Nothing in the synthetic individual model depended on it, so this is a removal of
unrelated content, not a reduction in the individual model's fidelity.

### Fictional display names

All population datasets now include `first_name`, `last_name` and `full_name`, generated with Faker 40.40.0 in the `en_AU` locale. The standalone `scripts/generate_names.py` command produces a seeded CSV. Names use an independent random generator. The longitudinal panel assigns one name per unique `agent_id`, so new entrants receive their own generated names and returning agents keep theirs.

Seven name tests cover the exact seeded CLI output, repeatability, independent global random state, SeedSequence support, preservation of existing records, agent identity and invalid counts. Those checks and the three signed-item tests continue to pass. All four population outputs were regenerated with the existing model seeds. Comparisons against the previous committed datasets verify that every pre-existing column and all annual summaries are unchanged.

### Fictional names removed

Removed on review: Faker's `en_AU` locale does not model Australian name-frequency distributions by age or ancestry, and the names were added to every population output unconditionally rather than as an opt-in. `scripts/generate_names.py`, `tests/test_names.py` and the `Faker` dependency are removed; the `first_name`, `last_name` and `full_name` columns no longer appear in any output. The seven name tests above no longer run. All four population outputs were regenerated without those columns; every other column and all annual summaries are unchanged from the signed-loss-corrected versions.

### Signed loss correction

The static and 2012-13 item samplers previously discarded negative source means. They now sample the absolute amount and restore the source sign. This also fixes losses in the longitudinal simulation, which reuses the static item sampler. The static sample, longitudinal panel and 2012-13 snapshot were regenerated with seed 42. The 2009-10 sampler already preserved signs.

Three regression tests pass. Before the fix, two failed with "Rental losses were all zero" and "The 2013 backtest discarded signed rental losses". The positive and zero item test passed before and after the correction. In the static sample, only `net_rent_loss` and `total_income` changed. Both affected annual summary files were unchanged.

| Statistic, across all lodgers | Synthetic | ATO |
| --- | ---: | ---: |
| Rental-loss presence | 7.565% | 7.010% |
| Mean rental loss | -$701.90 | -$655.17 |
| Mean rental profit | $767.01 | $753.98 |
| Mean net rental income | $65.11 | $98.81 |

The validator counts negative amounts as present and compares taxable-income means using the same all-lodger denominator. Preserving signed losses fixes the discarded-loss bug. Aggregate sample differences and independent financial draws remain.

The publishing copy has a fresh Git history. It excludes the original virtual environment, Python caches, filesystem metadata, raw source downloads and downloaded web archives. The included individual-model input tables are published aggregates. The separately labelled company files contain real corporate disclosures from ATO's public workbook.

The public copy adds two small processed inputs so generation and validation run without source downloads: Census G01 national population counts by sex and ABS quarterly national population totals. The relevant readers use these CSVs. The longitudinal validator can also read the compressed panel.

Source and documentation scans checked for common credential formats, embedded credentials in URLs, private network references, local user paths and unintended identifier columns. The region-name column `GCCSA NAME` contains geographic labels such as Greater Sydney. The three new name columns are deliberately generated display labels. No real-person source records or credentials are included.

Dataset integrity checksums are in [SHA256SUMS](../SHA256SUMS). The signed-loss correction and regenerated affected datasets were also applied to the original workspace.
