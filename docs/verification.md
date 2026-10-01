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

The publishing copy has a fresh Git history. It excludes the original virtual environment, Python caches, filesystem metadata, raw source downloads and downloaded web archives. The included input tables are published aggregates.

The public copy adds two small processed inputs so generation and validation run without source downloads: Census G01 national population counts by sex and ABS quarterly national population totals. The relevant readers use these CSVs. The longitudinal validator can also read the compressed panel.

Source and documentation scans checked for common credential formats, embedded credentials in URLs, private network references, local user paths and personal identifier columns. The region-name column `GCCSA NAME` contains geographic labels such as Greater Sydney, not person names. No credentials or person identifiers were found in the published files under these checks.

Dataset integrity checksums are in [SHA256SUMS](../SHA256SUMS). The original project's source files and datasets were unchanged.
