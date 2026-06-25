from pathlib import Path

import pandas as pd


TIME_SERIES_FILES = {
    "confirmed": "time_series_covid19_confirmed_global.csv",
    "deaths": "time_series_covid19_deaths_global.csv",
    "recovered": "time_series_covid19_recovered_global.csv",
}

META_COLUMNS = ["Province/State", "Country/Region", "Lat", "Long"]


def get_time_series_path(data_dir: str | Path, kind: str) -> Path:
    """Return the raw JHU time-series file path for one target kind."""
    if kind not in TIME_SERIES_FILES:
        raise ValueError(f"Unknown kind: {kind}. Expected one of {sorted(TIME_SERIES_FILES)}")

    path = Path(data_dir) / TIME_SERIES_FILES[kind]
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {kind} data file: {path}. Please place JHU CSSE time-series CSV files in data/raw."
        )
    return path


def load_jhu_timeseries(data_dir: str | Path, kind: str) -> pd.DataFrame:
    """Load one JHU CSSE global time-series table."""
    return pd.read_csv(get_time_series_path(data_dir, kind))


def get_date_columns(df: pd.DataFrame) -> list[str]:
    """JHU global tables keep dates as wide columns after the first four metadata fields."""
    return [col for col in df.columns if col not in META_COLUMNS]


def list_countries(data_dir: str | Path) -> list[str]:
    df = load_jhu_timeseries(data_dir, "confirmed")
    return sorted(df["Country/Region"].dropna().unique().tolist())


def list_provinces(data_dir: str | Path, country: str) -> list[str]:
    df = load_jhu_timeseries(data_dir, "confirmed")
    sub = _filter_country(df, country)
    return sorted(sub["Province/State"].fillna("").astype(str).unique().tolist())


def aggregate_region(
    df: pd.DataFrame,
    country: str,
    province: str | None = None,
    exclude_provinces: list[str] | None = None,
) -> pd.Series:
    """Aggregate a JHU wide table into a single cumulative series.

    If province is empty, all rows for the country are summed. If province is supplied,
    only that Province/State row is used.
    """
    sub = _filter_country(df, country)
    if province:
        province_key = province.strip().casefold()
        sub = sub[sub["Province/State"].fillna("").astype(str).str.casefold() == province_key]
        if sub.empty:
            available = sorted(_filter_country(df, country)["Province/State"].fillna("").astype(str).unique())
            raise ValueError(f"Province not found for {country!r}: {province!r}. Available: {available[:20]}")
    elif exclude_provinces:
        excluded = {item.strip().casefold() for item in exclude_provinces if item.strip()}
        province_names = sub["Province/State"].fillna("").astype(str).str.casefold()
        sub = sub[~province_names.isin(excluded)]

    date_cols = get_date_columns(df)
    cumulative = sub[date_cols].sum(axis=0)
    cumulative.index = pd.to_datetime(cumulative.index, format="%m/%d/%y")
    cumulative = cumulative.sort_index()
    cumulative.name = "cumulative"
    return cumulative


def province_panel(df: pd.DataFrame, country: str, exclude_provinces: list[str] | None = None) -> pd.DataFrame:
    """Convert one country's province-level wide table to a long cumulative panel."""
    sub = _filter_country(df, country).copy()
    if exclude_provinces:
        excluded = {item.strip().casefold() for item in exclude_provinces if item.strip()}
        province_names = sub["Province/State"].fillna("").astype(str).str.casefold()
        sub = sub[~province_names.isin(excluded)]
    date_cols = get_date_columns(df)
    if sub.empty:
        raise ValueError(f"Country/Region not found: {country!r}")

    panel = sub.melt(
        id_vars=["Province/State", "Country/Region"],
        value_vars=date_cols,
        var_name="date",
        value_name="cumulative",
    )
    panel["date"] = pd.to_datetime(panel["date"], format="%m/%d/%y")
    panel["province"] = panel["Province/State"].fillna("")
    panel["country"] = panel["Country/Region"]
    return panel[["date", "country", "province", "cumulative"]].sort_values(["province", "date"])


def _filter_country(df: pd.DataFrame, country: str) -> pd.DataFrame:
    country_key = country.strip().casefold()
    sub = df[df["Country/Region"].astype(str).str.casefold() == country_key]
    if sub.empty:
        countries = sorted(df["Country/Region"].dropna().astype(str).unique())
        raise ValueError(f"Country/Region not found: {country!r}. Available examples: {countries[:20]}")
    return sub
