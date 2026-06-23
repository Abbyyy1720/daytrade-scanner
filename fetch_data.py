import yfinance as yf
import pandas as pd
import json
import requests
from datetime import datetime, timedelta

# 候選股票清單（股價200以下、日均量2000張以上）
STOCKS = [
    {"code": "2382.TW", "name": "廣達"},
    {"code": "2317.TW", "name": "鴻海"},
    {"code": "2603.TW", "name": "長榮"},
    {"code": "3481.TW", "name": "群創"},
    {"code": "2886.TW", "name": "兆豐金"},
    {"code": "2303.TW", "name": "聯電"},
    {"code": "2891.TW", "name": "中信金"},
    {"code": "2882.TW", "name": "國泰金"},
]

def calc_kd(high, low, close, period=9):
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    return round(k.iloc[-1], 1), round(d.iloc[-1], 1)

def calc_vr(close, volume, period=26):
    price_change = close.diff()
    up_vol = volume.where(price_change > 0, 0).rolling(period).sum()
    dn_vol = volume.where(price_change < 0, 0).rolling(period).sum()
    vr = (up_vol / dn_vol * 100).iloc[-1]
    return round(vr, 1)

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return round(tr.rolling(period).mean().iloc[-1], 1)

def calc_score(vol_ratio, atr, foreign_buy, vr, kd_status):
    vol_score = min(vol_ratio / 2, 1) * 100
    atr_score = min(atr / 15, 1) * 100
    foreign_score = 100 if foreign_buy > 3000 else 75 if foreign_buy > 1000 else 50 if foreign_buy > 0 else 20
    vr_score = 100 if vr > 130 else 70 if vr > 100 else 40 if vr > 80 else 20
    kd_score = 100 if kd_status == "up" else 70 if kd_status == "cross" else 20
    total = vol_score*0.30 + atr_score*0.25 + foreign_score*0.20 + vr_score*0.15 + kd_score*0.10
    return round(total)

def fetch_foreign_buy(code):
    # 證交所外資買賣超（模擬，實際串接需額外處理）
    import random
    return random.randint(-2000, 5000)

results = []

for s in STOCKS:
    try:
        ticker = yf.Ticker(s["code"])
        hist = ticker.history(period="60d")
        if hist.empty or len(hist) < 20:
            continue

        price = round(hist["Close"].iloc[-1], 1)
        if price > 200:
            continue

        vol_today = int(hist["Volume"].iloc[-1] / 1000)
        vol_5avg = int(hist["Volume"].tail(5).mean() / 1000)
        if vol_5avg < 2000:
            continue

        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)
        foreign_buy = fetch_foreign_buy(s["code"])

        if kd_k > kd_d + 3:
            kd_status = "up"
            kd_label = "K>D 向上"
        elif kd_k > kd_d:
            kd_status = "cross"
            kd_label = "K 剛交叉 D"
        else:
            kd_status = "dn"
            kd_label = "K<D 偏弱"

        score = calc_score(vol_ratio, atr, foreign_buy, vr, kd_status)

        results.append({
            "code": s["code"].replace(".TW", ""),
            "name": s["name"],
            "price": price,
            "chg": f"+{chg}%" if chg >= 0 else f"{chg}%",
            "vol": vol_today,
            "avgVol": vol_5avg,
            "atr": atr,
            "vr": vr,
            "kdK": kd_k,
            "kdD": kd_d,
            "kdStatus": kd_status,
            "kdLabel": kd_label,
            "foreignBuy": foreign_buy,
            "vol5": vol5,
            "score": score,
            "badge": "hot" if score >= 65 else "watch",
            "badgeLabel": "熱門" if score >= 65 else "觀察",
        })

    except Exception as e:
        print(f"Error fetching {s['code']}: {e}")

results.sort(key=lambda x: x["score"], reverse=True)

output = {
    "updated": datetime.now().strftime("%Y/%m/%d %H:%M"),
    "stocks": results
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"完成，共 {len(results)} 支股票寫入 data.json")
