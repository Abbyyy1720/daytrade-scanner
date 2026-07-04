import yfinance as yf
import pandas as pd
import json
import requests
import datetime
import time
import re
from bs4 import BeautifulSoup

INDUSTRY_MAP = {}  # code -> 產業別，由 fetch_stock_universe() 填入

# GitHub Actions 伺服器系統時間是 UTC，直接用 datetime.now() 會少8小時。
# 台灣不實施日光節約時間，用固定 +8 時區即可，不需要額外裝 tzdata。
TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))

def now_tw():
    return datetime.datetime.now(TAIPEI_TZ)

def is_finance(code):
    return INDUSTRY_MAP.get(code) == "金融保險業"

def is_dr(name):
    return 'DR' in name or '-DR' in name

def fetch_stock_universe():
    """動態抓取台股上市＋上櫃「全市場」普通股＋ETF清單，取代原本手動維護的90檔候選清單。
    資料源：證交所 ISIN 公告表（官方、免金鑰）
      上市：https://isin.twse.com.tw/isin/C_public.jsp?strMode=2
      上櫃：https://isin.twse.com.tw/isin/C_public.jsp?strMode=4
    CFICode 前兩碼判斷類別（ISO 10962 CFI 分類標準）：
      'ES' = 一般普通股（例如 ESVUFR、ESVTFR 等變體都算）
      'CE' = 集合投資工具／ETF（例如 0050、0056、006208 這類）
    藉此排除權證(RW開頭)、公司債、特別股等其他標的，且不用再靠猜代碼前綴。
    同時把「產業別」記錄下來，讓 is_finance() 用官方分類而不是猜代碼開頭
    （ETF沒有產業別，is_finance() 對ETF自然回傳False，不影響判斷）。
    """
    urls = {
        "twse": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "otc": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
    }
    universe = []
    industry_map = {}
    for market, url in urls.items():
        try:
            res = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            res.encoding = "big5"
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", {"class": "h4"}) or soup.find("table")
            if not table:
                print(f"{market} 清單抓取失敗：找不到表格")
                continue
            count = 0
            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) != 7:
                    continue  # 這是分類標題列（股票/ETF/權證...），跳過
                code_name = cells[0].get_text().strip()
                if "\u3000" not in code_name:
                    continue
                code, name = code_name.split("\u3000", 1)
                code, name = code.strip(), name.strip()
                # 代碼放寬到4~6位數字、可帶一個英文字母後綴（涵蓋 006208、00675L 這類ETF代碼）
                if not re.match(r"^\d{4,6}[A-Z]?$", code):
                    continue
                cfi = cells[5].get_text().strip()
                if not (cfi.startswith("ES") or cfi.startswith("CE")):
                    continue  # 只留一般普通股(ES)與ETF(CE)，排除權證(RW)、公司債等
                industry = cells[4].get_text().strip()
                universe.append((code, name, market))
                industry_map[code] = industry
                count += 1
            print(f"{market} 普通股+ETF清單：{count} 檔")
        except Exception as e:
            print(f"{market} 清單抓取失敗: {e}")
    return universe, industry_map

def fetch_twse_foreign():
    """上市（TWSE）三大法人外資買賣超。
    關鍵：T86 這支 API 一定要帶 selectType 參數，否則永遠回傳空資料。
    這是原本版本一直抓不到外資資料的根本原因。
    """
    for i in range(5):
        target_date = (now_tw() - datetime.timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={target_date}&selectType=ALL&response=json"
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
                        # 「外陸資買賣超股數(不含外資自營商)」欄位
                        net = int(str(row[4]).replace(",", "").replace("+", ""))
                        id_map[code] = net // 1000
                        name_map[name] = net // 1000
                    except:
                        continue
                print(f"上市外資 {target_date}：{len(id_map)} 筆")
                return {"id_map": id_map, "name_map": name_map}
            else:
                print(f"上市外資 {target_date} 無資料（可能非交易日）")
        except Exception as e:
            print(f"上市外資失敗: {e}")
    return {"id_map": {}, "name_map": {}}

def fetch_tpex_foreign():
    """上櫃（TPEx）三大法人外資買賣超。
    原本的程式完全沒有抓上櫃法人資料，導致上櫃股票的外資分數永遠是「待確認」。
    資料源（data.gov.tw 開放資料集 11856）：
    https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php
    """
    for i in range(5):
        d = now_tw() - datetime.timedelta(days=i)
        roc_date = f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
        url = (
            "https://www.tpex.org.tw/web/stock/3insti/daily_trade/"
            f"3itrade_hedge_result.php?l=zh-tw&se=EW&t=D&d={roc_date}&o=json"
        )
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = res.json()
            rows = data.get("aaData")
            if not rows:
                print(f"上櫃外資 {roc_date} 無資料（可能非交易日）")
                continue
            id_map, name_map = {}, {}
            for row in rows:
                if len(row) < 5:
                    continue
                code = str(row[0]).strip()
                name = str(row[1]).strip()
                try:
                    # 「外資及陸資買賣超股數」欄位，位置隨櫃買中心格式可能微調，
                    # 若比對後發現偏移，請用 print(rows[0]) 對照欄位順序調整 idx
                    net = int(str(row[4]).replace(",", "").replace("+", ""))
                    id_map[code] = net // 1000
                    name_map[name] = net // 1000
                except:
                    continue
            print(f"上櫃外資 {roc_date}：{len(id_map)} 筆")
            return {"id_map": id_map, "name_map": name_map}
        except Exception as e:
            print(f"上櫃外資失敗: {e}")
    return {"id_map": {}, "name_map": {}}

def match_foreign(stock_id, stock_name, market, twse_foreign, tpex_foreign):
    foreign = tpex_foreign if market == "otc" else twse_foreign
    id_map = foreign.get("id_map", {})
    name_map = foreign.get("name_map", {})
    if stock_id in id_map:
        return id_map[stock_id], True
    if stock_name in name_map:
        return name_map[stock_name], True
    # 名稱模糊比對僅在雙方名稱都至少2字時才採用，降低誤配風險
    for k, v in name_map.items():
        if len(k) >= 2 and len(stock_name) >= 2 and (stock_name in k or k in stock_name):
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
    """回傳今日 VR 值，以及相對於昨日 VR 的趨勢方向（up/down/flat）。"""
    price_change = close.diff()
    up_vol = volume.where(price_change > 0, 0).rolling(period).sum()
    dn_vol = volume.where(price_change < 0, 0).rolling(period).sum()
    dn_vol = dn_vol.replace(0, 1)
    vr_series = (up_vol / dn_vol * 100)

    vr_today = vr_series.iloc[-1]
    vr_today = round(vr_today, 1) if not pd.isna(vr_today) else 100.0

    vr_trend = "flat"
    if len(vr_series) >= 2:
        vr_yesterday = vr_series.iloc[-2]
        if not pd.isna(vr_yesterday):
            diff = vr_today - round(vr_yesterday, 1)
            if diff > 0.5:
                vr_trend = "up"
            elif diff < -0.5:
                vr_trend = "down"

    return vr_today, vr_trend

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

def generate_reason(kd_status, kd_k, kd_d, vol_ratio, atr_pct, foreign_buy, foreign_found):
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

def fetch_batch_history(ticker_map, chunk_size=100, period="60d"):
    """分批＋多執行緒下載歷史股價，取代逐檔 yf.Ticker().history() 的做法。
    全市場約1700+檔，如果逐一呼叫會很慢，且容易被 Yahoo Finance 判定異常流量。
    這裡改用 yf.download() 一次帶入一批 ticker，批次之間間隔一下降低風險。
    注意：Yahoo Finance 對雲端機房 IP（含 GitHub Actions）較常見限流/封鎖，
    若正式跑起來發現大量失敗，請告知我，我們再評估要不要換官方資料源。
    """
    all_tickers = list(ticker_map.keys())
    hist_map = {}
    total = len(all_tickers)
    for i in range(0, total, chunk_size):
        chunk = all_tickers[i:i + chunk_size]
        try:
            df = yf.download(
                tickers=chunk, period=period, group_by="ticker",
                threads=True, progress=False, auto_adjust=False
            )
        except Exception as e:
            print(f"批次下載失敗（第 {i}-{i+len(chunk)} 檔）: {e}")
            continue

        for t in chunk:
            try:
                if len(chunk) == 1:
                    sub = df
                elif t in df.columns.get_level_values(0):
                    sub = df[t]
                else:
                    continue
                sub = sub.dropna(how="all")
                if len(sub) >= 20:
                    hist_map[t] = sub
            except Exception:
                continue

        print(f"歷史股價下載進度：{min(i + chunk_size, total)}/{total}")
        time.sleep(1.5)  # 批次間停頓，降低被限流風險

    return hist_map

# ==================== 主流程 ====================
STOCK_LIST, INDUSTRY_MAP = fetch_stock_universe()
print(f"候選清單共 {len(STOCK_LIST)} 檔（上市＋上櫃全市場普通股），開始抓取...")

ticker_map = {}  # yfinance代號 -> (code, name, market)
for (stock_id, name, market) in STOCK_LIST:
    if is_dr(name):
        continue
    suffix = ".TW" if market == "twse" else ".TWO"
    ticker_map[f"{stock_id}{suffix}"] = (stock_id, name, market)

hist_data = fetch_batch_history(ticker_map, chunk_size=100)
print(f"成功取得歷史價量資料：{len(hist_data)}/{len(ticker_map)} 檔")

twse_foreign = fetch_twse_foreign()
tpex_foreign = fetch_tpex_foreign()
results = []

for ticker, (stock_id, name, market) in ticker_map.items():
    try:
        hist = hist_data.get(ticker)
        if hist is None or hist.empty or len(hist) < 20:
            continue

        price = round(hist["Close"].iloc[-1], 1)
        vol_today = int(hist["Volume"].iloc[-1] / 1000)
        vol_5avg = int(hist["Volume"].tail(5).mean() / 1000)

        # 注意：這裡不再過濾低量股，全部股頁籤需要顯示全市場，
        # 交易量高低改由前端篩選器處理，不在後端就砍掉資料

        vol_ratio = round(vol_today / vol_5avg, 2) if vol_5avg > 0 else 1
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"])
        vr, vr_trend = calc_vr(hist["Close"], hist["Volume"])
        kd_k, kd_d = calc_kd(hist["High"], hist["Low"], hist["Close"])
        vol5 = [int(v/1000) for v in hist["Volume"].tail(5).tolist()]
        chg = round((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 1)
        atr_pct = round(atr / price * 100, 1) if price > 0 else 0

        foreign_buy, foreign_found = match_foreign(stock_id, name, market, twse_foreign, tpex_foreign)

        if kd_k > kd_d + 3:
            kd_status, kd_label = "up", "K>D 向上"
        elif kd_k > kd_d:
            kd_status, kd_label = "cross", "K 剛交叉 D"
        else:
            kd_status, kd_label = "dn", "K<D 偏弱"

        score = calc_score(vol_ratio, atr, price, foreign_buy, vr, kd_status, kd_k, kd_d)
        reason = generate_reason(kd_status, kd_k, kd_d, vol_ratio, atr_pct, foreign_buy, foreign_found)

        # 股價分類
        if price <= 100:
            price_range = "0-100"
        elif price <= 300:
            price_range = "100-300"
        else:
            price_range = "300+"

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

        print(f"{name}({stock_id}) 價={price} [{price_range}] 均量={vol_5avg} 外資={foreign_buy}{'✓' if foreign_found else '?'} 分={score}")

        results.append({
            "code": stock_id,
            "name": name,
            "market": market,
            "price": price,
            "priceRange": price_range,
            "chg": f"+{chg}%" if chg >= 0 else f"{chg}%",
            "vol": vol_today,
            "avgVol": vol_5avg,
            "atr": atr,
            "atrPct": atr_pct,
            "vr": vr,
            "vrTrend": vr_trend,
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
    "updated": now_tw().strftime("%Y/%m/%d %H:%M"),
    "stocks": results
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n完成，共 {len(results)} 檔寫入 data.json")
