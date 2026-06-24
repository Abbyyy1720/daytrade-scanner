import yfinance as yf
import pandas as pd
import json
import requests
import datetime

FINANCE_CODES = {'27', '28', '29', '25'}

def fetch_top_volume_stocks(limit=100):
    print("正在從證交所獲取今日熱門成交量排行...")
    try:
        # 用成交量排行（取前100名）
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = res.json()
        dynamic_stocks = []
        for row in data.get("data", [])[:limit]:
            code = str(row[1]).strip()
            name = str(row[2]).strip()
            if len(code) == 4 and code.isdigit():
                dynamic_stocks.append({
                    "code": f"{code}.TW",
                    "name": name,
                    "stock_id": code
                })
        print(f"從MI_INDEX20 抓到 {len(dynamic_stocks)} 檔")

        # 補充抓每日收盤行情的所有股票（量大的）
        url2 = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
        res2 = requests.get(url2, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data2 = res2.json()
        existing_codes = {s["stock_id"] for s in dynamic_stocks}
        extra = []
        for row in data2.get("data", []):
            if len(row) < 9:
                continue
            code = str(row[0]).strip()
            name = str(row[1]).strip()
            if len(code) == 4 and code.isdigit() and code not in existing_codes:
                try:
                    vol = int(str(row[2]).replace(",", ""))
                    if vol > 5000000:  # 成交量超過500萬股（約5000張）才納入
                        extra.append({
                            "code": f"{code}.TW",
                            "name": name,
                            "stock_id": code
                        })
                        existing_codes.add(code)
                except:
                    continue
        dynamic_stocks.extend(extra)
        print(f"合計鎖定 {len(dynamic_stocks)} 檔候選個股")
        return dynamic_stocks
    except Exception as e:
        print(f"自動抓取熱門股失敗: {e}")
        return [
            {"code": "2303.TW", "name": "聯電", "stock_id": "2303"},
            {"code": "2317.TW", "name": "鴻海", "stock_id": "2317"},
            {"code": "2409.TW", "name": "友達", "stock_id": "2409"},
        ]

def fetch_all_foreign():
    for i in range(5):
        target_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={target_date}&response=json"
        try:
            print(f"正在抓取 {target_date} 個股外資資料...")
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = res.json()
            if data.get("stat") == "OK" and data.get("data"):
                result_by_id = {}
                result_by_name = {}
                for row in data.get("data", []):
                    if len(row) < 8:
                        continue
                    code = str(row[0]).strip()
                    name = str(row[1]).strip()
                    try:
                        # row[4] 是外資買超股數（股），除以1000換算成張
                        net_str = str(row[4]).replace(",", "").replace("+", "").strip()
                        net_shares = int(net_str)
                        net_lots = net_shares // 1000
                        result_by_id[code] = net_lots
                        result_by_name[name] = net_lots
                    except:
                        continue
                print(f"成功抓到 {target_date} 外資資料，共 {len(result_by_id)} 筆")
                # 印出前5筆確認格式正確
                for k, v in list(result_by_id.items())[:5]:
                    print(f"  範例: {k} = {v} 張")
                return {"id_map": result_by_id, "name_map": result_by_name}
            else:
                print(f"日期 {target_date} 無資料，嘗試前一天...")
        except Exception as e:
            print(f"抓取失敗: {e}")
    return {"id_map": {}, "name_map": {}}

def calc_kd(high, low, close, period=9):
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    denom = highest_high - lowest_low
    denom = denom.replace(0, 1)
    rsv = (close - lowest_low) / denom * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    return round(k.iloc[-1], 1), round(d.iloc[-1], 1)

def calc_vr(close, volume, period=26):
    price_change = close.diff()
    up_vol = volume.where(price_change > 0, 0).rolling(period).sum()
    dn_vol = volume.where(price_change < 0, 0).rolling(period).sum()
    dn_vol = dn_vol.replace(0, 1)
    vr = (up_vol / dn_vol * 100).iloc[-1]
    return round(vr, 1) if not pd.isna(vr) else 100.0

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return round(val, 1) if not pd.isna(val) else 0.0

def calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status):
    vol_score = min(vol_ratio / 2, 1) * 100
    atr_percent = (atr / price) * 100 if price > 0 else 0
    atr_score = min(atr_percent / 3.5, 1) * 100
    foreign_score = 100 if foreign_buy > 3000 else 75 if foreign_buy > 1000 else 50 if foreign_buy > 0 else 20
    vr_score = 100 if vr > 130 else 70 if vr > 100 else 40 if vr > 80 else 20
    kd_score = 100 if kd_status == "up" else 70 if kd_status == "cross" else 20
    total = vol_score*0.30 + atr_score*0.25 + foreign_score*0.20 + vr_score*0.15 + kd_score*0.10
    return round(total)

def is_finance(code):
    prefix = code[:2]
    return prefix in FINANCE_CODES

# ==================== 主流程 ====================
STOCKS = fetch_top_volume_stocks(limit=100)
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

        # 後端只過濾最低門檻500張，讓前端做動態篩選
        if vol_5avg < 500:
            continue

        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)

        # 外資配對：先用代號，再用名稱
        pure_id = s["stock_id"]
        stock_name = s["name"]
        foreign_buy = 0

        if pure_id in id_map:
            foreign_buy = id_map[pure_id]
        elif stock_name in name_map:
            foreign_buy = name_map[stock_name]
        else:
            for k, v in name_map.items():
                if stock_name in k or k in stock_name:
                    foreign_buy = v
                    break

        print(f"{s['name']}({pure_id}): 外資={foreign_buy}張 價={price} 均量={vol_5avg}")

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

        # 標籤邏輯
        tags = []
        if vol_ratio > 1.3: tags.append("量能放大")
        if kd_status == "up": tags.append("KD 向上")
        if kd_status == "cross": tags.append("KD 交叉")
        if foreign_buy > 1000: tags.append("外資大買")
        elif foreign_buy > 0: tags.append("外資買超")
        elif foreign_buy < 0: tags.append("外資賣超")
        if vr > 130: tags.append("VR 強勢")
        if is_finance(pure_id): tags.append("金融股")
        tags.append("可當沖")

        results.append({
            "code": pure_id,
            "name": stock_name,
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
            "badge": "hot" if score >= 70 else "watch",
            "badgeLabel": "熱門" if score >= 70 else "觀察",
            "isFinance": is_finance(pure_id),
            "tags": tags,
            "reason": ""
        })

    except Exception as e:
        print(f"Error {s['code']}: {e}")

results.sort(key=lambda x: x["score"], reverse=True)

output = {
    "updated": datetime.datetime.now().strftime("%Y/%m/%d %H:%M"),
    "stocks": results
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n完成，共 {len(results)} 檔寫入 data.json")
