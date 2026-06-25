import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from models.sir import add_sir_predictions, fit_sir_model, prepare_sir_observations, regression_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit an SIR model on prepared COVID-19 time series.")
    parser.add_argument("--processed_csv", default="data/processed/china_all_timeseries.csv", help="Prepared region time-series CSV.")
    parser.add_argument("--country", default="China", help="Country label for output filenames.")
    parser.add_argument("--province", default="ALL", help="Province label for output filenames.")
    parser.add_argument("--start_date", default="", help="Optional fit start date, e.g. 2020-01-22.")
    parser.add_argument("--end_date", default="", help="Optional fit end date. Empty uses data and fit_days limit.")
    parser.add_argument("--fit_days", type=int, default=180, help="Number of days used for fitting. Use 0 for all reliable recovered dates.")
    parser.add_argument("--forecast_days", type=int, default=14, help="Days to simulate after the fit window.")
    parser.add_argument("--population_upper_bound", type=float, default=1_500_000_000, help="Upper bound for fitted effective population.")
    parser.add_argument("--output_dir", default="outputs", help="Output directory root.")
    return parser.parse_args()


def slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_") or "region"


def plot_sir_fit(predictions: pd.DataFrame, figure_path: Path, title: str) -> None:
    fit_part = predictions[predictions["split"] == "fit"]
    forecast_part = predictions[predictions["split"] == "forecast"]

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    axes[0].plot(fit_part["date"], fit_part["infected"], label="Observed active infected", color="#1f77b4", linewidth=2)
    axes[0].plot(predictions["date"], predictions["sir_infected"], label="SIR fitted/simulated infected", color="#ff7f0e", linestyle="--")
    if not forecast_part.empty:
        axes[0].axvspan(forecast_part["date"].min(), forecast_part["date"].max(), color="#f2f2f2", alpha=0.8, label="Forecast window")
    axes[0].set_ylabel("People")
    axes[0].set_title(title)
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(fit_part["date"], fit_part["removed"], label="Observed removed (recovered + deaths)", color="#2ca02c", linewidth=2)
    axes[1].plot(predictions["date"], predictions["sir_removed"], label="SIR fitted/simulated removed", color="#d62728", linestyle="--")
    axes[1].set_ylabel("People")
    axes[1].set_xlabel("Date")
    axes[1].legend()
    axes[1].grid(alpha=0.25)

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
    fit = fit_sir_model(observations, population_upper_bound=args.population_upper_bound)
    predictions = add_sir_predictions(observations, fit, forecast_days=args.forecast_days)

    region_slug = slug(f"{args.country}_{args.province}")
    prediction_path = prediction_dir / f"{region_slug}_sir_fit.csv"
    parameters_path = metrics_dir / f"{region_slug}_sir_parameters.csv"
    metrics_path = metrics_dir / f"{region_slug}_sir_metrics.csv"
    figure_path = figure_dir / f"{region_slug}_sir_fit.png"

    predictions.to_csv(prediction_path, index=False, encoding="utf-8-sig")

    pd.DataFrame(
        [
            {
                "country": args.country,
                "province": args.province,
                "fit_start_date": observations["date"].min().date().isoformat(),
                "fit_end_date": observations["date"].max().date().isoformat(),
                "fit_days": len(observations),
                "forecast_days": args.forecast_days,
                "beta": fit.beta,
                "gamma": fit.gamma,
                "R0_beta_over_gamma": fit.reproduction_number,
                "effective_population": fit.effective_population,
                "initial_susceptible": fit.initial_susceptible,
                "initial_infected": fit.initial_infected,
                "initial_removed": fit.initial_removed,
                "success": fit.success,
                "cost": fit.cost,
                "message": fit.message,
            }
        ]
    ).to_csv(parameters_path, index=False, encoding="utf-8-sig")

    fit_rows = []
    fit_predictions = predictions[predictions["split"] == "fit"]
    for target, pred_col in [
        ("active_infected", "sir_infected"),
        ("removed", "sir_removed"),
        ("confirmed", "sir_confirmed"),
    ]:
        true_col = {"active_infected": "infected", "removed": "removed", "confirmed": "confirmed"}[target]
        row = {"model": "SIR", "target": target}
        row.update(regression_metrics(fit_predictions[true_col], fit_predictions[pred_col]))
        fit_rows.append(row)
    pd.DataFrame(fit_rows).to_csv(metrics_path, index=False, encoding="utf-8-sig")

    plot_sir_fit(
        predictions,
        figure_path,
        title=f"SIR Model Fit - {args.country} {args.province} ({observations['date'].min().date()} to {observations['date'].max().date()})",
    )

    print(f"Saved SIR predictions: {prediction_path}")
    print(f"Saved SIR parameters: {parameters_path}")
    print(f"Saved SIR metrics: {metrics_path}")
    print(f"Saved SIR figure: {figure_path}")
    print(
        "Fitted beta={:.4f}, gamma={:.4f}, R0={:.4f}, effective_population={:.0f}".format(
            fit.beta, fit.gamma, fit.reproduction_number, fit.effective_population
        )
    )


if __name__ == "__main__":
    main()
