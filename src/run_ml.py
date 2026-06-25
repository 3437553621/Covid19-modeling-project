import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from models.ml_baselines import FEATURE_COLUMNS, build_lag_features, make_models, recursive_forecast, train_and_predict


TARGETS = {
    "confirmed": "daily_confirmed",
    "deaths": "daily_deaths",
    "recovered": "daily_recovered",
}

COMPARISON_MODELS = ["NaivePersistence", "LinearRegression", "RandomForest", "GradientBoosting"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ML baselines for COVID-19 daily new case forecasting.")
    parser.add_argument("--processed_csv", default="data/processed/china_all_timeseries.csv", help="Prepared region time-series CSV.")
    parser.add_argument("--country", default="China", help="Country label for output filenames.")
    parser.add_argument("--province", default="ALL", help="Province label for output filenames.")
    parser.add_argument("--target", default="all", choices=["all", *TARGETS.keys()], help="Target variable to train.")
    parser.add_argument("--test_ratio", type=float, default=0.2, help="Chronological test ratio.")
    parser.add_argument("--forecast_days", type=int, default=14, help="Future forecast horizon.")
    parser.add_argument(
        "--recovered_end_date",
        default="2021-08-04",
        help="Last reliable recovered date in JHU global time series; recovered is modeled only up to this date.",
    )
    parser.add_argument("--random_state", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--model",
        default="GradientBoosting",
        choices=sorted(make_models().keys()),
        help="ML model to keep in the main experiment.",
    )
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    parser.add_argument("--all_models", action="store_true", help="Run all ML candidates for exploratory comparison.")
    parser.add_argument("--single_model", action="store_true", help="Only run the model specified by --model.")
    return parser.parse_args()


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "region"


def plot_test_predictions(predictions: pd.DataFrame, output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    actual = predictions.drop_duplicates("date").sort_values("date")
    ax.plot(actual["date"], actual["actual"], label="Actual", color="#1f77b4", linewidth=2)
    for model_name, group in predictions.groupby("model", sort=False):
        group = group.sort_values("date")
        ax.plot(group["date"], group["prediction"], label=model_name, linestyle="--")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Daily new cases")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_future_forecast(future: pd.DataFrame, output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    for model_name, group in future.groupby("model", sort=False):
        group = group.sort_values("date")
        ax.plot(group["date"], group["prediction"], marker="o", label=model_name)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Predicted daily new cases")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_metrics(metrics: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, metric in zip(axes, ["RMSE", "MAE", "R2"]):
        plot_data = metrics.copy()
        if metric == "R2":
            plot_data[metric] = plot_data[metric].clip(lower=-5)
        pivot = plot_data.pivot(index="target", columns="model", values=metric)
        pivot.plot(kind="bar", ax=ax)
        ax.set_title(metric)
        ax.set_xlabel("Target")
        ax.grid(axis="y", alpha=0.25)
        if metric == "R2":
            ax.axhline(0, color="black", linewidth=0.8)
            ax.set_ylabel("R2 (values < -5 clipped)")
            ax.text(
                0.01,
                0.02,
                "Displayed R2 lower bound is -5; full values are kept in CSV/tables.",
                transform=ax.transAxes,
                fontsize=8,
                ha="left",
                va="bottom",
            )
    fig.suptitle("ML Model Metrics on Chronological Test Set")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def write_combined_metrics(metrics_df: pd.DataFrame, metrics_dir: Path, region_slug: str) -> Path:
    combined_rows = []
    ml_part = metrics_df.copy()
    ml_part.insert(0, "model_family", "Machine Learning")
    combined_rows.append(ml_part)

    for model_name in ["sir", "time_varying_sir"]:
        compartment_path = metrics_dir / f"{region_slug}_{model_name}_metrics.csv"
        if compartment_path.exists():
            compartment_part = pd.read_csv(compartment_path)
            compartment_part.insert(0, "model_family", "Compartment")
            compartment_part["target_column"] = ""
            compartment_part["train_rows"] = ""
            compartment_part["test_rows"] = ""
            for col in ["train_start_date", "train_end_date", "test_start_date", "test_end_date", "evaluation_scope"]:
                if col not in compartment_part.columns:
                    compartment_part[col] = ""
            compartment_part = compartment_part[
                [
                    "model_family",
                    "target",
                    "target_column",
                    "train_rows",
                    "test_rows",
                    "train_start_date",
                    "train_end_date",
                    "test_start_date",
                    "test_end_date",
                    "evaluation_scope",
                    "model",
                    "RMSE",
                    "MAE",
                    "R2",
                ]
            ]
            combined_rows.append(compartment_part)

    output = pd.concat(combined_rows, ignore_index=True, sort=False)
    output_path = metrics_dir / "metrics.csv"
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    figure_dir = output_root / "figures"
    metrics_dir = output_root / "metrics"
    prediction_dir = output_root / "predictions"
    for path in [figure_dir, metrics_dir, prediction_dir]:
        path.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.processed_csv)
    df["date"] = pd.to_datetime(df["date"])
    recovered_end_date = pd.to_datetime(args.recovered_end_date)
    region_slug = slug(f"{args.country}_{args.province}")
    selected_targets = TARGETS if args.target == "all" else {args.target: TARGETS[args.target]}

    all_metrics = []
    all_test_predictions = []
    all_future = []
    all_importances = []
    if args.all_models:
        selected_models = None
    elif args.single_model:
        selected_models = [args.model]
    else:
        selected_models = COMPARISON_MODELS

    for target_name, target_col in selected_targets.items():
        target_source = df.copy()
        if target_name == "recovered":
            target_source = target_source[target_source["date"].le(recovered_end_date)].copy()
        feature_df = build_lag_features(target_source, target_col)
        metrics, test_predictions, fitted_models = train_and_predict(
            feature_df,
            test_ratio=args.test_ratio,
            random_state=args.random_state,
            model_names=selected_models,
        )
        metrics.insert(0, "target", target_name)
        metrics.insert(1, "target_column", target_col)
        metrics.insert(2, "train_rows", int(len(feature_df) - len(test_predictions.drop_duplicates("date"))))
        metrics.insert(3, "test_rows", int(len(test_predictions.drop_duplicates("date"))))
        metrics["random_state"] = args.random_state
        metrics["gb_n_estimators"] = 500
        metrics["gb_learning_rate"] = 0.03
        metrics["gb_max_depth"] = 2
        all_metrics.append(metrics)

        test_predictions.insert(0, "target", target_name)
        test_predictions.insert(1, "target_column", target_col)
        all_test_predictions.append(test_predictions)

        for model_name, model in fitted_models.items():
            if hasattr(model, "feature_importances_"):
                for feature, importance in zip(FEATURE_COLUMNS, model.feature_importances_):
                    all_importances.append(
                        {
                            "target": target_name,
                            "model": model_name,
                            "feature": feature,
                            "importance": float(importance),
                        }
                    )
            future = recursive_forecast(
                model,
                target_source[["date", target_col]],
                target_col,
                forecast_days=args.forecast_days,
            )
            future.insert(0, "target", target_name)
            future.insert(1, "target_column", target_col)
            future.insert(2, "model", model_name)
            all_future.append(future)

        plot_test_predictions(
            test_predictions,
            figure_dir / f"{region_slug}_{target_name}_ml_test_prediction.png",
            title=f"{args.country} {args.province} {target_name}: Test Prediction",
        )
        plot_future_forecast(
            pd.concat([f for f in all_future if f["target"].iloc[0] == target_name], ignore_index=True),
            figure_dir / f"{region_slug}_{target_name}_ml_future_{args.forecast_days}d.png",
            title=f"{args.country} {args.province} {target_name}: Future {args.forecast_days}-Day Forecast",
        )

    metrics_df = pd.concat(all_metrics, ignore_index=True)
    test_df = pd.concat(all_test_predictions, ignore_index=True)
    future_df = pd.concat(all_future, ignore_index=True)

    metrics_path = metrics_dir / f"{region_slug}_ml_metrics.csv"
    importance_path = metrics_dir / f"{region_slug}_ml_feature_importance.csv"
    test_path = prediction_dir / f"{region_slug}_ml_test_predictions.csv"
    future_path = prediction_dir / f"{region_slug}_ml_future_{args.forecast_days}d.csv"
    main_future_path = prediction_dir / f"{region_slug}_ml_future_{args.forecast_days}d_confirmed_deaths.csv"
    recovered_future_path = prediction_dir / f"{region_slug}_ml_future_{args.forecast_days}d_recovered_reliable_window.csv"
    metrics_fig_path = figure_dir / f"{region_slug}_ml_metrics_comparison.png"

    metrics_df.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    if all_importances:
        pd.DataFrame(all_importances).sort_values(["target", "model", "importance"], ascending=[True, True, False]).to_csv(
            importance_path, index=False, encoding="utf-8-sig"
        )
    test_df.to_csv(test_path, index=False, encoding="utf-8-sig")
    future_df.to_csv(future_path, index=False, encoding="utf-8-sig")
    main_future = future_df[future_df["target"].isin(["confirmed", "deaths"])].copy()
    recovered_future = future_df[future_df["target"].eq("recovered")].copy()
    if not main_future.empty:
        main_future.to_csv(main_future_path, index=False, encoding="utf-8-sig")
    if not recovered_future.empty:
        recovered_future.to_csv(recovered_future_path, index=False, encoding="utf-8-sig")
    plot_metrics(metrics_df, metrics_fig_path)
    combined_metrics_path = write_combined_metrics(metrics_df, metrics_dir, region_slug)

    print(f"Saved ML metrics: {metrics_path}")
    if all_importances:
        print(f"Saved ML feature importance: {importance_path}")
    print(f"Saved combined metrics: {combined_metrics_path}")
    print(f"Saved ML test predictions: {test_path}")
    print(f"Saved ML future forecasts: {future_path}")
    if not main_future.empty:
        print(f"Saved confirmed/deaths future forecasts: {main_future_path}")
    if not recovered_future.empty:
        print(f"Saved recovered reliable-window future forecasts: {recovered_future_path}")
    print(f"Saved ML metrics figure: {metrics_fig_path}")
    print(metrics_df[["target", "model", "RMSE", "MAE", "R2"]].to_string(index=False))


if __name__ == "__main__":
    main()
