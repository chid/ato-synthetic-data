# Public country-by-country downloads

The local `downloads/` directory contains unchanged source downloads. It is ignored by Git. The public [source manifest](sources.json) records their URLs, checksums, observed coverage and reuse terms. No CbC data is relabelled as ATO data or combined with the AUD company disclosures.

## Available files

| Local file | Observed coverage | Units |
| --- | --- | --- |
| `downloads/taxplorer-data.csv` | 33,024 rows, 1,020 groups, 2,090 company-years, year labels 2014-2026 | Full EUR units; employees are headcounts |
| `downloads/taxplorer-data.xlsx` | Exact same headers and cell values as CSV, plus metadata | Full EUR units |
| `downloads/taxplorer-data.json` | 32,964 website rows, version 2026-09-19 | Website display amounts are rounded |
| `downloads/banks-cbcr.xlsx` | 6,587 DATA rows, 36 banks, 2014-2020 | Financial amounts in EUR millions; staff is a headcount |

The [Taxplorer source](https://www.taxplorer.eu/data/) includes mandatory and voluntary public company disclosures. Its CSV/Excel files retain 60 adjustment rows omitted from website JSON. They also retain numeric precision absent from JSON's rounded display values. Use CSV or Excel for analysis. Source blanks, negative profits and tax refunds are preserved.

The [bank dataset](https://taxobservatory.eu/repository/banks-country-by-country-reporting/) has 6,466 rows labelled `cbcr` and 121 labelled `computed or modified data`. Those labels are retained in the original workbook. Its [source working paper](https://www.taxobservatory.eu/www-site/uploads/2022/12/WP9_Tax-Planning-by-European-Banks_December2022-1.pdf), Appendix D, specifies EUR millions. Do not treat its numeric amounts as full EUR units or all its rows as direct unmodified disclosures. The bank population may overlap Taxplorer's groups, so the datasets are not additive.

## ATO availability

On 1 October 2026, the downloader checked all 43 datasets returned by the ATO's official data.gov.au organisation catalogue. It searched dataset names, titles, descriptions and resource names for CbC and country-by-country labels. No matching dataset was found. The query URLs and timestamp are retained in `sources.json`.

[ATO guidance](https://www.ato.gov.au/api/public/content/0-cdf60d77-063d-404a-a585-e36ee1e00e9c) expects the first public CbC publication in late 2026. [Public CbC reporting](https://softwaredevelopers.ato.gov.au/PublicCBCreporting) is distinct from confidential reports exchanged between tax administrations. The catalogue observation does not establish that no individual company has published a report elsewhere.

## Refresh and check

```sh
python3 scripts/download_public_cbc.py
python3 scripts/download_public_cbc.py --validate-only
```

The refresh checks the complete ATO catalogue and downloads resources from any matching dataset, then downloads the listed international sources. It preserves source bytes. Validation checks download checksums, byte counts, dataset coverage and every CSV value against its Excel counterpart. It does not audit every CbC number against the company's original filing.

## Attribution and reuse

Taxplorer: EU Tax Observatory, Taxplorer. Aliprandi, G., Borders, K., Gabriel, F., von Zedlitz, G. (2022), *Public Country-by-Country Reports: a new database*. The downloaded version is 2026-09-19. Taxplorer states CC BY-NC-ND 4.0 and additional [publisher terms](https://www.taxplorer.eu/licence/). Business use requires a licence, and republishing its database requires permission. These downloads remain local and unchanged. This repository publishes the downloader and source metadata.

Banks: EU Tax Observatory. Barake, M. (2022), *Tax Planning by European Banks*, Working Paper No. 9. No dataset-specific reuse licence was identified on the download page, so the workbook remains local and unchanged.

The project's MIT licence does not apply to downloaded third-party data. Neither dataset is a complete census of all public CbC reports worldwide.
