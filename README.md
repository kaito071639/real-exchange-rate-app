# Real Exchange Rate Explorer

A Python 3.12 Streamlit app using **live IMF SDMX 3.0** monthly CPI and exchange-rate data, where available from January 1976.

## What it does

- Select Country 1 and Country 2 from ISO3 country choices and the IMF euro area (`G163`). IMF coverage varies; not every listed country has both series.
- Select start and end months and display **Real**, **Nominal**, or **Both** with separate y-axes.
- Export all valid monthly observations and calculations for the selected period as CSV.
- Inspect an automatically generated worked example using the first month of the selected sample.

## Economics

Let `FX1` and `FX2` be IMF period-average exchange rates measured as domestic currency units per USD.

- `S = FX2 / FX1`: Country 2 currency per one Country 1 currency.
- `RER = S × P1 / P2`, with `P1` and `P2` the countries' CPI indices.
- `RER* = mean(RER)` over months with all four valid inputs **within the selected sample**.
- `Real Index = 100 × RER / RER*` (sample mean = 100).
- Nominal `S` is plotted in **actual currency units** and is **not normalized**.

For **UK → US**, `S` is **USD per GBP**. The US FX series is exactly 1 local unit per USD. Missing or nonpositive values are excluded without interpolation. CPI index base-year differences do not affect the sample-normalized index.

## IMF data

- IMF SDMX 3.0: https://api.imf.org/external/sdmx/3.0
- CPI dataflow `IMF.STA/CPI`, key `{ISO3}.CPI._T.IX.M`
- Exchange-rate dataflow `IMF.STA/ER`, key `{ISO3}.XDC_USD.PA_RT.M`
- Euro area code: `G163`

The app requests IMF CSV data and uses positive, overlapping monthly observations. Coverage is limited by IMF availability. Live IMF API requests can occasionally fail; retry later if the endpoint is unavailable.

## Deploy

1. Create a public GitHub repository named `real-exchange-rate-app`.
2. Place `app.py`, `requirements.txt`, and `README.md` at the repository root.
3. At https://share.streamlit.io select **Create app**, your repository, branch `main`, and main file `app.py`.
4. Under Advanced settings choose **Python 3.12**, leave Secrets empty, and deploy.

## Validation / assignment checklist

1. Select **United Kingdom (GBR)** for Country 1 and **United States (USA)** for Country 2; confirm nominal `S` is USD per GBP.
2. Change the sample start/end dates and export a CSV; verify that `Real_Index` averages 100 over the exported rows (allowing CSV rounding).
3. For one month, compute `S = FX2 / FX1`, `RER = S × P1 / P2`, and `Real_Index = 100 × RER / sample mean RER` from exported columns.
4. Test Real, Nominal, and Both views; confirm separate y-axes in Both.
5. Submit your live Streamlit URL, GitHub URL, prompt/chat screenshots, model and date, one manual RER calculation, and the CSV.

## AI development record

- Model: ChatGPT (GPT-6)
- Date: 2026-10-26
- Prompt: The full course assignment instructions provided to the model, followed by the request "コード書いて" ("Write the code").

The app's code was statically checked, but **live IMF access and Streamlit deployment must be tested after publishing**.
