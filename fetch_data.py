import yfinance as yf
import pandas as pd
import json
import requests
from datetime import datetime

def fetch_top_volume_stocks(limit=50):
    """
    🔥 全自動海選：直接從證交所 API 抓取今日成交量前 limit 名的股票
    """
    print("正在從證交所獲取今日熱門成交量排行...")
    try:
        # 抓取今日大盤成交量排行 API
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = res.json()
        
        dynamic_stocks = []
        # 解析證交所的名單 (前 limit 名)
        for row in data.get("data", [])[:limit]:
            code = row[1].strip()     # 股票代號 (例如: 2330)
            name = row[2].strip()     # 股票名稱 (例如: 台積電)
            
            # 過濾掉權證(代號通常6碼)、ETF(00開頭或含有英文字母)
            if len(code) == 4 and not code.startswith('00'):
                dynamic_stocks.append({
                    "code": f"{code}.TW",
                    "name": name,
                    "twse_name": name if "控" in name or "銀" in name or "鋼" in name else name
                })
        print(f"成功自動鎖定今日最熱門的 {len(dynamic_stocks)} 檔台股個股！")
        return dynamic_stocks
    except Exception as e:
        print(f"自動抓取熱門股失敗: {e}，改用備用基本清單。")
        # 萬一證交所 API 斷線的備用基本款
        return [{"code": "2317.TW", "name": "鴻海", "twse_name": "鴻海精密"}]

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
    return round(vr, 1) if not pd.isna(vr) else 100.0

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return round(tr.rolling(period).mean().iloc[-1], 1)

def calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status):
    vol_score = min(vol_ratio / 2, 1) * 100
    atr_percent = (atr / price) * 100
    atr_score = min(atr_percent / 3.5, 1) * 100
    foreign_score = 100 if foreign_buy > 3000 else 75 if foreign_buy > 1000 else 50 if foreign_buy > 0 else 20
    vr_score = 100 if vr > 130 else 70 if vr > 100 else 40 if vr > 80 else 20
    kd_score = 100 if kd_status == "up" else 70 if kd_status == "cross" else 20
    total = vol_score*0.30 + atr_score*0.25 + foreign_score*0.20 + vr_score*0.15 + kd_score*0.10
    return round(total)

# 执行海选
STOCKS = fetch_top_volume_stocks(limit=60) # 抓前 60 名來過濾
foreign_data = fetch_all_foreign()
results = []

for s in STOCKS:
    try:
        ticker = yf.Ticker(s["code"])
        hist = ticker.history(period="60d")
        if hist.empty or len(hist) < 20:
            continue

        price = round(hist["Close"].iloc[-1], 1)
        if price > 200: # 延續你的股價 200 以下限制
            continue

        vol_today = int(hist["Volume"].iloc[-1] / 1000)
        vol_5avg = int(hist["Volume"].tail(5).mean() / 1000)
        
        # 只要 5 日均量大於 500 張的熱門股通通進來
        if vol_5avg < 500:
            continue

        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)

        # 模糊比對外資名稱
        foreign_buy = 0
        for k, v in foreign_data.items():
            if s["name"] in k or k in s["name"]:
                foreign_buy = v
                break

        if kd_k > kd_d + 3:
            kd_status = "up"
            kd_label = "K>D 向上"
        elif kd_k > kd_d:
            kd_status = "cross"
            kd_label = "K 剛交叉 D"
        else:
            kd_status = "dn"
            kd_label = "K<D 偏弱"

        score = calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status)

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
            "reason": "動態爆量股追蹤中。"
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

print(f"全自動化完成，共 {len(results)} 支爆量熱門股寫入 data.json")
