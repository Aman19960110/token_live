import streamlit as st
from tvDatafeed import TvDatafeed, Interval
import pytz
import datetime
import time
import pandas as pd
from nselib import capital_market

# -------------------------
# Streamlit App Layout
# -------------------------
st.set_page_config(page_title="VWAP Settlement", layout="centered")

st.title("📊 Settlement Tracker")
st.write("This app fetches live data from TradingView and calculates VWAP for the selected stock.")

# -------------------------
# User Input
# -------------------------
#username = st.text_input("TradingView Username", type="default")
#password = st.text_input("TradingView Password", type="password")
stock_list = list(capital_market.fno_equity_list()['symbol'])
stock_name = st.selectbox("Enter Stock Symbol (e.g., 'UPL')",options=stock_list)
market = st.selectbox("Select Market", ["NSE", "BSE"], index=0)

run_button = st.button("Fetch")
username = 'YourTradingViewUsername'
password = 'YourTradingViewPassword'
tv = TvDatafeed(username, password)
# -------------------------
# VWAP Calculation Function
# -------------------------
def settlement(stock_name, market):
    try:

        df = tv.get_hist(
            symbol=stock_name,
            exchange=market,
            interval=Interval.in_1_minute,
            n_bars=1000
        )

        # Convert to IST
        df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")

        # Filter today's data
        current_date = datetime.date.today()
        df = df[df.index.date == current_date]

        # Filter after 10 AM
        required_time = datetime.time(3, 0)
        df = df[df.index.time >= required_time]

        if not df.empty:
            df["cls_vol"] = df["close"] * df["volume"]
            vwap_price = df["cls_vol"].sum() / df["volume"].sum()
            return vwap_price, df
        else:
            return None, None

    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None, None

# -------------------------
# Run on Button Click
# -------------------------
if run_button:
    if username and password:
        with st.spinner("Fetching data..."):
            vwap, df = settlement(stock_name, market)
        
        if vwap:
            st.success(f"VWAP for **{stock_name}** (Today after 3:00 PM): **₹{vwap:.2f}**")
            st.line_chart(df["close"])
        else:
            st.warning("No data available. Please try after 3:00 PM.")
    else:
        st.warning("Please enter your TradingView username and password.")
