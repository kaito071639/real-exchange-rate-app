"""Real Exchange Rate Explorer — IMF SDMX 3.0, Python 3.12."""
from __future__ import annotations

from datetime import date
from io import StringIO
import re

import altair as alt
from babel.numbers import get_territory_currencies
import numpy as np
import pandas as pd
import pycountry
import requests
import streamlit as st

BASE_URL = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA"
FIRST_MONTH = pd.Timestamp("1976-01-01")

st.set_page_config(page_title="Real Exchange Rate Explorer", page_icon="🌐", layout="wide")


def countries() -> dict[str, tuple[str, str]]:
    """IMF-compatible ISO3 candidates plus the IMF euro-area aggregate."""
    choices = {"Euro area (G163)": ("G163", "EUR")}
    overrides = {"GBR": "GBP", "USA": "USD", "JPN": "JPY", "CHN": "CNY"}
    for country in pycountry.countries:
        code = country.alpha_3
        currencies = get_territory_currencies(country.alpha_2, tender=True)
        if not currencies and code not in overrides:
            continue
        currency = overrides.get(code, currencies[0] if currencies else "")
        choices[f"{country.name} ({code})"] = (code, currency)
    return dict(sorted(choices.items()))


@st.cache_data(ttl=86400, show_spinner=False)
def imf_series(flow: str, key: str) -> pd.Series:
    """Retrieve monthly observations as IMF SDMX 3.0 CSV; never fabricate data."""
    url = f"{BASE_URL}/{flow}/~/{key}"
    params = {"c[TIME_PERIOD]": "ge:1976-M01"}
    headers = {"Accept": "text/csv", "User-Agent": "RER-Streamlit-Teaching-App/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=55)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"IMF download failed for {key}: {exc}") from exc
    if not response.content or not response.text.strip():
        raise ValueError(f"IMF returned no observations for {key}.")
    try:
        raw = pd.read_csv(StringIO(response.text), low_memory=False)
    except Exception as exc:
        raise ValueError(f"IMF did not return readable CSV for {key}: {exc}") from exc
    raw.columns = raw.columns.str.strip().str.upper()
    if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(raw.columns):
        raise ValueError(
            f"Unexpected IMF response for {key}; columns: {list(raw.columns)}. "
            "The IMF may be temporarily unavailable or may have changed its format."
        )
    # An exact key should match one series; filter defensively if metadata is included.
    expected_country = key.split(".")[0]
    if "COUNTRY" in raw.columns:
        raw = raw.loc[raw["COUNTRY"].astype(str) == expected_country]
    month = raw["TIME_PERIOD"].astype(str).str.replace(r"-M(\d{2})$", r"-\1", regex=True)
    parsed_dates = pd.to_datetime(month, format="%Y-%m", errors="coerce")
    values = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")
    series = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(parsed_dates), dtype=float)
    series = series.loc[series.index.notna() & np.isfinite(series) & (series > 0)]
    series = series.loc[series.index >= FIRST_MONTH]
    series = series[~series.index.duplicated(keep="last")].sort_index()
    if series.empty:
        raise ValueError(f"No usable monthly observations from January 1976 onward for {key}.")
    return series


def fetch_cpi(code: str) -> pd.Series:
    return imf_series("CPI", f"{code}.CPI._T.IX.M")


def fetch_fx(code: str, cpi_index: pd.DatetimeIndex) -> pd.Series:
    # The domestic-currency-per-USD exchange rate is identically one for the USA.
    if code == "USA":
        return pd.Series(1.0, index=cpi_index, name="fx_per_usd")
    return imf_series("ER", f"{code}.XDC_USD.PA_RT.M")


def calculate(cpi1: pd.Series, cpi2: pd.Series, fx1: pd.Series, fx2: pd.Series,
              start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, float]:
    combined = pd.concat([cpi1.rename("P1_CPI"), cpi2.rename("P2_CPI"),
                          fx1.rename("FX1_local_per_USD"),
                          fx2.rename("FX2_local_per_USD")], axis=1)
    combined = combined.loc[(combined.index >= start) & (combined.index <= end)].copy()
    combined = combined.replace([np.inf, -np.inf], np.nan).dropna()
    combined = combined.loc[(combined > 0).all(axis=1)].copy()
    if combined.empty:
        raise ValueError("No overlapping, positive CPI and exchange-rate observations in this period.")
    # FX_i = currency i per USD; therefore FX2 / FX1 = currency 2 per currency 1.
    combined["S_currency2_per_currency1"] = (
        combined["FX2_local_per_USD"] / combined["FX1_local_per_USD"]
    )
    combined["RER"] = (
        combined["S_currency2_per_currency1"] * combined["P1_CPI"] / combined["P2_CPI"]
    )
    rer_mean = float(combined["RER"].mean())
    combined["Real_Index"] = 100.0 * combined["RER"] / rer_mean
    combined.index.name = "Month"
    return combined, rer_mean


st.title("🌐 Real Exchange Rate Explorer")
st.caption("Monthly IMF CPI and exchange rates · January 1976 onward where available")
st.markdown(
    "**Definition:** S = units of Country 2 currency per 1 unit of Country 1 currency. "
    "RER = S × P1 / P2. The Real Index equals 100 × RER / the sample mean RER."
)

choices = countries()
labels = list(choices)
default_uk = next(k for k in labels if "(GBR)" in k)
default_us = next(k for k in labels if "(USA)" in k)

with st.sidebar:
    st.header("Settings")
    label1 = st.selectbox("Country 1", labels, index=labels.index(default_uk))
    label2 = st.selectbox("Country 2", labels, index=labels.index(default_us))
    display = st.radio("Display", ["Real", "Nominal", "Both"], index=2)
    st.caption("Monthly period-average FX rates and CPI index levels from IMF.")

code1, currency1 = choices[label1]
code2, currency2 = choices[label2]
if code1 == code2:
    st.warning("Select two different countries or regions.")
    st.stop()

try:
    with st.spinner("Downloading monthly CPI and exchange rates from IMF…"):
        p1 = fetch_cpi(code1)
        p2 = fetch_cpi(code2)
        x1 = fetch_fx(code1, p1.index)
        x2 = fetch_fx(code2, p2.index)
except (RuntimeError, ValueError) as exc:
    st.error(str(exc))
    st.info("Some countries or the euro area may have missing IMF series. Try UK / US, or retry later if the IMF API is unavailable.")
    st.stop()

available_start = max(s.index.min() for s in [p1, p2, x1, x2])
available_end = min(s.index.max() for s in [p1, p2, x1, x2])
if available_start > available_end:
    st.error("These countries have no overlapping monthly IMF observations.")
    st.stop()

st.subheader("Sample period")
left, right = st.columns(2)
with left:
    start_date = st.date_input("Start month", value=available_start.date(),
                               min_value=available_start.date(), max_value=available_end.date())
with right:
    end_date = st.date_input("End month", value=available_end.date(),
                             min_value=available_start.date(), max_value=available_end.date())
start = pd.Timestamp(start_date).replace(day=1)
end = pd.Timestamp(end_date).replace(day=1)
if start > end:
    st.warning("Start month must be no later than end month.")
    st.stop()

try:
    data, mean_rer = calculate(p1, p2, x1, x2, start, end)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.caption(f"Nominal quotation: **{currency2} per {currency1}** · "
           f"Valid overlapping months: **{len(data)}** · "
           f"Actual sample: **{data.index.min():%Y-%m} to {data.index.max():%Y-%m}**")

m1, m2, m3 = st.columns(3)
m1.metric("Mean RER (selected sample)", f"{mean_rer:,.5f}")
m2.metric("Mean Real Index", f"{data['Real_Index'].mean():.6f}")
m3.metric(f"Latest nominal ({currency2}/{currency1})", f"{data['S_currency2_per_currency1'].iloc[-1]:,.5f}")

chart_data = data.reset_index()
real_chart = (
    alt.Chart(chart_data).mark_line(color="#168A78", strokeWidth=2)
    .encode(x=alt.X("Month:T", title="Month"),
            y=alt.Y("Real_Index:Q", title="Real Index (sample mean = 100)", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Month:T", format="%Y-%m"), alt.Tooltip("Real_Index:Q", format=".3f")])
)
nominal_chart = (
    alt.Chart(chart_data).mark_line(color="#DE8730", strokeWidth=2)
    .encode(x=alt.X("Month:T", title="Month"),
            y=alt.Y("S_currency2_per_currency1:Q", title=f"Nominal: {currency2} per {currency1}",
                    scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Month:T", format="%Y-%m"),
                     alt.Tooltip("S_currency2_per_currency1:Q", format=".5f")])
)
if display == "Real":
    chart = real_chart
elif display == "Nominal":
    chart = nominal_chart
else:
    chart = alt.layer(real_chart, nominal_chart).resolve_scale(y="independent")
st.altair_chart(chart.properties(height=420).interactive(), use_container_width=True)

st.subheader("Observations and calculations")
st.dataframe(data, use_container_width=True)
csv = data.reset_index().to_csv(index=False, float_format="%.12g").encode("utf-8")
st.download_button("⬇ Download selected sample as CSV", data=csv,
                   file_name=f"rer_{code1}_{code2}_{start:%Y%m}_{end:%Y%m}.csv",
                   mime="text/csv", type="primary")

with st.expander("Calculation and verification notes"):
    st.markdown(
        f"""- IMF CPI: `{code1}.CPI._T.IX.M` and `{code2}.CPI._T.IX.M` (dataflow `CPI`).
- IMF FX: `{code1}.XDC_USD.PA_RT.M` and `{code2}.XDC_USD.PA_RT.M` (dataflow `ER`); US dollar FX = 1 by definition.
- **S = FX2 / FX1**, since each raw FX rate is local currency units per USD.
- **RER = S × P1 / P2**; **RER* = arithmetic mean of valid monthly RER** in the selected sample.
- **Real Index = 100 × RER / RER***. Its arithmetic mean across exported valid months is 100 (subject to rounding).
- Missing, nonpositive, or unmatched months are excluded, not interpolated. Changing dates recomputes RER*.
- Nominal FX is shown in actual currency units, **never normalized**.
- CPI index base years can differ across countries; the normalized Real Index is sample-relative and is not an absolute PPP valuation.
- The IMF may not publish the full history or every series for every ISO country or the euro-area aggregate.
"""
    )
    first = data.iloc[0]
    st.code(
        f"{data.index[0]:%Y-%m}: S = {first['FX2_local_per_USD']:.8g} / "
        f"{first['FX1_local_per_USD']:.8g} = {first['S_currency2_per_currency1']:.8g}\n"
        f"RER = {first['S_currency2_per_currency1']:.8g} × "
        f"{first['P1_CPI']:.8g} / {first['P2_CPI']:.8g} = {first['RER']:.8g}\n"
        f"Real Index = 100 × {first['RER']:.8g} / {mean_rer:.8g} "
        f"= {first['Real_Index']:.8g}", language="text"
    )

st.caption("Source: IMF SDMX 3.0 API (IMF.STA CPI and ER dataflows). No API key required; live availability may vary.")
