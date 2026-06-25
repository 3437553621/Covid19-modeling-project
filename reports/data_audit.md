# COVID-19 Data Audit

Country audited: `China`

## Summary

- Raw JHU global files are present for confirmed, deaths, and recovered.
- Processed country-level cumulative and daily values match independent recomputation from raw files with max absolute difference `0`.
- Recovered counts are reliable through `2021-08-04` for China; values from `2021-08-05` onward are marked missing rather than treated as true zeroes.
- Province-level cumulative totals reconcile exactly to the country-level cumulative totals. Province-level daily totals differ on correction days because negative daily changes are clipped per province for the regional panel, while the country table clips after country aggregation.

## Raw File Profile

| target    |   rows |   countries |   date_columns | start_date   | end_date   |   bad_date_columns |   date_null_cells |   negative_cells |   country_rows |   nonmonotonic_rows |
|:----------|-------:|------------:|---------------:|:-------------|:-----------|-------------------:|------------------:|-----------------:|---------------:|--------------------:|
| confirmed |    289 |         201 |           1143 | 2020-01-22   | 2023-03-09 |                  0 |                 0 |                0 |             34 |                 128 |
| deaths    |    289 |         201 |           1143 | 2020-01-22   | 2023-03-09 |                  0 |                 0 |                0 |             34 |                 106 |
| recovered |    274 |         201 |           1143 | 2020-01-22   | 2023-03-09 |                  0 |                 0 |                8 |             34 |                 259 |

## Processed File Profile

| file                           |   rows |   columns |   duplicate_rows |   null_cells | start_date   | end_date   | bad_dates   | duplicate_date_country_province   |
|:-------------------------------|-------:|----------:|-----------------:|-------------:|:-------------|:-----------|:------------|:----------------------------------|
| china_all_data_quality.csv     |      3 |        16 |                0 |            0 | N/A          | N/A        | N/A         | N/A                               |
| china_all_timeseries.csv       |   1143 |         9 |                0 |         1164 | 2020-01-22   | 2023-03-09 | 0           | 0                                 |
| china_beijing_data_quality.csv |      3 |        16 |                0 |            0 | N/A          | N/A        | N/A         | N/A                               |
| china_beijing_timeseries.csv   |   1143 |         9 |                0 |         1164 | 2020-01-22   | 2023-03-09 | 0           | 0                                 |
| china_province_timeseries.csv  |  38862 |         9 |                0 |        39588 | 2020-01-22   | 2023-03-09 | 0           | 0                                 |

## Country Aggregate Recalculation

| target    |   cumulative_max_abs_diff |   daily_max_abs_diff |   processed_missing_days | raw_terminal_reset_date   |   raw_terminal_missing_days |
|:----------|--------------------------:|---------------------:|-------------------------:|:--------------------------|----------------------------:|
| confirmed |                         0 |                    0 |                        0 | NONE                      |                           0 |
| deaths    |                         0 |                    0 |                        0 | NONE                      |                           0 |
| recovered |                         0 |                    0 |                      582 | 2021-08-05                |                         582 |

## Data Quality Summary File

| target    | country   | province   | start_date   | end_date   | reliable_end_date   |   days |   cumulative_start |   cumulative_end |   daily_max |   negative_daily_values_clipped |   zero_daily_days |   missing_days | terminal_zero_reset_date   |   terminal_zero_values_marked_missing | possible_reset_or_stop   |
|:----------|:----------|:-----------|:-------------|:-----------|:--------------------|-------:|-------------------:|-----------------:|------------:|--------------------------------:|------------------:|---------------:|:---------------------------|--------------------------------------:|:-------------------------|
| confirmed | China     | ALL        | 2020-01-22   | 2023-03-09 | 2023-03-09          |   1143 |                548 |      4.90352e+06 |       78859 |                               2 |                26 |              0 | NONE                       |                                     0 | False                    |
| deaths    | China     | ALL        | 2020-01-22   | 2023-03-09 | 2023-03-09          |   1143 |                 17 | 101056           |       59961 |                               1 |               429 |              0 | NONE                       |                                     0 | False                    |
| recovered | China     | ALL        | 2020-01-22   | 2023-03-09 | 2021-08-04          |   1143 |                 28 |  99228           |        3995 |                               4 |                12 |            582 | 2021-08-05                 |                                   582 | True                     |

## Negative Raw Daily Corrections

These raw negative changes are clipped to `0` in prepared daily series.

| target    | date       |   raw_daily_change |   processed_daily_after_clip |
|:----------|:-----------|-------------------:|-----------------------------:|
| confirmed | 2020-05-03 |                -16 |                            0 |
| confirmed | 2020-05-04 |                 -4 |                            0 |
| deaths    | 2022-11-15 |               -310 |                            0 |
| recovered | 2020-04-17 |               -849 |                            0 |
| recovered | 2021-07-10 |                -29 |                            0 |
| recovered | 2021-07-20 |                -39 |                            0 |
| recovered | 2021-07-23 |                 -3 |                            0 |

## Province Panel Sum Check

| column               |   max_abs_diff |   mismatched_dates |   matching_missing_status_dates |
|:---------------------|---------------:|-------------------:|--------------------------------:|
| cumulative_confirmed |              0 |                  0 |                            1143 |
| daily_confirmed      |            589 |                 28 |                            1143 |
| cumulative_deaths    |              0 |                  0 |                            1143 |
| daily_deaths         |             13 |                  2 |                            1143 |
| cumulative_recovered |              0 |                  0 |                            1143 |
| daily_recovered      |             99 |                 66 |                            1143 |

## Notes

- The JHU global recovered file stopped reporting many recovered series after 2021-08-04. Marking later values missing avoids fabricating recovered counts.
- Confirmed and deaths cumulative series contain a few country-level downward corrections. Prepared daily series clip those negative changes to `0`, as required by the project specification.
- For modeling daily recovered cases, downstream code should train only on non-missing recovered dates or clearly state that recovered data are unavailable after 2021-08-04.
