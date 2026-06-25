from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.integrate import odeint
from scipy.optimize import least_squares


@dataclass
class SIRFitResult:
    beta: float
    gamma: float
    effective_population: float
    reproduction_number: float
    initial_susceptible: float
    initial_infected: float
    initial_removed: float
    success: bool
    message: str
    cost: float


def sir_derivative(y: tuple[float, float, float], _t: float, beta: float, gamma: float, population: float) -> tuple[float, float, float]:
    """SIR differential equations."""
    susceptible, infected, removed = y
    d_s = -beta * susceptible * infected / population
    d_i = beta * susceptible * infected / population - gamma * infected
    d_r = gamma * infected
    return d_s, d_i, d_r


def simulate_sir(
    days: np.ndarray,
    beta: float,
    gamma: float,
    population: float,
    initial_infected: float,
    initial_removed: float,
) -> pd.DataFrame:
    initial_susceptible = max(population - initial_infected - initial_removed, 0.0)
    solution = odeint(
        sir_derivative,
        (initial_susceptible, initial_infected, initial_removed),
        days,
        args=(beta, gamma, population),
    )
    simulated = pd.DataFrame(solution, columns=["sir_susceptible", "sir_infected", "sir_removed"])
    simulated["sir_confirmed"] = simulated["sir_infected"] + simulated["sir_removed"]
    simulated[["sir_susceptible", "sir_infected", "sir_removed", "sir_confirmed"]] = simulated[
        ["sir_susceptible", "sir_infected", "sir_removed", "sir_confirmed"]
    ].clip(lower=0)
    simulated["sir_daily_confirmed"] = simulated["sir_confirmed"].diff().fillna(simulated["sir_confirmed"]).clip(lower=0)
    simulated["sir_daily_removed"] = simulated["sir_removed"].diff().fillna(simulated["sir_removed"]).clip(lower=0)
    return simulated


def prepare_sir_observations(df: pd.DataFrame, start_date: str | None = None, end_date: str | None = None, fit_days: int | None = 180) -> pd.DataFrame:
    """Build active infected and removed observations for SIR fitting.

    For compartment consistency, cumulative confirmed/deaths/recovered are made
    non-decreasing with cummax after known data corrections.
    """
    required = {"date", "cumulative_confirmed", "cumulative_deaths", "cumulative_recovered"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns for SIR: {sorted(missing)}")

    obs = df.copy()
    obs["date"] = pd.to_datetime(obs["date"])
    obs = obs.sort_values("date")
    obs = obs.dropna(subset=["cumulative_recovered"])

    if start_date:
        obs = obs[obs["date"] >= pd.to_datetime(start_date)]
    if end_date:
        obs = obs[obs["date"] <= pd.to_datetime(end_date)]
    if fit_days is not None and fit_days > 0:
        obs = obs.head(fit_days)

    if len(obs) < 14:
        raise ValueError("SIR fitting needs at least 14 daily observations with recovered data.")

    for col in ["cumulative_confirmed", "cumulative_deaths", "cumulative_recovered"]:
        obs[f"{col}_sir"] = obs[col].astype(float).cummax()

    obs["removed"] = obs["cumulative_deaths_sir"] + obs["cumulative_recovered_sir"]
    obs["infected"] = (obs["cumulative_confirmed_sir"] - obs["removed"]).clip(lower=0)
    obs["confirmed"] = obs["infected"] + obs["removed"]
    obs = obs[obs["confirmed"] > 0].copy()
    obs["day"] = np.arange(len(obs), dtype=float)
    return obs[["date", "day", "confirmed", "infected", "removed"]]


def fit_sir_model(observations: pd.DataFrame, population_upper_bound: float | None = None) -> SIRFitResult:
    days = observations["day"].to_numpy(dtype=float)
    infected_obs = observations["infected"].to_numpy(dtype=float)
    removed_obs = observations["removed"].to_numpy(dtype=float)
    confirmed_obs = observations["confirmed"].to_numpy(dtype=float)

    initial_infected = max(float(infected_obs[0]), 1.0)
    initial_removed = max(float(removed_obs[0]), 0.0)
    max_confirmed = max(float(np.nanmax(confirmed_obs)), initial_infected + initial_removed + 1.0)
    lower_population = max(max_confirmed * 1.01, initial_infected + initial_removed + 1.0)
    upper_population = max(float(population_upper_bound or max_confirmed * 100.0), lower_population * 1.1)

    scale_i = max(float(np.nanmax(infected_obs)), 1.0)
    scale_r = max(float(np.nanmax(removed_obs)), 1.0)
    scale_c = max(float(np.nanmax(confirmed_obs)), 1.0)

    def residuals(params: np.ndarray) -> np.ndarray:
        beta, gamma, population = params
        simulated = simulate_sir(days, beta, gamma, population, initial_infected, initial_removed)
        return np.concatenate(
            [
                (simulated["sir_infected"].to_numpy() - infected_obs) / scale_i,
                (simulated["sir_removed"].to_numpy() - removed_obs) / scale_r,
                (simulated["sir_confirmed"].to_numpy() - confirmed_obs) / scale_c,
            ]
        )

    initial_population = min(max(max_confirmed * 1.5, lower_population), upper_population)
    initial_params = np.array([0.35, 0.10, initial_population], dtype=float)
    result = least_squares(
        residuals,
        initial_params,
        bounds=([1e-6, 1e-6, lower_population], [3.0, 3.0, upper_population]),
        loss="soft_l1",
        max_nfev=5000,
    )

    beta, gamma, population = result.x
    return SIRFitResult(
        beta=float(beta),
        gamma=float(gamma),
        effective_population=float(population),
        reproduction_number=float(beta / gamma) if gamma > 0 else float("inf"),
        initial_susceptible=float(max(population - initial_infected - initial_removed, 0.0)),
        initial_infected=float(initial_infected),
        initial_removed=float(initial_removed),
        success=bool(result.success),
        message=str(result.message),
        cost=float(result.cost),
    )


def add_sir_predictions(observations: pd.DataFrame, fit: SIRFitResult, forecast_days: int = 14) -> pd.DataFrame:
    if forecast_days < 0:
        raise ValueError("forecast_days must be non-negative.")

    total_days = len(observations) + forecast_days
    days = np.arange(total_days, dtype=float)
    simulated = simulate_sir(
        days,
        fit.beta,
        fit.gamma,
        fit.effective_population,
        fit.initial_infected,
        fit.initial_removed,
    )

    start_date = observations["date"].min()
    output = simulated.copy()
    output["date"] = pd.date_range(start=start_date, periods=total_days, freq="D")
    output["day"] = days
    output["split"] = np.where(output["day"] < len(observations), "fit", "forecast")
    output = output.merge(observations[["date", "confirmed", "infected", "removed"]], on="date", how="left")
    return output[
        [
            "date",
            "day",
            "split",
            "confirmed",
            "infected",
            "removed",
            "sir_confirmed",
            "sir_daily_confirmed",
            "sir_infected",
            "sir_removed",
            "sir_daily_removed",
            "sir_susceptible",
        ]
    ]


def regression_metrics(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray) -> dict[str, float]:
    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(true) & np.isfinite(pred)
    true = true[mask]
    pred = pred[mask]
    if len(true) == 0:
        return {"RMSE": np.nan, "MAE": np.nan, "R2": np.nan}
    mse = np.mean((true - pred) ** 2)
    mae = np.mean(np.abs(true - pred))
    denom = np.sum((true - np.mean(true)) ** 2)
    r2 = 1 - np.sum((true - pred) ** 2) / denom if denom > 0 else np.nan
    return {"RMSE": float(np.sqrt(mse)), "MAE": float(mae), "R2": float(r2)}
