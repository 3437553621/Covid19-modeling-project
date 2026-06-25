import argparse
import re
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the COVID-19 modeling workflow end to end.")
    parser.add_argument("--data_dir", default="data/raw", help="Directory containing JHU global time-series CSV files.")
    parser.add_argument("--country", default="China", help="Country/Region name in JHU data.")
    parser.add_argument("--province", default="", help="Optional Province/State. Empty means aggregate the country.")
    parser.add_argument("--processed_dir", default="data/processed", help="Directory for processed CSV outputs.")
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    parser.add_argument("--fit_days", type=int, default=180, help="Days used for SIR fitting. Use 0 for all reliable recovered dates.")
    parser.add_argument("--forecast_days", type=int, default=14, help="Main future forecast horizon.")
    parser.add_argument("--test_ratio", type=float, default=0.2, help="Chronological test ratio for ML model.")
    parser.add_argument("--ml_model", default="GradientBoosting", help="Single ML model kept in the main experiment.")
    parser.add_argument(
        "--region_scope",
        default="mainland",
        choices=["mainland", "all"],
        help="For China with empty province, 'mainland' excludes Hong Kong, Macau, Taiwan and Unknown.",
    )
    parser.add_argument("--skip_province_panel", action="store_true", help="Skip province-level panel output.")
    return parser.parse_args()


def safe_slug(*parts: str) -> str:
    text = "_".join(part.strip() for part in parts if part and part.strip())
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("_").lower() or "region"


def run_step(args: list[str]) -> None:
    print("\n$ " + " ".join(args), flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    args = parse_args()
    mainland_scope = args.country.strip().casefold() == "china" and not args.province.strip() and args.region_scope == "mainland"
    province_label = args.province.strip() or ("Mainland" if mainland_scope else "ALL")
    region_slug_part = args.province or ("mainland" if mainland_scope else "all")
    processed_csv = Path(args.processed_dir) / f"{safe_slug(args.country, region_slug_part)}_timeseries.csv"

    prepare_cmd = [
        sys.executable,
        "src/prepare_data.py",
        "--data_dir",
        args.data_dir,
        "--country",
        args.country,
        "--province",
        args.province,
        "--output_dir",
        args.processed_dir,
    ]
    if mainland_scope:
        prepare_cmd.extend(
            [
                "--exclude_provinces",
                "Hong Kong,Macau,Taiwan,Unknown",
                "--region_label",
                "Mainland",
            ]
        )
    if args.skip_province_panel:
        prepare_cmd.append("--skip_province_panel")
    run_step(prepare_cmd)

    if not args.province.strip() and not args.skip_province_panel:
        run_step(
            [
                sys.executable,
                "src/run_regional_trends.py",
                "--processed_csv",
                str(processed_csv),
                "--province_panel_csv",
                str(Path(args.processed_dir) / f"{safe_slug(args.country, region_slug_part)}_province_timeseries.csv"),
                "--country",
                f"{args.country} {province_label}",
                "--output_dir",
                args.output_dir,
            ]
        )

    common_model_args = [
        "--processed_csv",
        str(processed_csv),
        "--country",
        args.country,
        "--province",
        province_label,
        "--forecast_days",
        str(args.forecast_days),
        "--output_dir",
        args.output_dir,
    ]

    run_step([sys.executable, "src/run_sir.py", *common_model_args, "--fit_days", str(args.fit_days)])
    run_step([sys.executable, "src/run_time_varying_sir.py", *common_model_args, "--fit_days", str(args.fit_days)])

    horizons = sorted({7, args.forecast_days})
    for horizon in horizons:
        run_step(
            [
                sys.executable,
                "src/run_ml.py",
                "--processed_csv",
                str(processed_csv),
                "--country",
                args.country,
                "--province",
                province_label,
                "--target",
                "all",
                "--test_ratio",
                str(args.test_ratio),
                "--forecast_days",
                str(horizon),
                "--model",
                args.ml_model,
                "--output_dir",
                args.output_dir,
            ]
        )

    run_step(
        [
            sys.executable,
            "src/run_compartment_ml.py",
            "--processed_csv",
            str(processed_csv),
            "--country",
            args.country,
            "--province",
            province_label,
            "--fit_days",
            str(args.fit_days),
            "--test_ratio",
            str(args.test_ratio),
            "--model",
            args.ml_model,
            "--output_dir",
            args.output_dir,
        ]
    )

    run_step(
        [
            sys.executable,
            "src/generate_report.py",
            "--processed_csv",
            str(processed_csv),
            "--quality_csv",
            str(Path(args.processed_dir) / f"{safe_slug(args.country, region_slug_part)}_data_quality.csv"),
            "--country",
            args.country,
            "--province",
            province_label,
            "--output_dir",
            args.output_dir,
            "--report_path",
            "reports/report.md",
        ]
    )

    print("\nWorkflow completed.")
    print(f"Processed data: {processed_csv}")
    print(f"Figures: {Path(args.output_dir) / 'figures'}")
    print(f"Metrics: {Path(args.output_dir) / 'metrics'}")
    print(f"Predictions: {Path(args.output_dir) / 'predictions'}")
    print("Report: reports/report.md")


if __name__ == "__main__":
    main()
