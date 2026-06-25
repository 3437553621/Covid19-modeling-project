import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot national and province-level COVID-19 trend charts.")
    parser.add_argument("--processed_csv", default="data/processed/china_all_timeseries.csv", help="Prepared country time-series CSV.")
    parser.add_argument(
        "--province_panel_csv",
        default="data/processed/china_province_timeseries.csv",
        help="Prepared province-level panel CSV.",
    )
    parser.add_argument("--country", default="China", help="Country label for output filenames.")
    parser.add_argument("--top_n", type=int, default=10, help="Number of provinces highlighted in comparison charts.")
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    return parser.parse_args()


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "region"


def _last_valid(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.iloc[-1]) if not clean.empty else 0.0


def province_summary(panel: pd.DataFrame) -> pd.DataFrame:
    grouped = panel.sort_values("date").groupby("province", dropna=False)
    summary = grouped.agg(
        final_cumulative_confirmed=("cumulative_confirmed", _last_valid),
        total_daily_confirmed=("daily_confirmed", "sum"),
        peak_daily_confirmed=("daily_confirmed", "max"),
        first_date=("date", "min"),
        last_date=("date", "max"),
    ).reset_index()
    summary["province"] = summary["province"].fillna("").replace("", "UNKNOWN")
    return summary.sort_values("final_cumulative_confirmed", ascending=False).reset_index(drop=True)


def plot_country_trends(df: pd.DataFrame, country: str, figure_dir: Path, region_slug: str) -> None:
    df = df.sort_values("date")
    cumulative_cols = [
        ("cumulative_confirmed", "Confirmed"),
        ("cumulative_deaths", "Deaths"),
        ("cumulative_recovered", "Recovered"),
    ]
    daily_cols = [
        ("daily_confirmed", "Daily confirmed"),
        ("daily_deaths", "Daily deaths"),
        ("daily_recovered", "Daily recovered"),
    ]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    for col, label in cumulative_cols:
        if col in df:
            ax.plot(df["date"], df[col], label=label, linewidth=2)
    ax.set_title(f"{country} Cumulative COVID-19 Trends")
    ax.set_xlabel("Date")
    ax.set_ylabel("People")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_dir / f"{region_slug}_cumulative_trends.png", dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    for col, label in daily_cols:
        if col in df:
            smoothed = df[col].rolling(window=7, min_periods=1).mean()
            ax.plot(df["date"], smoothed, label=f"{label} (7-day mean)", linewidth=2)
    ax.set_title(f"{country} Daily New COVID-19 Trends")
    ax.set_xlabel("Date")
    ax.set_ylabel("People")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_dir / f"{region_slug}_daily_trends.png", dpi=300)
    plt.close(fig)


def plot_province_lines(panel: pd.DataFrame, summary: pd.DataFrame, country: str, figure_dir: Path, country_slug: str, top_n: int) -> None:
    named_summary = summary[summary["province"].astype(str).str.upper() != "UNKNOWN"]
    top_provinces = named_summary.head(top_n)["province"].tolist()
    palette = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(12, 6))
    for province, group in panel.groupby("province"):
        group = group.sort_values("date")
        province_label = province or "UNKNOWN"
        if province_label in top_provinces:
            color = palette(top_provinces.index(province_label) % 10)
            ax.plot(group["date"], group["cumulative_confirmed"], label=province_label, linewidth=2.0, color=color)
        else:
            ax.plot(group["date"], group["cumulative_confirmed"], color="#c9c9c9", linewidth=0.7, alpha=0.45)
    ax.set_title(f"{country} Province Cumulative Confirmed Trends")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative confirmed")
    ax.grid(alpha=0.25)
    ax.legend(title=f"Top {top_n}", ncol=2, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_dir / f"{country_slug}_province_cumulative_confirmed_trends.png", dpi=300)
    plt.close(fig)

    smoothed = panel.sort_values(["province", "date"]).copy()
    smoothed["daily_confirmed_7d_mean"] = smoothed.groupby("province")["daily_confirmed"].transform(
        lambda s: s.rolling(window=7, min_periods=1).mean()
    )

    fig, ax = plt.subplots(figsize=(12, 6))
    for province, group in smoothed.groupby("province"):
        group = group.sort_values("date")
        province_label = province or "UNKNOWN"
        if province_label in top_provinces:
            color = palette(top_provinces.index(province_label) % 10)
            ax.plot(group["date"], group["daily_confirmed_7d_mean"], label=province_label, linewidth=2.0, color=color)
        else:
            ax.plot(group["date"], group["daily_confirmed_7d_mean"], color="#c9c9c9", linewidth=0.7, alpha=0.45)
    ax.set_title(f"{country} Province Daily New Confirmed Trends")
    ax.set_xlabel("Date")
    ax.set_ylabel("Daily confirmed, 7-day mean")
    ax.grid(alpha=0.25)
    ax.legend(title=f"Top {top_n}", ncol=2, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_dir / f"{country_slug}_province_daily_confirmed_trends.png", dpi=300)
    plt.close(fig)


def plot_top_province_bars(summary: pd.DataFrame, country: str, figure_dir: Path, country_slug: str, top_n: int) -> None:
    named_summary = summary[summary["province"].astype(str).str.upper() != "UNKNOWN"]
    top = named_summary.head(top_n).sort_values("final_cumulative_confirmed", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top["province"], top["final_cumulative_confirmed"], color="#4c78a8")
    ax.set_title(f"{country} Top {top_n} Provinces by Cumulative Confirmed Cases")
    ax.set_xlabel("Cumulative confirmed")
    ax.set_ylabel("Province")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(figure_dir / f"{country_slug}_province_top{top_n}_confirmed_comparison.png", dpi=300)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    figure_dir = output_root / "figures"
    metrics_dir = output_root / "metrics"
    figure_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    country_slug = slug(args.country)
    region_slug = country_slug

    processed_path = Path(args.processed_csv)
    if processed_path.exists():
        df = pd.read_csv(processed_path)
        df["date"] = pd.to_datetime(df["date"])
        plot_country_trends(df, args.country, figure_dir, region_slug)

    panel_path = Path(args.province_panel_csv)
    if not panel_path.exists():
        raise FileNotFoundError(f"Missing province panel CSV: {panel_path}. Run prepare_data.py without --skip_province_panel first.")

    panel = pd.read_csv(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    panel["province"] = panel["province"].fillna("").replace("", "UNKNOWN")
    panel["daily_confirmed"] = panel["daily_confirmed"].clip(lower=0)

    summary = province_summary(panel)
    summary_path = metrics_dir / f"{country_slug}_province_trend_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    plot_province_lines(panel, summary, args.country, figure_dir, country_slug, args.top_n)
    plot_top_province_bars(summary, args.country, figure_dir, country_slug, args.top_n)

    print(f"Saved province trend summary: {summary_path}")
    print(f"Saved regional trend figures to: {figure_dir}")


if __name__ == "__main__":
    main()
