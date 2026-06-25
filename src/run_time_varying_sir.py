import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from models.sir import prepare_sir_observations
from models.time_varying_sir import (
    add_time_varying_sir_predictions,
    fit_time_varying_sir,
    time_varying_sir_metric_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit a time-varying-parameter SIR model.")
    parser.add_argument("--processed_csv", default="data/processed/china_all_timeseries.csv", help="Prepared region time-series CSV.")
    parser.add_argument("--country", default="China", help="Country label for output filenames.")
    parser.add_argument("--province", default="ALL", help="Province label for output filenames.")
    parser.add_argument("--start_date", default="", help="Optional fit start date, e.g. 2020-01-22.")
    parser.add_argument("--end_date", default="", help="Optional fit end date. Empty uses data and fit_days limit.")
    parser.add_argument("--fit_days", type=int, default=180, help="Number of days used for fitting. Use 0 for all reliable recovered dates.")
    parser.add_argument("--forecast_days", type=int, default=14, help="Days to simulate after the fit window.")
    parser.add_argument("--smoothing_window", type=int, default=1, help="Rolling smoothing window for beta(t) and gamma(t).")
    parser.add_argument("--population_upper_bound", type=float, default=1_500_000_000, help="Upper bound for fitted effective population.")
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    return parser.parse_args()


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "region"


def plot_time_varying_sir(predictions: pd.DataFrame, parameter_df: pd.DataFrame, figure_path: Path, title: str) -> None:
    fit_part = predictions[predictions["split"] == "fit"]
    forecast_part = predictions[predictions["split"] == "forecast"]

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=False)
    axes[0].plot(fit_part["date"], fit_part["infected"], label="Observed active infected", color="#1f77b4", linewidth=2)
    axes[0].plot(predictions["date"], predictions["tvsir_infected"], label="Time-varying SIR infected", color="#ff7f0e", linestyle="--")
    if not forecast_part.empty:
        axes[0].axvspan(forecast_part["date"].min(), forecast_part["date"].max(), color="#f2f2f2", alpha=0.8, label="Forecast window")
    axes[0].set_title(title)
    axes[0].set_ylabel("People")
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(fit_part["date"], fit_part["removed"], label="Observed removed", color="#2ca02c", linewidth=2)
    axes[1].plot(predictions["date"], predictions["tvsir_removed"], label="Time-varying SIR removed", color="#d62728", linestyle="--")
    axes[1].plot(fit_part["date"], fit_part["confirmed"], label="Observed confirmed", color="#1f77b4", linewidth=1.5, alpha=0.7)
    axes[1].plot(predictions["date"], predictions["tvsir_confirmed"], label="Time-varying SIR confirmed", color="#9467bd", linestyle=":")
    axes[1].set_ylabel("People")
    axes[1].legend()
    axes[1].grid(alpha=0.25)

    axes[2].plot(parameter_df["date"], parameter_df["beta"], label="beta(t): infection rate", color="#ff7f0e")
    axes[2].plot(parameter_df["date"], parameter_df["gamma"], label="gamma(t): removal rate", color="#2ca02c")
    axes[2].set_ylabel("Rate")
    axes[2].set_xlabel("Date")
    axes[2].legend()
    axes[2].grid(alpha=0.25)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_path, dpi=300)
    plt.close(fig)


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
    observations = prepare_sir_observations(
        df,
        start_date=args.start_date or None,
        end_date=args.end_date or None,
        fit_days=fit_days,
    )
    fit, parameter_df = fit_time_varying_sir(
        observations,
        population_upper_bound=args.population_upper_bound,
        smoothing_window=args.smoothing_window,
    )
    predictions = add_time_varying_sir_predictions(observations, fit, parameter_df, forecast_days=args.forecast_days)

    region_slug = slug(f"{args.country}_{args.province}")
    prediction_path = prediction_dir / f"{region_slug}_time_varying_sir_fit.csv"
    daily_parameters_path = metrics_dir / f"{region_slug}_time_varying_sir_daily_parameters.csv"
    parameters_path = metrics_dir / f"{region_slug}_time_varying_sir_parameters.csv"
    metrics_path = metrics_dir / f"{region_slug}_time_varying_sir_metrics.csv"
    figure_path = figure_dir / f"{region_slug}_time_varying_sir_fit.png"

    predictions.to_csv(prediction_path, index=False, encoding="utf-8-sig")
    parameter_df.to_csv(daily_parameters_path, index=False, encoding="utf-8-sig")

    pd.DataFrame(
        [
            {
                "country": args.country,
                "province": args.province,
                "fit_start_date": observations["date"].min().date().isoformat(),
                "fit_end_date": observations["date"].max().date().isoformat(),
                "fit_days": len(observations),
                "forecast_days": args.forecast_days,
                "smoothing_window": fit.smoothing_window,
                "mean_beta": fit.mean_beta,
                "mean_gamma": fit.mean_gamma,
                "mean_R0_beta_over_gamma": fit.mean_reproduction_number,
                "final_beta": fit.final_beta,
                "final_gamma": fit.final_gamma,
                "final_R0_beta_over_gamma": fit.final_reproduction_number,
                "effective_population": fit.effective_population,
                "initial_susceptible": fit.initial_susceptible,
                "initial_infected": fit.initial_infected,
                "initial_removed": fit.initial_removed,
                "base_sir_beta": fit.base_sir.beta,
                "base_sir_gamma": fit.base_sir.gamma,
                "base_sir_R0": fit.base_sir.reproduction_number,
            }
        ]
    ).to_csv(parameters_path, index=False, encoding="utf-8-sig")

    pd.DataFrame(time_varying_sir_metric_rows(predictions)).to_csv(metrics_path, index=False, encoding="utf-8-sig")
    plot_time_varying_sir(
        predictions,
        parameter_df,
        figure_path,
        title=f"Time-varying SIR Fit - {args.country} {args.province} ({observations['date'].min().date()} to {observations['date'].max().date()})",
    )

    print(f"Saved time-varying SIR predictions: {prediction_path}")
    print(f"Saved time-varying SIR daily parameters: {daily_parameters_path}")
    print(f"Saved time-varying SIR parameters: {parameters_path}")
    print(f"Saved time-varying SIR metrics: {metrics_path}")
    print(f"Saved time-varying SIR figure: {figure_path}")
    print(
        "Mean beta={:.4f}, mean gamma={:.4f}, mean R0={:.4f}; final beta={:.4f}, final gamma={:.4f}, final R0={:.4f}".format(
            fit.mean_beta,
            fit.mean_gamma,
            fit.mean_reproduction_number,
            fit.final_beta,
            fit.final_gamma,
            fit.final_reproduction_number,
        )
    )


if __name__ == "__main__":
    main()
