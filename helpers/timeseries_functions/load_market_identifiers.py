import json
from pathlib import Path

import pandas as pd

# Timeseries row id == "category" (e.g. "Active MF") matches Funds-sheet labels.
_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "Active MF": ("mutual fund", "Active"),
    "Passive MF": ("mutual fund", "Passive"),
    "Active ETF": ("ETF", "Active"),
    "Passive ETF": ("ETF", "Passive"),
    "To Check MF": ("mutual fund", "To Check"),
}


def _wrapper_and_management(category: object) -> tuple[object, object]:
    if pd.isna(category):
        return pd.NA, pd.NA
    pair = _CATEGORY_LABELS.get(str(category).strip())
    if pair is None:
        return pd.NA, pd.NA
    return pair[0], pair[1]


def load_market_identifiers(timeseries_df, cache_relative) -> pd.DataFrame:

    # Excel row 1 is the column header (an ISIN for each fund).
    # Long name and vehicle / management labels live on rows where id is "name" or "category".
    name_row = timeseries_df.loc[timeseries_df["id"].eq("name")].iloc[0]
    category_row = timeseries_df.loc[timeseries_df["id"].eq("category")].iloc[0]

    funds = pd.DataFrame(
        {
            "ISIN": timeseries_df.columns,
            "Name": name_row.reindex(timeseries_df.columns).to_numpy(),
            "category": category_row.reindex(timeseries_df.columns).to_numpy(),
        }
    )
    funds = funds.loc[
        funds["ISIN"].astype("string").str.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d")
    ].reset_index(drop=True)
    wrapper_management = funds["category"].map(_wrapper_and_management)
    funds["fund_wrapper"] = wrapper_management.map(lambda pair: pair[0])
    funds["fund_type"] = wrapper_management.map(lambda pair: pair[1])
    funds = funds.drop(columns=["category"])
    funds = funds.astype(
        {"ISIN": "string", "Name": "string", "fund_wrapper": "string", "fund_type": "string"}
    )

    print("Read the list of funds - found", len(funds), "funds")

    # Lookup market identifier in `cache-isin-openfigi.json`
    def find_cache(cache_relative) -> Path:
        """Find the OpenFIGI cache whether the kernel cwd is code/ or notebooks/."""
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            candidate = directory / cache_relative
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(
            f"Could not find {cache_relative}, starting from {start}"
        )

    isin_cache = json.loads(find_cache(cache_relative).read_text())
    tickers = {
        isin: ticker
        for isin, ticker in isin_cache.items()
        if isinstance(ticker, str) and ticker
    }
    funds["market_identifier"] = funds["ISIN"].map(tickers).astype("string")
    num_with_identifier = funds["market_identifier"].notna().sum()
    num_without_identifier = funds["market_identifier"].isna().sum()
    print("Mapped to market identifiers")
    print(f"- Funds with market identifier: {num_with_identifier}")
    print(f"- Funds without market identifier: {num_without_identifier}")

    return funds
