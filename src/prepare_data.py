import argparse
import re
from pathlib import Path

from preprocessing import build_country_province_daily_panel, build_region_timeseries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare JHU CSSE COVID-19 time-series data.")
    parser.add_argument("--data_dir", default="data/raw", help="Directory containing JHU global time-series CSV files.")
    parser.add_argument("--country", default="China", help="Country/Region name in JHU data, e.g. China or US.")
    parser.add_argument("--province", default="", help="Optional Province/State. Empty means aggregate the country.")
    parser.add_argument(
        "--exclude_provinces",
        default="",
        help="Comma-separated Province/State names to exclude when aggregating a country, e.g. Hong Kong,Macau,Taiwan,Unknown.",
    )
    parser.add_argument(
        "--region_label",
        default="",
        help="Output label used when province is empty, e.g. Mainland.",
    )
    parser.add_argument("--output_dir", default="data/processed", help="Directory for processed CSV outputs.")
    parser.add_argument(
        "--skip_province_panel",
        action="store_true",
        help="Skip province-level panel output for faster country-only preparation.",
    )
    return parser.parse_args()


def safe_slug(*parts: str) -> str:
    text = "_".join(part.strip() for part in parts if part and part.strip())
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("_").lower() or "region"


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    province = args.province.strip() or None
    exclude_provinces = [item.strip() for item in args.exclude_provinces.split(",") if item.strip()]
    region_label = args.region_label.strip() or None
    slug = safe_slug(args.country, province or region_label or "all")

    region_df, quality_df = build_region_timeseries(
        data_dir,
        args.country,
        province,
        exclude_provinces=exclude_provinces if province is None else None,
        region_label=region_label,
    )
    region_path = output_dir / f"{slug}_timeseries.csv"
    quality_path = output_dir / f"{slug}_data_quality.csv"
    region_df.to_csv(region_path, index=False, encoding="utf-8-sig")
    quality_df.to_csv(quality_path, index=False, encoding="utf-8-sig")

    print(f"Saved region time series: {region_path}")
    print(f"Saved data quality summary: {quality_path}")

    if province is None and not args.skip_province_panel:
        panel_df = build_country_province_daily_panel(data_dir, args.country, exclude_provinces=exclude_provinces)
        panel_path = output_dir / f"{safe_slug(args.country, region_label or 'all')}_province_timeseries.csv"
        panel_df.to_csv(panel_path, index=False, encoding="utf-8-sig")
        print(f"Saved province panel: {panel_path}")


if __name__ == "__main__":
    main()
