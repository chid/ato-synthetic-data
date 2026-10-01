# Sources and attribution

Source links and licence information checked on 1 October 2026. This repository contains reshaped aggregate tables, published corporate disclosures and simulated outputs. The MIT code licence does not replace source-data licences.

## Australian Taxation Office

Based on Australian Taxation Office Taxation Statistics data, Commonwealth of Australia. The processed tables retain published dimensions, counts and dollar totals, with tidy column names and CSV formatting.

| Publication | Included tables | Licence |
| --- | --- | --- |
| [Taxation Statistics 2022-23](https://data.gov.au/data/dataset/taxation-statistics-2022-23) | Individuals Tables 1, 3A, 5, 6A, 16A, 16B, 18 and 19 | [CC BY 2.5 Australia](https://creativecommons.org/licenses/by/2.5/au/) |
| [Taxation Statistics 2012-13](https://data.gov.au/data/dataset/taxation-statistics-2012-13) | Individuals Tables 3 and 14 | [CC BY 3.0 Australia](https://creativecommons.org/licenses/by/3.0/au/) |
| [Taxation Statistics 2009-10](https://data.gov.au/data/dataset/taxation-statistics-2009-10) | Personal tax Table PER11 | [CC BY 3.0 Australia](https://creativecommons.org/licenses/by/3.0/au/) |

The dataset metadata and licence identifiers are also available through the [data.gov.au package API](https://data.gov.au/data/api/3/action/package_show?id=taxation-statistics-2022-23), substituting the dataset slug for each vintage.

(Real, named ATO corporate tax-transparency disclosures and public country-by-country
sources previously documented here now live in the separate
[`ato-company-tax-data`](https://github.com/chid/ato-company-tax-data) repo, with their
own sources file.)

## Australian Bureau of Statistics

Based on Australian Bureau of Statistics data, Commonwealth of Australia. ABS data used with permission from the Australian Bureau of Statistics. This project reshapes the published tables, selects columns, aggregates counts and derives annual amounts from weekly amounts where documented in the extraction scripts.

| Publication | Use |
| --- | --- |
| [Personal Income in Australia, 2022-23](https://www.abs.gov.au/statistics/labour/earnings-and-working-conditions/personal-income-australia/2022-23) | Tables 2 and 3 for distribution comparisons |
| [Census 2021 DataPacks](https://www.abs.gov.au/census/find-census-data/datapacks) | General Community Profile G01 national counts, G02 medians and G54 industry by age and sex |
| [Household Income and Wealth, 2019-20](https://www.abs.gov.au/statistics/economy/finance/household-income-and-wealth-australia/2019-20) | Table 1 income percentile comparisons |
| [Life Tables, 2021-2023](https://www.abs.gov.au/statistics/people/population/life-tables/2021-2023) | National mortality by age and sex |
| [Life Tables, 2016-2018](https://www.abs.gov.au/statistics/people/population/life-tables/2016-2018) | Retained older extracted reference table |
| [National, state and territory population](https://www.abs.gov.au/statistics/people/population/national-state-and-territory-population) | Quarterly population components, archived input snapshot |
| [Population by age and sex, Australia](https://www.abs.gov.au/statistics/people/population/national-state-and-territory-population) | Table 3101059, single-year age counts and historical age profiles |

ABS publishes website material under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to its [copyright policy and exclusions](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer). Product-specific licence notices continue to apply. No ABS unit record microdata, logos or Census artwork are included.

## Australian Government Actuary

This work includes Australian Life Tables 2005-07 and 2010-12 published by the Australian Government Actuary, an entity of the Commonwealth of Australia. The repository extracts age, sex and annual mortality probabilities into CSVs. These tables are modified extracts, not the original publications.

- [Australian Life Tables 2005-07](https://aga.gov.au/publications/life-tables/australian-life-tables-2005-07), published 27 November 2009.
- [Australian Life Tables 2010-12](https://aga.gov.au/publications/life-tables/australian-life-tables-2010-12), published 10 December 2014. The [2010-12 publication](https://aga.gov.au/sites/aga.gov.au/files/publications/life_table_2010-12/downloads/Australian_Life_Tables_2010-12_Final_V2.pdf) carries [CC BY 3.0 Australia](https://creativecommons.org/licenses/by/3.0/au/).

The AGA's current [copyright policy](https://aga.gov.au/copyright-disclaimer) publishes its website material under CC BY 4.0, except the stated exclusions. Retain any publication-specific licence notices and credit the AGA when reusing its data. The 2010-12 extracts retain the publication's CC BY 3.0 Australia terms.

## Backtest source date correction

The original development notes and some code comments describe the AGA 2010-12 life table as available to a 2013 forecaster. Its publication date was 10 December 2014. Its observation period precedes the forecast period, but its release did not. The public copy preserves the existing numerical model and labels the backtests as experimental historical-vintage comparisons. They are not fully audited simulations of information available at each forecast date.

## Synthetic outputs

The project creates every row in `synthetic/` by random sampling and simulation. The outputs are neither ATO taxpayer records nor ABS microdata. Geographic codes and demographic categories come from public aggregates.

The project-created outputs are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit `chid/ato-synthetic-data` and retain attribution to ATO, ABS and AGA for the underlying sources. None of these agencies endorses this project.
