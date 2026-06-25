from dataclasses import dataclass

import numpy as np
import pandas as pd

from models.sir import SIRFitResult, fit_sir_model, regression_metrics


@dataclass
class TimeVaryingSIRFitResult:
    effective_population: float
    initial_susceptible: float
    initial_infected: float
    initial_removed: float
    mean_beta: float
    mean_gamma: float
    mean_reproduction_number: float
    final_beta: float
    final_gamma: float
    final_reproduction_number: float
    smoothing_window: int
    base_sir: SIRFitResult


def estimate_time_varying_parameters(
    observations: pd.DataFrame,
    population: float,
    smoothing_window: int = 7,
) -> pd.DataFrame:
    """Estimate daily beta(t) and gamma(t) from observed SIR compartments.

    This follows the PPT's difference approximation:
    gamma(t) = delta_removed / infected,
    beta(t) = new_infections / infected.
    The susceptible term is treated as approximately constant or absorbed into
    the empirical infection rate, which is more stable for reporting data.
    """
    if smoothing_window < 1:
        raise ValueError("smoothing_window must be positive.")

    obs = observations.sort_values("date").reset_index(drop=True).copy()
    susceptible = (population - obs["infected"] - obs["removed"]).clip(lower=1.0)
    infected = obs["infected"].clip(lower=1.0)
    removed = obs["removed"].clip(lower=0.0)

    delta_infected = infected.diff().shift(-1)
    delta_removed = removed.diff().shift(-1)
    new_infections = (delta_infected + delta_removed).clip(lower=0.0)

    raw_gamma = (delta_removed / infected).replace([np.inf, -np.inf], np.nan).clip(lower=0.0, upper=3.0)
    raw_beta = (new_infections / infected).replace([np.inf, -np.inf], np.nan).clip(lower=0.0, upper=3.0)

    params = pd.DataFrame(
        {
            "date": obs["date"],
            "day": obs["day"],
            "susceptible": susceptible,
            "infected": infected,
            "removed": removed,
            "beta_raw": raw_beta,
            "gamma_raw": raw_gamma,
        }
    ).iloc[:-1].copy()

    for col in ["beta_raw", "gamma_raw"]:
        smooth_col = col.replace("_raw", "")
        median = params[col].rolling(window=smoothing_window, min_periods=1, center=True).median()
        mean = median.rolling(window=smoothing_window, min_periods=1, center=True).mean()
        params[smooth_col] = mean.bfill().ffill().clip(lower=1e-6, upper=3.0)

    params["reproduction_number"] = params["beta"] / params["gamma"].replace(0, np.nan)
    return params


def simulate_time_varying_sir(
    observations: pd.DataFrame,
    parameter_df: pd.DataFrame,
    population: float,
    initial_infected: float,
    initial_removed: float,
    forecast_days: int = 14,
) -> pd.DataFrame:
    if forecast_days < 0:
        raise ValueError("forecast_days must be non-negative.")
    if parameter_df.empty:
        raise ValueError("parameter_df must contain at least one beta/gamma estimate.")

    obs = observations.sort_values("date").reset_index(drop=True).copy()
    total_days = len(obs) + forecast_days
    fit_steps = len(obs) - 1
    forecast_steps = forecast_days

    fit_beta = parameter_df["beta"].to_numpy(dtype=float)
    fit_gamma = parameter_df["gamma"].to_numpy(dtype=float)
    last_beta = float(pd.Series(fit_beta).tail(7).mean())
    last_gamma = float(pd.Series(fit_gamma).tail(7).mean())

    beta_series = np.concatenate([fit_beta[:fit_steps], np.repeat(last_beta, forecast_steps)])
    gamma_series = np.concatenate([fit_gamma[:fit_steps], np.repeat(last_gamma, forecast_steps)])

    susceptible = [max(population - initial_infected - initial_removed, 0.0)]
    infected = [max(initial_infected, 1.0)]
    removed = [max(initial_removed, 0.0)]

    for beta, gamma in zip(beta_series, gamma_series):
        s_t = susceptible[-1]
        i_t = infected[-1]
        r_t = removed[-1]
        new_infections = max(beta * i_t, 0.0)
        new_removed = max(gamma * i_t, 0.0)
        new_infections = min(new_infections, s_t)
        new_removed = min(new_removed, i_t + new_infections)

        susceptible.append(max(s_t - new_infections, 0.0))
        infected.append(max(i_t + new_infections - new_removed, 0.0))
        removed.append(max(r_t + new_removed, 0.0))

    output = pd.DataFrame(
        {
            "date": pd.date_range(start=obs["date"].min(), periods=total_days, freq="D"),
            "day": np.arange(total_days, dtype=float),
            "tvsir_susceptible": susceptible,
            "tvsir_infected": infected,
            "tvsir_removed": removed,
        }
    )
    output["tvsir_confirmed"] = output["tvsir_infected"] + output["tvsir_removed"]
    output["tvsir_daily_confirmed"] = output["tvsir_confirmed"].diff().fillna(output["tvsir_confirmed"]).clip(lower=0)
    output["tvsir_daily_removed"] = output["tvsir_removed"].diff().fillna(output["tvsir_removed"]).clip(lower=0)
    output["beta"] = np.concatenate([[np.nan], beta_series])
    output["gamma"] = np.concatenate([[np.nan], gamma_series])
    output["reproduction_number"] = output["beta"] / output["gamma"].replace(0, np.nan)
    output["split"] = np.where(output["day"] < len(obs), "fit", "forecast")
    output = output.merge(obs[["date", "confirmed", "infected", "removed"]], on="date", how="left")
    return output[
        [
            "date",
            "day",
            "split",
            "confirmed",
            "infected",
            "removed",
            "tvsir_confirmed",
            "tvsir_daily_confirmed",
            "tvsir_infected",
            "tvsir_removed",
            "tvsir_daily_removed",
            "tvsir_susceptible",
            "beta",
            "gamma",
            "reproduction_number",
        ]
    ]


def fit_time_varying_sir(
    observations: pd.DataFrame,
    population_upper_bound: float | None = None,
    smoothing_window: int = 7,
) -> tuple[TimeVaryingSIRFitResult, pd.DataFrame]:
    base_sir = fit_sir_model(observations, population_upper_bound=population_upper_bound)
    params = estimate_time_varying_parameters(
        observations,
        population=base_sir.effective_population,
        smoothing_window=smoothing_window,
    )
    tail = params.tail(7)
    final_beta = float(tail["beta"].mean())
    final_gamma = float(tail["gamma"].mean())
    mean_beta = float(params["beta"].mean())
    mean_gamma = float(params["gamma"].mean())

    fit = TimeVaryingSIRFitResult(
        effective_population=base_sir.effective_population,
        initial_susceptible=base_sir.initial_susceptible,
        initial_infected=base_sir.initial_infected,
        initial_removed=base_sir.initial_removed,
        mean_beta=mean_beta,
        mean_gamma=mean_gamma,
        mean_reproduction_number=float(mean_beta / mean_gamma) if mean_gamma > 0 else float("inf"),
        final_beta=final_beta,
        final_gamma=final_gamma,
        final_reproduction_number=float(final_beta / final_gamma) if final_gamma > 0 else float("inf"),
        smoothing_window=smoothing_window,
        base_sir=base_sir,
    )
    return fit, params


def add_time_varying_sir_predictions(
    observations: pd.DataFrame,
    fit: TimeVaryingSIRFitResult,
    parameter_df: pd.DataFrame,
    forecast_days: int = 14,
) -> pd.DataFrame:
    return simulate_time_varying_sir(
        observations,
        parameter_df,
        population=fit.effective_population,
        initial_infected=fit.initial_infected,
        initial_removed=fit.initial_removed,
        forecast_days=forecast_days,
    )


def time_varying_sir_metric_rows(predictions: pd.DataFrame) -> list[dict[str, float | str]]:
    fit_predictions = predictions[predictions["split"] == "fit"]
    rows = []
    for target, true_col, pred_col in [
        ("active_infected", "infected", "tvsir_infected"),
        ("removed", "removed", "tvsir_removed"),
        ("confirmed", "confirmed", "tvsir_confirmed"),
    ]:
        row = {"model": "TimeVaryingSIR", "target": target, "evaluation_scope": "descriptive_reconstruction"}
        row.update(regression_metrics(fit_predictions[true_col], fit_predictions[pred_col]))
        rows.append(row)
    return rows
