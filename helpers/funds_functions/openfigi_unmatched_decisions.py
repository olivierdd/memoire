"""Decisions for selected funds with no OpenFIGI ISIN match.

Six of the seven unmatched ISINs are closed or merged identifiers. Missing
OpenFIGI is a symptom of a dead listing: even a manual FIGI would not restore
usable history, primary-class confirmation, or classification DQ. Those rows
are dropped from the working selection.

John Hancock US Sector Rotation Fund;NAV is live, already selected, matched on
EDGAR by name (only class), and has a clean daily total-return series. It stays
with an identity-quality caveat because ``openfigi_market_id`` remains empty.
"""

from __future__ import annotations

import pandas as pd

DROP_ISINS: frozenset[str] = frozenset(
    {
        "US4791648656",  # Johnson Disciplined Large-Cap Fund
        "US31678R6760",  # Fifth Third Equity Index Fund;A
        "US31617F8178",  # Fidelity Advisor Series Growth & Income Fund
        "US22540Y8663",  # Aberdeen US Equity II Fund;A
        "US31678R6273",  # Fifth Third Structured Large Cap Plus Fund;A
        "US3167865654",  # Fifth Third Dividend Growth Fund;A
    }
)

KEEP_ISIN = "US47805T7651"  # John Hancock US Sector Rotation Fund;NAV
IDENTITY_QUALITY_CAVEAT = "no OpenFIGI match; EDGAR-only identity"

# Static review rows shown in the notebook (Name, ISIN, pipeline status, why).
UNMATCHED_REVIEW: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "Johnson Disciplined Large-Cap Fund",
        "US4791648656",
        "Already dropped (is_selected=False)",
        "Merged into Johnson Growth Fund (Dec 2011); no timeseries; no TE",
        "Drop",
    ),
    (
        "Fifth Third Equity Index Fund;A",
        "US31678R6760",
        "Already dropped (is_selected=False)",
        "Liquidated Jul 2012; flat stale prices; no TE",
        "Drop",
    ),
    (
        "Fidelity Advisor Series Growth & Income Fund",
        "US31617F8178",
        "Already dropped (is_selected=False)",
        "Feeder/reorganized into Series Large Cap Stock (Sep 2018); no usable TR",
        "Drop",
    ),
    (
        "Aberdeen US Equity II Fund;A",
        "US22540Y8663",
        "Already dropped (is_selected=False)",
        "Merged into Aberdeen U.S. Equity (Feb 2013); no timeseries",
        "Drop",
    ),
    (
        "Fifth Third Structured Large Cap Plus Fund;A",
        "US31678R6273",
        "Already dropped (is_selected=False)",
        "Liquidated Jul 2012; flat prices; Alternatives labeled but Lipper Equity US",
        "Drop",
    ),
    (
        "Fifth Third Dividend Growth Fund;A",
        "US3167865654",
        "Already dropped (is_selected=False)",
        "Liquidated Jul 2012; flat prices; no TE",
        "Drop",
    ),
    (
        "John Hancock US Sector Rotation Fund;NAV",
        "US47805T7651",
        "Still in Funds final",
        "Live fund; EDGAR matched by name; only class; has daily TR",
        "Keep (caveat)",
    ),
)


def unmatched_review_frame() -> pd.DataFrame:
    """Return the documented review table for the seven unmatched funds."""
    return pd.DataFrame(
        UNMATCHED_REVIEW,
        columns=["Name", "ISIN", "Status in pipeline", "Why it fails downstream", "Decision"],
    )


def apply_openfigi_unmatched_decisions(
    funds: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop the six closed/merged unmatched funds; keep John Hancock with a flag.

    Returns ``(kept_funds, decision_log)``. ``kept_funds`` is a copy of ``funds``
    without the drop ISINs. John Hancock gets ``openfigi_identity_quality`` set
    to ``IDENTITY_QUALITY_CAVEAT``; other kept rows get a blank value when the
    column is created.
    """
    if "ISIN" not in funds.columns:
        raise KeyError("funds must include an ISIN column")

    isin = funds["ISIN"].astype("string").str.strip().str.upper()
    decision_log = unmatched_review_frame().copy()
    present = set(isin.dropna().tolist())
    decision_log["present_in_selection"] = decision_log["ISIN"].isin(present)

    drop_mask = isin.isin(DROP_ISINS)
    kept = funds.loc[~drop_mask].copy()
    if "openfigi_identity_quality" not in kept.columns:
        kept["openfigi_identity_quality"] = pd.Series(pd.NA, index=kept.index, dtype="string")
    else:
        kept["openfigi_identity_quality"] = kept["openfigi_identity_quality"].astype("string")

    keep_mask = (
        kept["ISIN"].astype("string").str.strip().str.upper().eq(KEEP_ISIN)
    )
    kept.loc[keep_mask, "openfigi_identity_quality"] = IDENTITY_QUALITY_CAVEAT

    dropped = int(drop_mask.sum())
    kept_count = int(keep_mask.sum())
    print(
        f"OpenFIGI unmatched decisions: dropped {dropped} closed/merged funds; "
        f"kept {kept_count} with identity-quality caveat "
        f"({len(kept)} funds remain)"
    )
    return kept, decision_log
