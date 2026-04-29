import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import pytz
import concurrent.futures

# ================= CONFIG =================
BASE_URL = "https://api.binance.com/api/v3/klines"

TIMEFRAME_MAP = {
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1d"
}

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc

# ================= UI =================
st.title("📊 Crypto Breakout Screener")

timeframe = st.selectbox("Select Timeframe", list(TIMEFRAME_MAP.keys()))
coin_limit = st.selectbox("Select Coins", [50, 100, 200, 400])

# 🔥 NEW: Pattern Selection
pattern_choice = st.selectbox(
    "Select Pattern",
    ["Inside Bar", "Engulfing", "Both"]
)

user_date = st.date_input("Select Date")
user_time = st.time_input("Select Time (IST)")

run_button = st.button("Run Scanner")

# ================= FUNCTIONS =================
def get_target_timestamp():
    dt_ist = IST.localize(datetime.combine(user_date, user_time))
    dt_utc = dt_ist.astimezone(UTC)
    return int(dt_utc.timestamp() * 1000)

def get_top_symbols(limit):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    data = requests.get(url).json()

    usdt_pairs = [x for x in data if x["symbol"].endswith("USDT")]
    sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x["quoteVolume"]), reverse=True)

    return [x["symbol"] for x in sorted_pairs[:limit]]

def get_klines(symbol):
    params = {
        "symbol": symbol,
        "interval": timeframe,
        "limit": 100
    }
    res = requests.get(BASE_URL, params=params).json()

    df = pd.DataFrame(res, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","tbav","tqav","ignore"
    ])

    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    return df

def get_last_3_closed(df, target_ts):
    df = df[df["time"] < pd.to_datetime(target_ts, unit="ms")]
    if len(df) < 3:
        return None
    return df.iloc[-3], df.iloc[-2], df.iloc[-1]

# ================= PATTERN LOGIC =================
def check_inside_bar(c1, c2, c3):
    if c2["high"] < c1["high"] and c2["low"] > c1["low"]:
        if c3["close"] > c1["high"]:
            return "Inside Bar Breakout", "Bullish"
        elif c3["close"] < c1["low"]:
            return "Inside Bar Breakout", "Bearish"
    return None

def check_engulfing(c1, c2, c3):
    if c2["open"] < c1["close"] and c2["close"] > c1["open"]:
        if c3["close"] > max(c1["high"], c2["high"]):
            return "Bullish Engulfing Breakout", "Bullish"

    if c2["open"] > c1["close"] and c2["close"] < c1["open"]:
        if c3["close"] < min(c1["low"], c2["low"]):
            return "Bearish Engulfing Breakout", "Bearish"

    return None

# ================= SCAN =================
def scan_symbol(symbol, target_ts):
    try:
        df = get_klines(symbol)
        candles = get_last_3_closed(df, target_ts)

        if candles is None:
            return None

        c1, c2, c3 = candles

        # 🔥 Apply pattern filter
        if pattern_choice in ["Inside Bar", "Both"]:
            result = check_inside_bar(c1, c2, c3)
            if result:
                return (symbol, timeframe, result[0], result[1], str(c3["time"]))

        if pattern_choice in ["Engulfing", "Both"]:
            result = check_engulfing(c1, c2, c3)
            if result:
                return (symbol, timeframe, result[0], result[1], str(c3["time"]))

    except:
        return None

    return None

# ================= RUN =================
if run_button:
    st.write("🔍 Scanning...")

    target_ts = get_target_timestamp()
    symbols = get_top_symbols(coin_limit)

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(scan_symbol, sym, target_ts) for sym in symbols]

        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    df = pd.DataFrame(results, columns=[
        "Symbol", "Timeframe", "Pattern", "Direction", "Candle Time"
    ])

    if not df.empty:
        df["Candle Time"] = pd.to_datetime(df["Candle Time"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False), "results.csv")
    else:
        st.warning("No patterns found.")