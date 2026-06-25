from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_loader import aggregate_region, load_jhu_timeseries, province_panel


@dataclass
class DailySeriesResult:
    daily: pd.Series
    negative_corrections: int


@dataclass
class ResetCheckResult:
    cumulative: pd.Series
    reset_date: pd.Timestamp | None
    reliable_end_date: pd.Timestamp
    values_marked_missing: int


def mark_terminal_zero_reset(cumulative: pd.Series) -> ResetCheckResult:
    """Mark terminal zeroes as missing when a cumulative series resets after reporting."""
    clean = cumulative.astype(float).copy()
    reset_date = None
    values_marked_missing = 0

    if clean.max(skipna=True) > 0 and clean.iloc[-1] == 0:
        positive_dates = clean[clean > 0].index
        reliable_end_date = positive_dates.max()
        missing_mask = clean.index > reliable_end_date
        values_marked_missing = int(missing_mask.sum())
        if values_marked_missing:
            reset_date = clean.index[missing_mask][0]
            clean.loc[missing_mask] = pd.NA
    else:
        reliable_end_date = clean.dropna().index.max()

    return ResetCheckResult(
        cumulative=clean,
        reset_date=reset_date,
        reliable_end_date=reliable_end_date,
        values_marked_missing=values_marked_missing,
    )


def cumulative_to_daily(cumulative: pd.Series) -> DailySeriesResult:
    """Convert cumulative counts to daily new counts and clip negative corrections to zero."""
    daily_raw = cumulative.diff()
    if not cumulative.empty and pd.notna(cumulative.iloc[0]):
        daily_raw.iloc[0] = cumulative.iloc[0]
    negative_corrections = int((daily_raw < 0).sum())
    daily = daily_raw.clip(lower=0)
    daily.name = "daily"
    return DailySeriesResult(daily=daily, negative_corrections=negative_corrections)


def build_region_timeseries(
    data_dir: str | Path,
    country: str,
    province: str | None = None,
    exclude_provinces: list[str] | None = None,
    region_label: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one country/province modeling table and a compact data-quality table."""
    frames: dict[str, pd.Series] = {}
    quality_rows: list[dict[str, object]] = []
    region_label = region_label or province or "ALL"

    for kind in ["confirmed", "deaths", "recovered"]:
        df = load_jhu_timeseries(data_dir, kind)
        cumulative = aggregate_region(df, country=country, province=province, exclude_provinces=exclude_provinces)
        if kind == "recovered":
            reset_result = mark_terminal_zero_reset(cumulative)
            cumulative = reset_result.cumulative
        else:
            reset_result = ResetCheckResult(
                cumulative=cumulative.astype(float),
                reset_date=None,
                reliable_end_date=cumulative.index.max(),
                values_marked_missing=0,
            )
        daily_result = cumulative_to_daily(cumulative)

        frames[f"cumulative_{kind}"] = cumulative
        frames[f"daily_{kind}"] = daily_result.daily

        quality_rows.append(
            {
                "target": kind,
                "country": country,
                "province": region_label,
                "start_date": cumulative.index.min().date().isoformat(),
                "end_date": cumulative.index.max().date().isoformat(),
                "reliable_end_date": reset_result.reliable_end_date.date().isoformat(),
                "days": len(cumulative),
                "cumulative_start": float(cumulative.iloc[0]),
                "cumulative_end": float(cumulative.dropna().iloc[-1]) if cumulative.notna().any() else pd.NA,
                "daily_max": float(daily_result.daily.max()),
                "negative_daily_values_clipped": daily_result.negative_corrections,
                "zero_daily_days": int((daily_result.daily == 0).sum()),
                "missing_days": int(cumulative.isna().sum()),
                "terminal_zero_reset_date": reset_result.reset_date.date().isoformat()
                if reset_result.reset_date is not None
                else "NONE",
                "terminal_zero_values_marked_missing": reset_result.values_marked_missing,
                "possible_reset_or_stop": bool(reset_result.values_marked_missing > 0),
            }
        )

    result = pd.DataFrame(frames).reset_index(names="date")
    result.insert(1, "country", country)
    result.insert(2, "province", region_label)
    quality = pd.DataFrame(quality_rows)
    return result, quality


def build_country_province_daily_panel(
    data_dir: str | Path,
    country: str,
    exclude_provinces: list[str] | None = None,
) -> pd.DataFrame:
    """Build a province-level panel with cumulative and daily values for regional trend analysis."""
    panels: list[pd.DataFrame] = []
    for kind in ["confirmed", "deaths", "recovered"]:
        raw = load_jhu_timeseries(data_dir, kind)
        panel = province_panel(raw, country, exclude_provinces=exclude_provinces)
        panel = panel.rename(columns={"cumulative": f"cumulative_{kind}"})

        if kind == "recovered":
            panel[f"cumulative_{kind}"] = panel.groupby("province", group_keys=False)[f"cumulative_{kind}"].apply(
                lambda s: mark_terminal_zero_reset(s).cumulative
            )

        # 按省份分别差分，避免相邻省份之间串线。
        panel[f"daily_{kind}"] = (
            panel.groupby("province", group_keys=False)[f"cumulative_{kind}"]
            .apply(lambda s: cumulative_to_daily(s).daily)
            .astype(float)
        )
        panels.append(panel)

    merged = panels[0]
    for panel in panels[1:]:
        merged = merged.merge(panel, on=["date", "country", "province"], how="outer")

    metric_cols = [col for col in merged.columns if col.startswith(("cumulative_", "daily_"))]
    non_recovered_cols = [col for col in metric_cols if not col.endswith("_recovered")]
    merged[non_recovered_cols] = merged[non_recovered_cols].fillna(0)
    return merged.sort_values(["province", "date"]).reset_index(drop=True)
