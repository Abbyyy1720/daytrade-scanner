import yfinance as yf
import pandas as pd
import json
import requests
import datetime

FINANCE_CODES = {'27', '28', '29', '25'}

def is_finance(code):
    return code[:2] in FINANCE_CODES

def is_dr(name):
    return 'DR' in name or 'dr' in name

# 內建台股候選清單（上市+上櫃，100元以下常見活絡股）
# 每季可手動更新一次，加入新熱門股
STOCK_LIST = [
    # 半導體/電子
    ("2303", "聯電", "twse"), ("2317", "鴻海", "twse"), ("2409", "友達", "twse"),
    ("3481", "群創", "twse"), ("6770", "力積電", "twse"), ("2337", "旺宏", "twse"),
    ("6116", "彩晶", "twse"), ("1802", "台玻", "twse"), ("2610", "華航", "twse"),
    ("2618", "長榮航", "twse"), ("2603", "長榮", "twse"), ("2615", "萬海", "twse"),
    ("2609", "陽明", "twse"), ("5880", "合庫金", "twse"), ("2884", "玉山金", "twse"),
    ("2885", "元大金", "twse"), ("2886", "兆豐金", "twse"), ("2887", "台新金", "twse"),
    ("2888", "新光金", "twse"), ("2890", "永豐金", "twse"), ("2891", "中信金", "twse"),
    ("2892", "第一金", "twse"), ("2882", "國泰金", "twse"), ("2883", "開發金", "twse"),
    ("1301", "台塑", "twse"), ("1303", "南亞", "twse"), ("1326", "台化", "twse"),
    ("2002", "中鋼", "twse"), ("2006", "東和鋼鐵", "twse"), ("2008", "高興昌", "twse"),
    ("2049", "上銀", "twse"), ("2201", "裕隆", "twse"), ("2207", "和泰車", "twse"),
    ("2227", "裕日車", "twse"), ("2356", "英業達", "twse"), ("2376", "技嘉", "twse"),
    ("2379", "瑞昱", "twse"), ("2383", "台光電", "twse"), ("2385", "群光", "twse"),
    ("2392", "正崴", "twse"), ("2395", "研華", "twse"), ("2408", "南亞科", "twse"),
    ("2449", "京元電子", "twse"), ("2460", "建邦", "twse"), ("2475", "華映", "twse"),
    ("2492", "華新", "twse"), ("2504", "國產", "twse"), ("2511", "太子", "twse"),
    ("2542", "興富發", "twse"), ("2545", "皇翔", "twse"), ("2547", "日勝生", "twse"),
    ("2548", "華固", "twse"), ("2601", "益航", "twse"), ("2605", "新興", "twse"),
    ("2606", "裕民", "twse"), ("2607", "榮運", "twse"), ("2608", "嘉里大榮", "twse"),
    ("2611", "志信", "twse"), ("2614", "東森", "twse"), ("2616", "山隆", "twse"),
    ("2619", "中航", "twse"), ("2630", "亞航", "twse"), ("2634", "漢翔", "twse"),
    ("2640", "大車隊", "twse"), ("2707", "晶華", "twse"), ("2712", "遠雄來", "twse"),
    ("2723", "美食達人", "twse"), ("2727", "王品", "twse"), ("2731", "雄獅", "twse"),
    ("2801", "彰銀", "twse"), ("2809", "京城銀", "twse"), ("2812", "台中銀", "twse"),
    ("2834", "臺企銀", "twse"), ("2836", "聯邦銀", "twse"), ("2838", "聯邦銀", "twse"),
    ("2845", "遠東銀", "twse"), ("2847", "大眾銀", "twse"), ("2849", "安泰銀", "twse"),
    ("2850", "新產", "twse"), ("2851", "中再保", "twse"), ("2852", "第一保", "twse"),
    ("2855", "統一證", "twse"), ("2856", "元富證", "twse"), ("2867", "三商壽", "twse"),
    ("2880", "華南金", "twse"), ("2881", "富邦金", "twse"),
    ("3008", "大立光", "twse"), ("3034", "聯詠", "twse"), ("3037", "欣興", "twse"),
    ("3045", "台灣大", "twse"), ("3047", "訊舟", "twse"), ("3049", "和鑫", "twse"),
    ("3189", "景碩", "twse"), ("3231", "緯創", "twse"), ("3443", "創意", "twse"),
    ("3474", "華亞科", "twse"), ("3576", "新日興", "twse"), ("3583", "辛耘", "twse"),
    ("3607", "谷崧", "twse"), ("3653", "健策", "twse"), ("3673", "TPK", "twse"),
    ("3711", "日月光投控", "twse"), ("4904", "遠傳", "twse"), ("4938", "和碩", "twse"),
    ("4958", "臻鼎-KY", "twse"), ("5483", "中美晶", "twse"), ("5871", "中租-KY", "twse"),
    ("6239", "力成", "twse"), ("6285", "啟碁", "twse"), ("6409", "旭隼", "twse"),
    ("6415", "矽力-KY", "twse"), ("6456", "GIS-KY", "twse"), ("6505", "台塑化", "twse"),
    ("6547", "高端疫苗", "twse"), ("6669", "緯穎", "twse"), ("8046", "南電", "twse"),
    # 上櫃熱門股
    ("3591", "艾笛森", "otc"), ("6274", "台燿", "otc"), ("5347", "世界", "otc"),
    ("3通", "通泰", "otc"), ("6756", "威鋒電子", "otc"), ("3714", "富采", "otc"),
    ("8044", "網家", "otc"), ("6488", "環球晶", "otc"), ("3702", "大聯大", "otc"),
    ("5264", "鎧勝-KY", "otc"), ("6271", "同欣電", "otc"), ("3260", "威剛", "otc"),
    ("3167", "奕劭", "otc"), ("6278", "台表科", "otc"), ("3533", "嘉澤", "otc"),
    ("6515", "穎崴", "otc"), ("3017", "奇鋐", "otc"), ("6598", "ABC-KY", "otc"),
    ("3055", "蘋果", "otc"), ("8454", "富邦媒", "otc"),
]

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
    vol_score = min(max((vol_ratio - 0.5) / 1.5, 0), 1) * 100
    atr_pct = (atr / price * 100) if price > 0 else 0
    atr_score = min(max(atr_pct / 5.0, 0), 1) * 100
    foreign_score = min(max((foreign_buy + 5000) / 10000, 0), 1) * 100
    vr_score = min(max((vr - 60) / 240, 0), 1) * 100
    if kd_status == "up":
        kd_score = 60 + min((kd_k - kd_d) / 20, 1) * 40
    elif kd_status == "cross":
        kd_score = 55
    else:
        kd_score = max(20, 50 - (kd_d - kd_k) * 2)
    return round(vol_score*0.30 + atr_score*0.25 + foreign_score*0.20 + vr_score*0.15 + kd_score*0.10)

def generate_reason(kd_status, kd_k, kd_d, vol_ratio, atr_pct, foreign_buy, foreign_found, vr):
    points = []
    if vol_ratio >= 2.0:
        points.append(f"成交量為均量 {vol_ratio:.1f} 倍，爆量明顯")
    elif vol_ratio >= 1.3:
        points.append(f"成交量為均量 {vol_ratio:.1f} 倍，量能放大中")
    else:
        points.append("量能持平，與均量相近")

    if kd_status == "up":
        points.append(f"KD 向上（K={kd_k} D={kd_d}），短線動能偏多")
    elif kd_status == "cross":
        points.append(f"KD 剛完成黃金交叉（K={kd_k} D={kd_d}），留意後續確認")
    else:
        points.append(f"KD 偏弱（K={kd_k} D={kd_d}），需觀察是否止跌")

    if not foreign_found:
        points.append("外資資料待確認")
    elif foreign_buy > 3000:
        points.append(f"外資大買 {foreign_buy:,} 張，籌碼正向")
    elif foreign_buy > 0:
        points.append(f"外資買超 {foreign_buy:,} 張，小幅偏多")
    elif foreign_buy < -1000:
        points.append(f"外資賣超 {abs(foreign_buy):,} 張，籌碼偏空需謹慎")
    else:
        points.append("外資近乎中性")

    if atr_pct >= 4:
        points.append(f"波動率 {atr_pct:.1f}%，日內價差空間充足，適合當沖")
    elif atr_pct >= 2:
        points.append(f"波動率 {atr_pct:.1f}%，波動中等")
    else:
        points.append(f"波動率僅 {atr_pct:.1f}%，波動偏小，當沖空間有限")

    return "。".join(points) + "。"


# ==================== 主流程 ====================
print(f"候選清單共 {len(STOCK_LIST)} 檔，開始抓取...")
twse_foreign = fetch_twse_foreign()
results = []

for (stock_id, name, market) in STOCK_LIST:
    try:
        suffix = ".TW" if market == "twse" else ".TWO"
        ticker = yf.Ticker(f"{stock_id}{suffix}")
        hist = ticker.history(period="60d")
        if hist.empty or len(hist) < 20:
            continue

        price = round(hist["Close"].iloc[-1], 1)
        if price > 100:
            continue

        vol_today = int(hist["Volume"].iloc[-1] / 1000)
        vol_5avg = int(hist["Volume"].tail(5).mean() / 1000)
        if vol_5avg < 500:
            continue

        vol_ratio = round(vol_today / vol_5avg, 2) if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)
        atr_pct = round(atr / price * 100, 1) if price > 0 else 0

        # DR股跳過
        if is_dr(name):
            continue

        foreign_buy, foreign_found = match_foreign(stock_id, name, twse_foreign)

        if kd_k > kd_d + 3:
            kd_status, kd_label = "up", "K>D 向上"
        elif kd_k > kd_d:
            kd_status, kd_label = "cross", "K 剛交叉 D"
        else:
            kd_status, kd_label = "dn", "K<D 偏弱"

        score = calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status, kd_k, kd_d)
        reason = generate_reason(kd_status, kd_k, kd_d, vol_ratio, atr_pct, foreign_buy, foreign_found, vr)

        tags = []
        if vol_ratio > 1.3: tags.append("量能放大")
        if kd_status == "up": tags.append("KD 向上")
        if kd_status == "cross": tags.append("KD 交叉")
        if foreign_buy > 1000: tags.append("外資大買")
        elif foreign_buy > 0: tags.append("外資買超")
        elif foreign_buy < 0: tags.append("外資賣超")
        if vr > 150: tags.append("VR 強勢")
        if is_finance(stock_id): tags.append("金融股")
        if market == "otc": tags.append("上櫃")
        tags.append("可當沖")

        print(f"{name}({stock_id}) 價={price} 均量={vol_5avg} 外資={foreign_buy}{'✓' if foreign_found else '?'} 分={score}")

        results.append({
            "code": stock_id,
            "name": name,
            "market": market,
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
            "isFinance": is_finance(stock_id),
            "tags": tags,
            "reason": reason
        })

    except Exception as e:
        print(f"Error {stock_id}: {e}")

results.sort(key=lambda x: x["score"], reverse=True)

output = {
    "updated": datetime.datetime.now().strftime("%Y/%m/%d %H:%M"),
    "stocks": results
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n完成，共 {len(results)} 檔寫入 data.json")
