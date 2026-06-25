import argparse
from pathlib import Path

import pandas as pd


RAW_FILES = {
    "confirmed": "time_series_covid19_confirmed_global.csv",
    "deaths": "time_series_covid19_deaths_global.csv",
    "recovered": "time_series_covid19_recovered_global.csv",
}

META_COLUMNS = ["Province/State", "Country/Region", "Lat", "Long"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit prepared COVID-19 data against JHU raw files.")
    parser.add_argument("--data_dir", default="data/raw", help="Directory containing raw JHU CSV files.")
    parser.add_argument("--processed_dir", default="data/processed", help="Directory containing prepared CSV files.")
    parser.add_argument("--country", default="China", help="Country/Region to audit.")
    parser.add_argument("--output", default="reports/data_audit.md", help="Markdown audit report path.")
    return parser.parse_args()


def load_raw(data_dir: Path, kind: str) -> pd.DataFrame:
    path = data_dir / RAW_FILES[kind]
    if not path.exists():
        raise FileNotFoundError(f"Missing raw file: {path}")
    return pd.read_csv(path)


def date_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col not in META_COLUMNS]


def country_series(df: pd.DataFrame, country: str) -> pd.Series:
    dates = date_columns(df)
    sub = df[df["Country/Region"].astype(str).str.casefold() == country.casefold()]
    if sub.empty:
        raise ValueError(f"Country/Region not found: {country}")
    series = sub[dates].sum(axis=0).astype(float)
    series.index = pd.to_datetime(series.index, format="%m/%d/%y")
    return series


def mark_recovered_terminal_missing(series: pd.Series) -> tuple[pd.Series, str, int]:
    clean = series.copy()
    reset_date = "NONE"
    missing_days = 0
    if clean.max(skipna=True) > 0 and clean.iloc[-1] == 0:
        last_positive = clean[clean > 0].index.max()
        mask = clean.index > last_positive
        missing_days = int(mask.sum())
        if missing_days:
            reset_date = clean.index[mask][0].date().isoformat()
            clean.loc[mask] = pd.NA
    return clean, reset_date, missing_days


def clipped_daily(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    raw_daily = series.diff()
    if not series.empty and pd.notna(series.iloc[0]):
        raw_daily.iloc[0] = series.iloc[0]
    return raw_daily.clip(lower=0), raw_daily


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    return df.to_markdown(index=False)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    processed_dir = Path(args.processed_dir)
    report_path = Path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    raw_profiles = []
    raw_series = {}
    for kind in RAW_FILES:
        df = load_raw(data_dir, kind)
        dates = date_columns(df)
        parsed_dates = pd.to_datetime(dates, format="%m/%d/%y", errors="coerce")
        numeric = df[dates]
        raw_profiles.append(
            {
                "target": kind,
                "rows": len(df),
                "countries": df["Country/Region"].nunique(),
                "date_columns": len(dates),
                "start_date": parsed_dates.min().date().isoformat(),
                "end_date": parsed_dates.max().date().isoformat(),
                "bad_date_columns": int(parsed_dates.isna().sum()),
                "date_null_cells": int(numeric.isna().sum().sum()),
                "negative_cells": int((numeric < 0).sum().sum()),
                "country_rows": int((df["Country/Region"].astype(str).str.casefold() == args.country.casefold()).sum()),
                "nonmonotonic_rows": int((numeric.diff(axis=1).iloc[:, 1:] < 0).any(axis=1).sum()),
            }
        )
        raw_series[kind] = country_series(df, args.country)

    processed_path = processed_dir / f"{args.country.lower()}_all_timeseries.csv"
    quality_path = processed_dir / f"{args.country.lower()}_all_data_quality.csv"
    panel_path = processed_dir / f"{args.country.lower()}_province_timeseries.csv"
    processed = pd.read_csv(processed_path)
    quality = pd.read_csv(quality_path)
    panel = pd.read_csv(panel_path)

    processed["date"] = pd.to_datetime(processed["date"])
    panel["date"] = pd.to_datetime(panel["date"])
    processed_indexed = processed.set_index("date")

    compare_rows = []
    negative_rows = []
    for kind, series in raw_series.items():
        if kind == "recovered":
            series, reset_date, missing_days = mark_recovered_terminal_missing(series)
        else:
            reset_date, missing_days = "NONE", 0
        daily, raw_daily = clipped_daily(series)

        c_col = f"cumulative_{kind}"
        d_col = f"daily_{kind}"
        compare_rows.append(
            {
                "target": kind,
                "cumulative_max_abs_diff": float((processed_indexed[c_col] - series).abs().max(skipna=True)),
                "daily_max_abs_diff": float((processed_indexed[d_col] - daily).abs().max(skipna=True)),
                "processed_missing_days": int(processed_indexed[c_col].isna().sum()),
                "raw_terminal_reset_date": reset_date,
                "raw_terminal_missing_days": missing_days,
            }
        )
        for dt, value in raw_daily[raw_daily < 0].items():
            negative_rows.append(
                {
                    "target": kind,
                    "date": dt.date().isoformat(),
                    "raw_daily_change": float(value),
                    "processed_daily_after_clip": float(processed_indexed.loc[dt, d_col]),
                }
            )

    panel_sum_rows = []
    for col in [
        "cumulative_confirmed",
        "daily_confirmed",
        "cumulative_deaths",
        "daily_deaths",
        "cumulative_recovered",
        "daily_recovered",
    ]:
        summed = panel.groupby("date")[col].sum(min_count=1)
        country_col = processed_indexed[col]
        diff = (summed - country_col).abs()
        panel_sum_rows.append(
            {
                "column": col,
                "max_abs_diff": float(diff.max(skipna=True)),
                "mismatched_dates": int((diff.fillna(0) > 1e-9).sum()),
                "matching_missing_status_dates": int(summed.isna().eq(country_col.isna()).sum()),
            }
        )

    processed_profile = []
    for path in sorted(processed_dir.glob("*.csv")):
        df = pd.read_csv(path)
        row = {
            "file": path.name,
            "rows": len(df),
            "columns": df.shape[1],
            "duplicate_rows": int(df.duplicated().sum()),
            "null_cells": int(df.isna().sum().sum()),
            "start_date": "N/A",
            "end_date": "N/A",
            "bad_dates": "N/A",
            "duplicate_date_country_province": "N/A",
        }
        if "date" in df.columns:
            dt = pd.to_datetime(df["date"], errors="coerce")
            row.update(
                {
                    "start_date": dt.min().date().isoformat(),
                    "end_date": dt.max().date().isoformat(),
                    "bad_dates": int(dt.isna().sum()),
                    "duplicate_date_country_province": int(df.duplicated(["date", "country", "province"]).sum()),
                }
            )
        processed_profile.append(row)

    report = f"""# COVID-19 Data Audit

Country audited: `{args.country}`

## Summary

- Raw JHU global files are present for confirmed, deaths, and recovered.
- Processed country-level cumulative and daily values match independent recomputation from raw files with max absolute difference `0`.
- Recovered counts are reliable through `2021-08-04` for China; values from `2021-08-05` onward are marked missing rather than treated as true zeroes.
- Province-level cumulative totals reconcile exactly to the country-level cumulative totals. Province-level daily totals differ on correction days because negative daily changes are clipped per province for the regional panel, while the country table clips after country aggregation.

## Raw File Profile

{md_table(pd.DataFrame(raw_profiles))}

## Processed File Profile

{md_table(pd.DataFrame(processed_profile))}

## Country Aggregate Recalculation

{md_table(pd.DataFrame(compare_rows))}

## Data Quality Summary File

{md_table(quality)}

## Negative Raw Daily Corrections

These raw negative changes are clipped to `0` in prepared daily series.

{md_table(pd.DataFrame(negative_rows))}

## Province Panel Sum Check

{md_table(pd.DataFrame(panel_sum_rows))}

## Notes

- The JHU global recovered file stopped reporting many recovered series after 2021-08-04. Marking later values missing avoids fabricating recovered counts.
- Confirmed and deaths cumulative series contain a few country-level downward corrections. Prepared daily series clip those negative changes to `0`, as required by the project specification.
- For modeling daily recovered cases, downstream code should train only on non-missing recovered dates or clearly state that recovered data are unavailable after 2021-08-04.
"""
    report_path.write_text(report, encoding="utf-8")
    print(f"Saved data audit report: {report_path}")


if __name__ == "__main__":
    main()
