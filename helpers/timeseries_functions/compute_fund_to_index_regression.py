from dataclasses import dataclass

import altair as alt
import numpy as np
import pandas as pd
import statsmodels.api as sm

DEFAULT_MASTER_TIMESERIES = "Lipper"
INDEX_COLOR = "#8A8175"
FUND_COLOR = "#0F4C81"
FIT_COLOR = "#C2410C"


@dataclass
class FundIndexRegressionResult:
    regression_sample: pd.DataFrame
    regression: pd.Series
    coefficient_table: pd.DataFrame
    fit_table: pd.Series
    returns_chart: alt.Chart
    regression_chart: alt.Chart
    alpha: float
    beta: float
    r_squared: float
    n_months: int


def _format_p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def compute_fund_to_index_regression(
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    *,
    fund_name: str,
    master_timeseries: str = DEFAULT_MASTER_TIMESERIES,
    quiet: bool = False,
) -> FundIndexRegressionResult:
    """OLS of fund monthly total return on index monthly total return.

    Coefficients and inference come from statsmodels OLS. Alpha is the
    intercept. No risk-free rate is subtracted.
    """
    regression_sample = fund_timeseries[
        ["Period", "Date", index_column, master_column]
    ].dropna()
    n_months = len(regression_sample)
    if n_months < 3:
        raise ValueError("Need at least 3 months to fit the regression")

    fund_return = regression_sample[master_column].to_numpy(dtype=float)
    index_return = regression_sample[index_column].to_numpy(dtype=float)
    fit = sm.OLS(fund_return, sm.add_constant(index_return)).fit()
    estimates = np.asarray(fit.params, dtype=float)
    std_error = np.asarray(fit.bse, dtype=float)
    t_stat = np.asarray(fit.tvalues, dtype=float)
    p_value = np.asarray(fit.pvalues, dtype=float)
    confidence = np.asarray(fit.conf_int(), dtype=float)
    alpha = float(estimates[0])
    beta = float(estimates[1])
    r_squared = float(fit.rsquared)
    r_squared_adj = float(fit.rsquared_adj)
    residual_se = float(np.sqrt(fit.scale))
    f_statistic = float(np.asarray(fit.fvalue))
    f_pvalue = float(np.asarray(fit.f_pvalue))
    correlation = float(np.corrcoef(index_return, fund_return)[0, 1])

    excess = fund_return - index_return
    excess_annualized = float(excess.mean() * 12)
    residual_volatility = float(np.std(excess, ddof=1) * np.sqrt(12))
    information_ratio = excess_annualized / residual_volatility

    regression = pd.Series(
        {
            "alpha": alpha,
            "beta": beta,
            "r_squared": r_squared,
            "r_squared_adj": r_squared_adj,
            "correlation": correlation,
            "residual_se": residual_se,
            "alpha_annualized": alpha * 12,
            "n_months": n_months,
            "excess_annualized": excess_annualized,
            "residual_volatility": residual_volatility,
            "information_ratio": information_ratio,
            "f_statistic": f_statistic,
            "f_pvalue": f_pvalue,
        }
    )

    coefficient_table = pd.DataFrame(
        {
            "Estimate": estimates,
            "Std. error": std_error,
            "t": t_stat,
            "p-value": [_format_p(p) for p in p_value],
            "95% low": confidence[:, 0],
            "95% high": confidence[:, 1],
        },
        index=pd.Index(["Alpha", "Beta"], name="Parameter"),
    )
    fit_table = pd.Series(
        {
            "R²": f"{r_squared:.3f}",
            "Adjusted R²": f"{r_squared_adj:.3f}",
            "Correlation": f"{correlation:.3f}",
            "Number of months": f"{n_months}",
            "Residual standard error": f"{residual_se:.2%}",
            "Alpha, annualized (× 12)": f"{alpha * 12:+.2%}",
            "Annualized excess return": f"{excess_annualized:+.2%}",
            "Annualized residual volatility": f"{residual_volatility:.2%}",
            "Information ratio": f"{information_ratio:.2f}",
            "F statistic": f"{f_statistic:,.1f}",
            "Prob (F)": _format_p(f_pvalue),
        },
        name="Value",
    )

    start = regression_sample["Date"].min()
    end = regression_sample["Date"].max()
    if not quiet:
        print(f"{fund_name}")
        print(f"{master_timeseries} = {alpha:+.2%} + {beta:.3f} × {index_column}")
        print(
            f"{n_months} months, {start:%Y-%m-%d} to {end:%Y-%m-%d}. "
            f"Alpha is {alpha * 1e4:+.1f} bp per month "
            f"({alpha * 12:+.2%} annualized, × 12)."
        )

    history = pd.concat(
        [
            regression_sample[["Date", "Period"]].assign(
                Series=index_column, Return=regression_sample[index_column]
            ),
            regression_sample[["Date", "Period"]].assign(
                Series=master_timeseries, Return=regression_sample[master_column]
            ),
        ],
        ignore_index=True,
    )
    zero = pd.DataFrame({"Return": [0.0]})
    returns_chart = (
        alt.Chart(zero).mark_rule(color="#E4E4E4", strokeWidth=1).encode(y="Return:Q")
        + alt.Chart(history)
        .mark_line(strokeWidth=1.6)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y(
                "Return:Q",
                title="Monthly total return",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "Series:N",
                title=None,
                scale=alt.Scale(
                    domain=[index_column, master_timeseries],
                    range=[INDEX_COLOR, FUND_COLOR],
                ),
            ),
            strokeDash=alt.StrokeDash(
                "Series:N",
                title=None,
                scale=alt.Scale(
                    domain=[index_column, master_timeseries],
                    range=[[5, 3], [1, 0]],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Period:N", title="Month"),
                alt.Tooltip("Series:N"),
                alt.Tooltip("Return:Q", title="Return", format=".2%"),
            ],
        )
    ).properties(width=720, height=340, title="Monthly total return")

    scatter = regression_sample.rename(
        columns={index_column: "Index", master_column: "Fund"}
    )
    fitted_line = pd.DataFrame(
        {
            "Index": [index_return.min(), index_return.max()],
            "Fitted": [
                alpha + beta * index_return.min(),
                alpha + beta * index_return.max(),
            ],
        }
    )
    regression_chart = (
        alt.Chart(scatter)
        .mark_circle(size=48, opacity=0.75, color=FUND_COLOR)
        .encode(
            x=alt.X("Index:Q", title=index_column, axis=alt.Axis(format="%")),
            y=alt.Y(
                "Fund:Q",
                title=master_timeseries,
                axis=alt.Axis(format="%"),
            ),
            tooltip=[
                alt.Tooltip("Period:N", title="Month"),
                alt.Tooltip("Index:Q", title=index_column, format=".2%"),
                alt.Tooltip("Fund:Q", title=master_timeseries, format=".2%"),
            ],
        )
        + alt.Chart(fitted_line)
        .mark_line(color=FIT_COLOR, strokeWidth=2)
        .encode(x="Index:Q", y="Fitted:Q")
    ).properties(
        width=720,
        height=340,
        title=alt.Title(
            f"{master_timeseries} = {alpha:+.2%} + {beta:.2f} × {index_column}",
            subtitle=f"R² = {r_squared:.3f}",
        ),
    )

    return FundIndexRegressionResult(
        regression_sample=regression_sample,
        regression=regression,
        coefficient_table=coefficient_table,
        fit_table=fit_table,
        returns_chart=returns_chart,
        regression_chart=regression_chart,
        alpha=alpha,
        beta=beta,
        r_squared=r_squared,
        n_months=n_months,
    )
