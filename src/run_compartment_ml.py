import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from models.ml_baselines import build_lag_features, train_and_predict
from models.sir import prepare_sir_observations


TARGETS = {
    "infected": "infected",
    "removed": "removed",
    "confirmed": "confirmed",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GradientBoosting on SIR-window compartment targets.")
    parser.add_argument("--processed_csv", default="data/processed/china_all_timeseries.csv", help="Prepared region time-series CSV.")
    parser.add_argument("--country", default="China", help="Country label for output filenames.")
    parser.add_argument("--province", default="ALL", help="Province label for output filenames.")
    parser.add_argument("--fit_days", type=int, default=180, help="Same observation window length used by SIR. Use 0 for all reliable dates.")
    parser.add_argument("--test_ratio", type=float, default=0.2, help="Chronological test ratio within the SIR window.")
    parser.add_argument("--random_state", type=int, default=42, help="Random seed.")
    parser.add_argument("--model", default="GradientBoosting", help="ML model name from ml_baselines.make_models().")
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    return parser.parse_args()


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "region"


def plot_compartment_predictions(predictions: pd.DataFrame, figure_path: Path, title: str) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=False)
    for ax, target in zip(axes, TARGETS):
        part = predictions[predictions["target"] == target].sort_values("date")
        ax.plot(part["date"], part["actual"], label="Actual", color="#1f77b4", linewidth=2)
        ax.plot(part["date"], part["prediction"], label="GradientBoosting", color="#ff7f0e", linestyle="--", linewidth=2)
        ax.set_title(target)
        ax.set_ylabel("People")
        ax.grid(alpha=0.25)
        ax.legend()
    axes[-1].set_xlabel("Date")
    fig.suptitle(title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_path, dpi=300)
    plt.close(fig)


def update_combined_metrics(metrics_df: pd.DataFrame, metrics_dir: Path) -> Path:
    combined_path = metrics_dir / "metrics.csv"
    addition = metrics_df.copy()
    addition.insert(0, "model_family", "Machine Learning (SIR window)")

    if combined_path.exists():
        combined = pd.read_csv(combined_path)
        if "model_family" in combined.columns:
            combined = combined[combined["model_family"] != "Machine Learning (SIR window)"]
        combined = pd.concat([combined, addition], ignore_index=True, sort=False)
    else:
        combined = addition

    combined.to_csv(combined_path, index=False, encoding="utf-8-sig")
    return combined_path


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    figure_dir = output_root / "figures"
    metrics_dir = output_root / "metrics"
    prediction_dir = output_root / "predictions"
    for path in [figure_dir, metrics_dir, prediction_dir]:
        path.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.processed_csv)
    fit_days = None if args.fit_days == 0 else args.fit_days
    observations = prepare_sir_observations(df, fit_days=fit_days)

    all_metrics = []
    all_predictions = []
    for target, target_col in TARGETS.items():
        feature_df = build_lag_features(observations[["date", target_col]], target_col)
        metrics, test_predictions, _models = train_and_predict(
            feature_df,
            test_ratio=args.test_ratio,
            random_state=args.random_state,
            model_names=[args.model],
        )
        train_rows = int(len(feature_df) - len(test_predictions.drop_duplicates("date")))
        test_rows = int(len(test_predictions.drop_duplicates("date")))
        metrics.insert(0, "target", target)
        metrics.insert(1, "target_column", target_col)
        metrics.insert(2, "train_rows", train_rows)
        metrics.insert(3, "test_rows", test_rows)
        metrics["evaluation_scope"] = "chronological_test_within_sir_window"
        metrics["fit_window_start"] = observations["date"].min().date().isoformat()
        metrics["fit_window_end"] = observations["date"].max().date().isoformat()
        all_metrics.append(metrics)

        test_predictions.insert(0, "target", target)
        test_predictions.insert(1, "target_column", target_col)
        all_predictions.append(test_predictions)

    metrics_df = pd.concat(all_metrics, ignore_index=True)
    prediction_df = pd.concat(all_predictions, ignore_index=True)
    region_slug = slug(f"{args.country}_{args.province}")

    metrics_path = metrics_dir / f"{region_slug}_compartment_ml_metrics.csv"
    predictions_path = prediction_dir / f"{region_slug}_compartment_ml_test_predictions.csv"
    figure_path = figure_dir / f"{region_slug}_compartment_ml_test_prediction.png"

    metrics_df.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    prediction_df.to_csv(predictions_path, index=False, encoding="utf-8-sig")
    plot_compartment_predictions(
        prediction_df,
        figure_path,
        title=f"{args.country} {args.province}: GradientBoosting on SIR-window Compartments",
    )
    combined_path = update_combined_metrics(metrics_df, metrics_dir)

    print(f"Saved compartment ML metrics: {metrics_path}")
    print(f"Saved compartment ML predictions: {predictions_path}")
    print(f"Saved compartment ML figure: {figure_path}")
    print(f"Updated combined metrics: {combined_path}")
    print(metrics_df[["target", "model", "RMSE", "MAE", "R2"]].to_string(index=False))


if __name__ == "__main__":
    main()
