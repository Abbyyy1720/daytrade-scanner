import yfinance as yf
import pandas as pd
import json
import requests
import datetime

def fetch_top_volume_stocks(limit=60):
    """
    自動海選成交量前 limit 名的股票
    """
    print("正在從證交所獲取今日熱門成交量排行...")
    try:
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = res.json()
        
        dynamic_stocks = []
        for row in data.get("data", [])[:limit]:
            code = str(row[1]).strip()     # 確保是純字串去空格
            name = str(row[2]).strip()     # 確保是純字串去空格
            
            if len(code) == 4 and not code.startswith('00'):
                dynamic_stocks.append({
                    "code": f"{code}.TW",
                    "name": name,
                    "stock_id": code  
                })
        print(f"成功自動鎖定今日最熱門的 {len(dynamic_stocks)} 檔台股個股！")
        return dynamic_stocks
    except Exception as e:
        print(f"自動抓取熱門股失敗: {e}")
        return [{"code": "2303.TW", "name": "聯電", "stock_id": "2303"}]

def fetch_all_foreign():
    """
    完美防禦版：將證交所的所有代號與名稱徹底清洗
    """
    for i in range(5):
        target_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/TWT38U?date={target_date}&response=json"
        
        try:
            print(f"正在嘗試抓取日期 {target_date} 的外資資料...")
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = res.json()
            
            if data.get("stat") == "OK" and data.get("data"):
                raw_data = data.get("data", [])
                
                result_by_id = {}
                result_by_name = {}
                
                for row in raw_data:
                    if len(row) < 8: 
                        continue
                        
                    # ⚡ 核心清洗：強制轉字串、徹底削掉所有隱藏空格
                    code = str(row[1]).strip() 
                    name = str(row[2]).strip() 
                    
                    try:
                        net_shares = int(str(row[7]).replace(",", ""))
                        net_vols = net_shares // 1000 
                        
                        result_by_id[code] = net_vols
                        result_by_name[name] = net_vols
                    except Exception as e:
                        continue
                        
                print(f"🎉 成功抓到 {target_date} 的外資資料，共 {len(result_by_id)} 筆！")
                return {"id_map": result_by_id, "name_map": result_by_name}
            else:
                print(f"📅 日期 {target_date} 證交所尚未公告或無資料，嘗試前一天...")
        except Exception as e:
            print(f"抓取 {target_date} 資料時發生異常: {e}")
            
    return {"id_map": {}, "name_map": {}}

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

# ==================== 執行核心流程 ====================
STOCKS = fetch_top_volume_stocks(limit=60)
foreign_data = fetch_all_foreign()
results = []

id_map = foreign_data.get("id_map", {})
name_map = foreign_data.get("name_map", {})

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
        
        if vol_5avg < 500:
            continue

        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)

        # 🎯 終極暴力清洗配對邏輯
        foreign_buy = 0
        try:
            # 確保提取出來的比較基准絕對沒有任何前後空格
            pure_id = str(s.get("stock_id", s["code"].split('.')[0])).strip()
            stock_name = str(s["name"]).strip()
            
            # 1. 數位代號精準碰撞
            if pure_id in id_map:
                foreign_buy = id_map[pure_id]
            # 2. 股票名稱精準碰撞
            elif stock_name in name_map:
                foreign_buy = name_map[stock_name]
            # 3. 萬無一失的雙向模糊包含比對
            else:
                for k, v in name_map.items():
                    clean_k = str(k).strip()
                    if stock_name in clean_k or clean_k in stock_name:
                        foreign_buy = v
                        break
        except Exception as f_err:
            foreign_buy = 0

        # 📢 Log 明細監控：這一次絕對要看到正確張數印出來
        print(f"👉 最終匹配結果 - {s['name']}({pure_id}): {foreign_buy} 張")

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
    "updated": datetime.datetime.now().strftime("%Y/%m/%d %H:%M"),
    "stocks": results
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"優化完成，共 {len(results)} 檔熱門爆量股成功寫入！")
