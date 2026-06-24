import yfinance as yf
import pandas as pd
import json
import requests
import datetime

FINANCE_CODES = {'27', '28', '29', '25'}

def is_finance(code):
    return code[:2] in FINANCE_CODES

def fetch_top_volume_stocks():
    stocks = {}

    # 1. 上市：證交所成交量排行
    try:
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = res.json()
        for row in data.get("data", []):
            code = str(row[1]).strip()
            name = str(row[2]).strip()
            if len(code) == 4 and code.isdigit():
                stocks[code] = {"code": f"{code}.TW", "name": name, "stock_id": code, "market": "twse"}
        print(f"證交所排行：{len(stocks)} 檔")
    except Exception as e:
        print(f"證交所排行失敗: {e}")

    # 2. 上市：全市場量大補充
    try:
        url2 = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
        res2 = requests.get(url2, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data2 = res2.json()
        added = 0
        for row in data2.get("data", []):
            if len(row) < 9:
                continue
            code = str(row[0]).strip()
            name = str(row[1]).strip()
            if len(code) == 4 and code.isdigit() and code not in stocks:
                try:
                    vol = int(str(row[2]).replace(",", ""))
                    if vol > 3000000:
                        stocks[code] = {"code": f"{code}.TW", "name": name, "stock_id": code, "market": "twse"}
                        added += 1
                except:
                    continue
        print(f"證交所補充：+{added} 檔")
    except Exception as e:
        print(f"證交所補充失敗: {e}")

    # 3. 上櫃：櫃買排行
    try:
        url3 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_index/st41_result.php?l=zh-tw&o=json"
        res3 = requests.get(url3, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data3 = res3.json()
        otc_added = 0
        for row in data3.get("aaData", []):
            if len(row) < 3:
                continue
            code = str(row[0]).strip()
            name = str(row[1]).strip()
            if len(code) == 4 and code.isdigit() and code not in stocks:
                stocks[code] = {"code": f"{code}.TWO", "name": name, "stock_id": code, "market": "otc"}
                otc_added += 1
        print(f"櫃買補充：+{otc_added} 檔")
    except Exception as e:
        print(f"櫃買失敗: {e}")

    result = list(stocks.values())
    print(f"合計候選：{len(result)} 檔")
    return result


def fetch_twse_foreign():
    for i in range(5):
        target_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={target_date}&response=json"
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = res.json()
            if data.get("stat") == "OK" and data.get("data"):
                id_map, name_map = {}, {}
                for row in data.get("data", []):
                    if len(row) < 8:
                        continue
                    code = str(row[0]).strip()
                    name = str(row[1]).strip()
                    try:
                        net = int(str(row[4]).replace(",", "").replace("+", ""))
                        id_map[code] = net // 1000
                        name_map[name] = net // 1000
                    except:
                        continue
                print(f"上市外資 {target_date}：{len(id_map)} 筆")
                return {"id_map": id_map, "name_map": name_map}
            else:
                print(f"上市外資 {target_date} 無資料")
        except Exception as e:
            print(f"上市外資失敗: {e}")
    return {"id_map": {}, "name_map": {}}


def fetch_otc_foreign():
    for i in range(5):
        dt = datetime.datetime.now() - datetime.timedelta(days=i)
        roc_date = f"{dt.year - 1911}/{dt.strftime('%m/%d')}"
        url = f"https://www.tpex.org.tw/web/stock/3insti/foreign_invest/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D&d={roc_date}"
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = res.json()
            rows = data.get("aaData", [])
            if rows:
                id_map, name_map = {}, {}
                for row in rows:
                    if len(row) < 6:
                        continue
                    code = str(row[0]).strip()
                    name = str(row[1]).strip()
                    try:
                        net = int(str(row[4]).replace(",", "").replace("+", "").strip())
                        id_map[code] = net
                        name_map[name] = net
                    except:
                        continue
                print(f"上櫃外資 {roc_date}：{len(id_map)} 筆")
                return {"id_map": id_map, "name_map": name_map}
            else:
                print(f"上櫃外資 {roc_date} 無資料")
        except Exception as e:
            print(f"上櫃外資失敗: {e}")
    return {"id_map": {}, "name_map": {}}


def match_foreign(stock_id, stock_name, foreign):
    id_map = foreign.get("id_map", {})
    name_map = foreign.get("name_map", {})
    if stock_id in id_map:
        return id_map[stock_id], True
    if stock_name in name_map:
        return name_map[stock_name], True
    for k, v in name_map.items():
        if stock_name in k or k in stock_name:
            return v, True
    return 0, False


def calc_kd(high, low, close, period=9):
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    denom = (highest_high - lowest_low).replace(0, 1)
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

def calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status, kd_k, kd_d):
    """
    改成連續分佈評分，不再輕易給滿分
    """
    # 量能比：1.0以下很差，2.0以上才接近滿分
    vol_score = min(max((vol_ratio - 0.5) / 1.5, 0), 1) * 100

    # ATR波動率：以股價百分比計算，5%以上才接近滿分
    atr_pct = (atr / price * 100) if price > 0 else 0
    atr_score = min(max(atr_pct / 5.0, 0), 1) * 100

    # 外資：連續分佈，-5000到+5000之間線性換算
    foreign_score = min(max((foreign_buy + 5000) / 10000, 0), 1) * 100

    # VR：100以下很差，300以上才滿分
    vr_score = min(max((vr - 60) / 240, 0), 1) * 100

    # KD：考慮K值位置和K-D差距，不只看方向
    if kd_status == "up":
        kd_gap = min((kd_k - kd_d) / 20, 1)  # K比D高越多越好，但最高20分差就滿
        kd_score = 60 + kd_gap * 40            # 60~100分
    elif kd_status == "cross":
        kd_score = 55
    else:
        kd_score = max(20, 50 - (kd_d - kd_k) * 2)  # K比D低越多分越低

    total = vol_score*0.30 + atr_score*0.25 + foreign_score*0.20 + vr_score*0.15 + kd_score*0.10
    return round(total)

def generate_reason(s, vol_ratio, atr_pct, foreign_buy, foreign_found):
    """根據各指標數值產生文字說明"""
    points = []

    # 量能
    if vol_ratio >= 2.0:
        points.append(f"成交量為均量 {vol_ratio:.1f} 倍，爆量明顯，市場高度關注")
    elif vol_ratio >= 1.3:
        points.append(f"成交量為均量 {vol_ratio:.1f} 倍，量能放大中")
    else:
        points.append(f"量能持平，成交量與均量相近")

    # KD
    if s["kdStatus"] == "up":
        points.append(f"KD 向上（K={s['kdK']} D={s['kdD']}），短線動能偏多")
    elif s["kdStatus"] == "cross":
        points.append(f"KD 剛完成黃金交叉（K={s['kdK']} D={s['kdD']}），留意後續確認")
    else:
        points.append(f"KD 偏弱（K={s['kdK']} D={s['kdD']}），需觀察是否止跌")

    # 外資
    if not foreign_found:
        points.append("外資資料待確認（可能為上櫃或資料延遲）")
    elif foreign_buy > 3000:
        points.append(f"外資大幅買超 {foreign_buy:,} 張，籌碼面正向")
    elif foreign_buy > 0:
        points.append(f"外資買超 {foreign_buy:,} 張，小幅偏多")
    elif foreign_buy < -1000:
        points.append(f"外資賣超 {abs(foreign_buy):,} 張，籌碼面偏空，需謹慎")
    else:
        points.append("外資近乎中性")

    # ATR
    if atr_pct >= 4:
        points.append(f"ATR 波動率 {atr_pct:.1f}%，日內價差空間充足，適合當沖")
    elif atr_pct >= 2:
        points.append(f"ATR 波動率 {atr_pct:.1f}%，波動中等")
    else:
        points.append(f"ATR 波動率僅 {atr_pct:.1f}%，波動偏小，當沖空間有限")

    return "。".join(points) + "。"


# ==================== 主流程 ====================
STOCKS = fetch_top_volume_stocks()
twse_foreign = fetch_twse_foreign()
otc_foreign = fetch_otc_foreign()
results = []

for s in STOCKS:
    try:
        ticker = yf.Ticker(s["code"])
        hist = ticker.history(period="60d")
        if hist.empty or len(hist) < 20:
            continue

        price = round(hist["Close"].iloc[-1], 1)

        # ★ 股價上限 100 元
        if price > 100:
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
        atr_pct = round(atr / price * 100, 1) if price > 0 else 0

        foreign = twse_foreign if s["market"] == "twse" else otc_foreign
        foreign_buy, foreign_found = match_foreign(s["stock_id"], s["name"], foreign)

        if kd_k > kd_d + 3:
            kd_status, kd_label = "up", "K>D 向上"
        elif kd_k > kd_d:
            kd_status, kd_label = "cross", "K 剛交叉 D"
        else:
            kd_status, kd_label = "dn", "K<D 偏弱"

        stock_data = {
            "kdStatus": kd_status, "kdK": kd_k, "kdD": kd_d
        }
        score = calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status, kd_k, kd_d)
        reason = generate_reason(stock_data, vol_ratio, atr_pct, foreign_buy, foreign_found)

        tags = []
        if vol_ratio > 1.3: tags.append("量能放大")
        if kd_status == "up": tags.append("KD 向上")
        if kd_status == "cross": tags.append("KD 交叉")
        if foreign_buy > 1000: tags.append("外資大買")
        elif foreign_buy > 0: tags.append("外資買超")
        elif foreign_buy < 0: tags.append("外資賣超")
        if vr > 150: tags.append("VR 強勢")
        if is_finance(s["stock_id"]): tags.append("金融股")
        if s["market"] == "otc": tags.append("上櫃")
        tags.append("可當沖")

        print(f"{s['name']}({s['stock_id']}) [{s['market']}]: 價={price} 均量={vol_5avg} 外資={foreign_buy}{'✓' if foreign_found else '?'} 分={score}")

        results.append({
            "code": s["stock_id"],
            "name": s["name"],
            "market": s["market"],
            "price": price,
            "chg": f"+{chg}%" if chg >= 0 else f"{chg}%",
            "vol": vol_today,
            "avgVol": vol_5avg,
            "atr": atr,
            "atrPct": atr_pct,
            "vr": vr,
            "kdK": kd_k,
            "kdD": kd_d,
            "kdStatus": kd_status,
            "kdLabel": kd_label,
            "foreignBuy": foreign_buy,
            "foreignFound": foreign_found,
            "vol5": vol5,
            "score": score,
            "badge": "hot" if score >= 65 else "watch",
            "badgeLabel": "熱門" if score >= 65 else "觀察",
            "isFinance": is_finance(s["stock_id"]),
            "tags": tags,
            "reason": reason
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
