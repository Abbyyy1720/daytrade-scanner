import yfinance as yf
import pandas as pd
import json
import requests
from datetime import datetime

STOCKS = [
    {"code": "2382.TW", "name": "廣達", "twse_name": "廣達電腦"},
    {"code": "2317.TW", "name": "鴻海", "twse_name": "鴻海精密"},
    {"code": "2603.TW", "name": "長榮", "twse_name": "長榮海運"},
    {"code": "3481.TW", "name": "群創", "twse_name": "群創光電"},
    {"code": "2886.TW", "name": "兆豐金", "twse_name": "兆豐金控"},
    {"code": "2303.TW", "name": "聯電", "twse_name": "聯華電子"},
    {"code": "2891.TW", "name": "中信金", "twse_name": "中信金控"},
    {"code": "2882.TW", "name": "國泰金", "twse_name": "國泰金控"},
]

def fetch_all_foreign():
    try:
        url = "https://www.twse.com.tw/rwd/zh/fund/TWT38U?response=json"
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = res.json()
        result = {}
        for row in data.get("data", []):
            name = row[0].strip()
            buy = int(row[2].replace(",", ""))
            sell = int(row[3].replace(",", ""))
            result[name] = (buy - sell) // 1000
        print(f"外資資料抓取成功，共 {len(result)} 筆")
        return result
    except Exception as e:
        print(f"外資資料抓取失敗: {e}")
        return {}

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

foreign_data = fetch_all_foreign()
results = []

for s in STOCKS:
    try:
        ticker = yf.Ticker(s["code"])
        hist = ticker.history(period="60d")
        if hist.empty or len(hist) < 20:
            print(f"{s['code']} 資料不足，跳過")
            continue

        price = round(hist["Close"].iloc[-1], 1)
        if price > 200:
            print(f"{s['code']} 股價 {price} 超過200元，跳過")
            continue

        vol_today = int(hist["Volume"].iloc[-1] / 1000)
        vol_5avg = int(hist["Volume"].tail(5).mean() / 1000)
        if vol_5avg < 2000:
            print(f"{s['code']} 均量 {vol_5avg} 不足2000張，跳過")
            continue

        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)

        foreign_buy = foreign_data.get(s["twse_name"], 0)
        print(f"{s['name']} 外資買賣超: {foreign_buy} 張")

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
            "tags": [],
            "reason": ""
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
