"""
Inflection Point Tracker — Monitor v5.1
- 4개 테마 × 10종목 (미국 5 + 한국 5) = 40종목 전체 수집
- Yahoo Finance 서버 측 수집 (CORS 없음, 안정적)
- RSI(14) 직접 계산 (종가 데이터 기반)
- PER · 선행PER · EPS · 목표주가 · 기관지분 수집
- Finnhub EPS 서프라이즈 (선택적)
- DART OpenAPI 한국 재무데이터 (선택적)
- 번스타인 사이클 신호 변화 감지 → Telegram 알림
- data/signals.json 저장 → Vercel 대시보드 자동 반영
"""

import os, json, time, datetime, math, requests, shutil
from pathlib import Path

# ── 환경변수 ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
FINNHUB_KEY        = os.environ.get("FINNHUB_KEY", "")
DART_KEY           = os.environ.get("DART_KEY", "")

DATA_FILE = Path("data/signals.json")
PREV_FILE = Path("data/signals_prev.json")
HEADERS   = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ── 전체 종목 정의 ─────────────────────────────────────────
THEMES = [
  {
    "id": "ai_infra", "name": "AI / LLM 인프라", "icon": "⬡",
    "comp_base": 84, "bernstein_stage": 9,
    "stocks": [
      {"ticker":"NVDA",   "name":"엔비디아",      "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"AMD",    "name":"AMD",            "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"AVGO",   "name":"Broadcom",       "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"TSM",    "name":"TSMC",           "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"MRVL",   "name":"Marvell Tech",   "market":"US", "type":"미국 중소형", "sig":"GROWTH"},
      {"ticker":"005930", "name":"삼성전자",        "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"000660", "name":"SK하이닉스",      "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"042700", "name":"한미반도체",      "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"058470", "name":"리노공업",        "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"007660", "name":"이수페타시스",    "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
    ],
  },
  {
    "id": "ai_dc", "name": "AI Datacenter / 전력", "icon": "▣",
    "comp_base": 88, "bernstein_stage": 9,
    "stocks": [
      {"ticker":"EQIX",   "name":"Equinix",        "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"VST",    "name":"Vistra",          "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"GEV",    "name":"GE Vernova",      "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"DLR",    "name":"Digital Realty",  "market":"US", "type":"미국 대형",   "sig":"GROWTH"},
      {"ticker":"NRG",    "name":"NRG Energy",      "market":"US", "type":"미국 대형",   "sig":"WATCH"},
      {"ticker":"000660", "name":"SK하이닉스",      "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"005930", "name":"삼성전자",        "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"010120", "name":"LS일렉트릭",      "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"298040", "name":"효성중공업",      "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"034020", "name":"두산에너빌리티",  "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
    ],
  },
  {
    "id": "space", "name": "Space Tech / 위성", "icon": "◎",
    "comp_base": 73, "bernstein_stage": 8,
    "stocks": [
      {"ticker":"RKLB",   "name":"Rocket Lab",          "market":"US", "type":"미국 중소형", "sig":"GROWTH"},
      {"ticker":"ASTS",   "name":"AST SpaceMobile",     "market":"US", "type":"미국 중소형", "sig":"GROWTH"},
      {"ticker":"LUNR",   "name":"Intuitive Machines",  "market":"US", "type":"미국 중소형", "sig":"WATCH"},
      {"ticker":"BWXT",   "name":"BWX Technologies",    "market":"US", "type":"미국 중소형", "sig":"WATCH"},
      {"ticker":"KTOS",   "name":"Kratos Defense",      "market":"US", "type":"미국 중소형", "sig":"WATCH"},
      {"ticker":"012450", "name":"한화에어로스페이스",  "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"099440", "name":"쎄트렉아이",          "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
      {"ticker":"227950", "name":"컨텍",               "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"211270", "name":"AP위성",              "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"189300", "name":"인텔리안테크",        "market":"KR", "type":"한국 상장",   "sig":"GROWTH"},
    ],
  },
  {
    "id": "quantum", "name": "양자컴퓨팅", "icon": "◈",
    "comp_base": 61, "bernstein_stage": 7,
    "stocks": [
      {"ticker":"IONQ",   "name":"IonQ",             "market":"US", "type":"미국 중소형", "sig":"VALUE"},
      {"ticker":"RGTI",   "name":"Rigetti",           "market":"US", "type":"미국 중소형", "sig":"VALUE"},
      {"ticker":"IBM",    "name":"IBM",               "market":"US", "type":"미국 대형",   "sig":"WATCH"},
      {"ticker":"QBTS",   "name":"D-Wave Quantum",    "market":"US", "type":"미국 중소형", "sig":"VALUE"},
      {"ticker":"QUBT",   "name":"Quantum Computing", "market":"US", "type":"미국 중소형", "sig":"VALUE"},
      {"ticker":"017670", "name":"SK텔레콤",          "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"030200", "name":"KT",                "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"032640", "name":"LG유플러스",        "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
      {"ticker":"054920", "name":"아이에이치큐",      "market":"KR", "type":"한국 상장",   "sig":"VALUE"},
      {"ticker":"035600", "name":"KG이니시스",        "market":"KR", "type":"한국 상장",   "sig":"WATCH"},
    ],
  },
]

# ── RSI 계산 ──────────────────────────────────────────────
def calc_rsi(closes, period=14):
    """종가 리스트에서 RSI(14) 계산"""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

# ── Yahoo Finance 수집 ────────────────────────────────────
def yahoo_price_and_rsi(ticker, market):
    """주가·등락률·3개월 모멘텀·RSI(14) 수집"""
    yt = ticker + ".KS" if market == "KR" else ticker
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yt}?interval=1d&range=6mo"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return {}
        d    = result[0]
        meta = d.get("meta", {})
        closes_raw = d.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes_raw if c is not None]

        price   = meta.get("regularMarketPrice")
        prev_c  = meta.get("chartPreviousClose")
        change1d = round((price - prev_c) / prev_c * 100, 2) if price and prev_c else None
        mom3m    = round((closes[-1] - closes[-63]) / closes[-63] * 100, 1) if len(closes) >= 63 else (
                   round((closes[-1] - closes[0])  / closes[0]   * 100, 1) if len(closes) > 5 else None)
        rsi = calc_rsi(closes)

        return {
            "price":     round(price, 2) if price else None,
            "change_1d": change1d,
            "mom_3m":    mom3m,
            "rsi":       rsi,
        }
    except Exception as e:
        print(f"    [price] {ticker}: {e}")
        return {}

def yahoo_fundamentals(ticker, market):
    """PER·선행PER·EPS·목표주가·기관지분·매출성장·영업이익률 수집"""
    yt = ticker + ".KS" if market == "KR" else ticker
    modules = "defaultKeyStatistics,financialData,earningsTrend,institutionOwnershipSummary"
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{yt}?modules={modules}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        s = r.json().get("quoteSummary", {}).get("result", [{}])[0]
        ks   = s.get("defaultKeyStatistics", {})
        fd   = s.get("financialData", {})
        et   = s.get("earningsTrend", {}).get("trend", [{}])
        inst = s.get("institutionOwnershipSummary", {})

        # EPS 추정치 수정 방향
        eps_now = et[0].get("epsTrend", {}).get("current", {}).get("raw") if et else None
        eps_30d = et[0].get("epsTrend", {}).get("30daysAgo", {}).get("raw") if et else None
        rev_pct = None
        rev_dir = None
        if eps_now is not None and eps_30d and eps_30d != 0:
            rev_pct = round((eps_now - eps_30d) / abs(eps_30d) * 100, 2)
            rev_dir = "상향" if rev_pct > 1 else "하향" if rev_pct < -1 else "유지"

        def rv(d, k, mult=1, rnd=2):
            v = d.get(k, {})
            raw = v.get("raw") if isinstance(v, dict) else v
            return round(raw * mult, rnd) if raw is not None else None

        return {
            "per":           rv(ks, "trailingPE", rnd=1),
            "forward_per":   rv(ks, "forwardPE",  rnd=1),
            "eps":           rv(ks, "trailingEps", rnd=2),
            "market_cap":    rv(ks, "marketCap",   rnd=0),
            "target_price":  rv(fd, "targetMeanPrice", rnd=1),
            "revenue_growth": rv(fd, "revenueGrowth", mult=100, rnd=1),
            "op_margin":     rv(fd, "operatingMargins", mult=100, rnd=1),
            "inst_pct":      round((inst.get("ownershipPercent", {}).get("raw") or 0) * 100, 1),
            "eps_revision_pct": rev_pct,
            "eps_revision_dir": rev_dir,
            "eps_now":       eps_now,
            "eps_30d":       eps_30d,
        }
    except Exception as e:
        print(f"    [fundamentals] {ticker}: {e}")
        return {}

def yahoo_institutions(ticker, market):
    """상위 기관 보유자 목록"""
    yt = ticker + ".KS" if market == "KR" else ticker
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{yt}?modules=institutionOwnership"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        holders = (r.json().get("quoteSummary", {})
                           .get("result", [{}])[0]
                           .get("institutionOwnership", {})
                           .get("ownershipList", []))
        return [
            {
                "name":     h.get("organization"),
                "pct_held": round((h.get("pctHeld", {}).get("raw") or 0) * 100, 3),
                "date":     h.get("reportDate", {}).get("fmt"),
            }
            for h in holders[:8]
        ]
    except:
        return []

# ── Finnhub EPS 서프라이즈 ────────────────────────────────
def finnhub_earnings(ticker):
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/stock/earnings?symbol={ticker}&limit=6&token={FINNHUB_KEY}",
            timeout=10
        )
        return [
            {
                "period":       e.get("period"),
                "actual":       e.get("actual"),
                "estimate":     e.get("estimate"),
                "surprise_pct": round(e.get("surprisePercent") or 0, 2),
            }
            for e in r.json()
        ]
    except:
        return []

# ── DART 한국 재무 (선택적) ──────────────────────────────
def dart_financials(corp_code):
    """DART OpenAPI에서 한국 재무 데이터 수집"""
    if not DART_KEY or not corp_code:
        return {}
    try:
        year = datetime.datetime.now().year - 1  # 직전 회계연도
        url = (f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
               f"?crtfc_key={DART_KEY}&corp_code={corp_code}"
               f"&bsns_year={year}&reprt_code=11011&fs_div=CFS")
        r = requests.get(url, timeout=12)
        items = r.json().get("list", [])
        result = {}
        for item in items:
            acnt = item.get("account_nm", "")
            if "매출" in acnt and "합계" in acnt:
                result["revenue"] = item.get("thstrm_amount")
            if "영업이익" in acnt:
                result["op_income"] = item.get("thstrm_amount")
        return result
    except:
        return {}

# DART 종목코드 매핑 (필요 시 확장)
DART_CODES = {
    "005930": "00126380",  # 삼성전자
    "000660": "00164742",  # SK하이닉스
    "012450": "00164588",  # 한화에어로스페이스
}

# ── 신호 점수 계산 ────────────────────────────────────────
def compute_composite(theme, stock_data_list):
    """
    번스타인 사이클 복합 점수 계산
    기본값은 theme의 comp_base 사용 (검증된 수동 값)
    실데이터가 충분하면 자동 보정
    """
    revisions, inst_pcts, moms, surprises = [], [], [], []

    for s in stock_data_list:
        fin  = s.get("financials", {})
        px   = s.get("price", {})
        earn = s.get("earnings", [])

        if fin.get("eps_revision_pct") is not None:
            revisions.append(fin["eps_revision_pct"])
        if fin.get("inst_pct"):
            inst_pcts.append(fin["inst_pct"])
        if px.get("mom_3m") is not None:
            moms.append(px["mom_3m"])
        if earn:
            surprises.extend([e["surprise_pct"] for e in earn[:3] if e.get("surprise_pct")])

    def safe_avg(lst):
        return round(sum(lst) / len(lst), 2) if lst else None

    avg_rev  = safe_avg(revisions)
    avg_inst = safe_avg(inst_pcts)
    avg_mom  = safe_avg(moms)
    avg_surp = safe_avg(surprises)

    # 자동 점수 (데이터 있을 때만 사용)
    has_data = sum([v is not None for v in [avg_rev, avg_inst, avg_mom, avg_surp]])
    if has_data >= 2:
        def rev_s(v):
            if v is None: return 50
            if v > 10: return 90
            if v > 5:  return 80
            if v > 1:  return 65
            if v > -1: return 50
            if v > -5: return 35
            return 20
        def inst_s(v):
            if v is None: return 60
            if v > 80: return 90
            if v > 60: return 75
            if v > 40: return 60
            return 45
        def mom_s(v):
            if v is None: return 50
            if v > 30: return 85
            if v > 10: return 70
            if v > 0:  return 55
            if v > -10: return 40
            return 25
        def surp_s(v):
            if v is None: return 50
            if v > 10: return 90
            if v > 5:  return 75
            if v > 0:  return 60
            if v > -5: return 40
            return 25

        auto = round(
            rev_s(avg_rev)  * 0.25 +
            inst_s(avg_inst)* 0.25 +
            mom_s(avg_mom)  * 0.20 +
            surp_s(avg_surp)* 0.20 +
            60              * 0.10
        )
        # 기준값과 자동값의 가중평균 (기준값 신뢰도 70%)
        composite = round(theme["comp_base"] * 0.7 + auto * 0.3)
    else:
        composite = theme["comp_base"]

    # 번스타인 단계 매핑
    STAGE_MAP = {
        (85, 100): (9,  "이익추정치 상향 수정"),
        (75,  85): (8,  "긍정적 어닝 서프라이즈 모델"),
        (65,  75): (7,  "역발상 → 긍정적 서프라이즈"),
        (55,  65): (6,  "역발상 투자 단계"),
        (45,  55): (5,  "무시 단계"),
        (35,  45): (4,  "소외 단계"),
        (25,  35): (3,  "추정치 하향"),
        ( 0,  25): (2,  "부정적 서프라이즈"),
    }
    stage, label = theme["bernstein_stage"], "이익추정치 상향 수정"
    for (lo, hi), (s, l) in STAGE_MAP.items():
        if lo <= composite < hi:
            stage, label = s, l
            break

    return {
        "composite":       composite,
        "bernstein_stage": stage,
        "bernstein_label": label,
        "avg_eps_revision": avg_rev,
        "avg_inst_pct":    avg_inst,
        "avg_mom_3m":      avg_mom,
        "avg_eps_surprise":avg_surp,
    }

# ── Telegram ──────────────────────────────────────────────
def send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"  Telegram 오류: {e}")

def build_alert(theme, prev_sig, curr_sig):
    sc, ps = curr_sig.get("composite", 0), prev_sig.get("composite", 0)
    diff = sc - ps
    stage_changed = curr_sig.get("bernstein_stage") != prev_sig.get("bernstein_stage")
    lines = [
        f"{'🚨' if stage_changed else '📊'} <b>Inflection Point Tracker</b>",
        "━━━━━━━━━━━━━━━━",
        f"{theme['icon']} <b>{theme['name']}</b>",
        "",
        f"📍 단계: <b>{curr_sig['bernstein_label']}</b>" + (f" ← {prev_sig.get('bernstein_label','?')}" if stage_changed else ""),
        f"📈 복합 점수: <b>{sc}</b> {'▲' if diff>0 else '▼' if diff<0 else '━'} ({diff:+d})",
        "",
        f"  • EPS 수정: {curr_sig.get('avg_eps_revision', '—')}%",
        f"  • 기관 지분: {curr_sig.get('avg_inst_pct', '—')}%",
        f"  • 3M 모멘텀: {curr_sig.get('avg_mom_3m', '—')}%",
        f"  • EPS 서프라이즈: {curr_sig.get('avg_eps_surprise', '—')}%",
        "",
        f"🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
        "⚠ 투자 참고용 · 투자 권유 아님",
    ]
    return "\n".join(lines)

def build_weekly(data):
    lines = [
        "📋 <b>Inflection Point Tracker — Weekly Summary</b>",
        "━━━━━━━━━━━━━━━━",
        f"📅 {datetime.datetime.now().strftime('%Y년 %m월 %d일')}\n",
    ]
    for t in data["themes"]:
        sig = t["signal"]
        sc  = sig.get("composite", 0)
        em  = "🟢" if sc >= 80 else "🔵" if sc >= 65 else "🟡" if sc >= 50 else "🔴"
        lines.append(f"{t['icon']} <b>{t['name']}</b>")
        lines.append(f"   {em} {sig.get('bernstein_label','?')} | 점수 {sc}")
        lines.append(f"   EPS수정 {sig.get('avg_eps_revision','—')}% | 기관 {sig.get('avg_inst_pct','—')}%\n")
    lines.append("⚠ 투자 참고용 · 투자 권유 아님")
    return "\n".join(lines)

# ── 변화 감지 ─────────────────────────────────────────────
def detect_changes(prev, curr):
    alerts = []
    for t in curr["themes"]:
        pt = next((x for x in prev.get("themes", []) if x["id"] == t["id"]), None)
        if not pt:
            continue
        cs, ps = t["signal"], pt.get("signal", {})
        stage_diff = cs.get("bernstein_stage") != ps.get("bernstein_stage")
        score_diff = abs((cs.get("composite") or 0) - (ps.get("composite") or 0))
        if stage_diff or score_diff >= 5:
            alerts.append((t, ps, cs))
    return alerts

# ── 메인 ──────────────────────────────────────────────────
def main():
    now = datetime.datetime.now()
    print(f"\n{'='*56}")
    print(f"Inflection Point Tracker  {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*56}\n")

    result = {
        "updated_at": now.isoformat(),
        "themes": [],
    }

    for theme in THEMES:
        print(f"\n[{theme['icon']} {theme['name']}]")
        stock_data = []

        for s in theme["stocks"]:
            ticker, market = s["ticker"], s["market"]
            print(f"  {ticker:>8}  {s['name']}")

            px   = yahoo_price_and_rsi(ticker, market)
            fin  = yahoo_fundamentals(ticker, market)
            inst = yahoo_institutions(ticker, market) if market == "US" else []
            earn = finnhub_earnings(ticker) if market == "US" else []
            dart = dart_financials(DART_CODES.get(ticker)) if market == "KR" else {}

            # 수집 결과 요약 출력
            price_str = f"₩{px.get('price'):,.0f}" if market == "KR" and px.get("price") else \
                        f"${px.get('price'):.2f}" if px.get("price") else "—"
            rsi_str   = f"RSI {px.get('rsi')}" if px.get("rsi") else "RSI —"
            per_str   = f"PER {fin.get('per')}" if fin.get("per") else "PER —"
            print(f"           → {price_str}  {per_str}  {rsi_str}")

            stock_data.append({
                "ticker":       ticker,
                "name":         s["name"],
                "market":       market,
                "type":         s["type"],
                "sig":          s["sig"],
                "price":        px,
                "financials":   fin,
                "dart":         dart,
                "institutions": inst,
                "earnings":     earn,
            })
            time.sleep(1.0)  # Yahoo rate limit 방지

        signal = compute_composite(theme, stock_data)
        print(f"\n  → 복합 점수: {signal['composite']} | {signal['bernstein_label']}")

        result["themes"].append({
            "id":     theme["id"],
            "name":   theme["name"],
            "icon":   theme["icon"],
            "signal": signal,
            "stocks": stock_data,
        })

    # ── 저장 ──────────────────────────────────────────────
    DATA_FILE.parent.mkdir(exist_ok=True)

    prev = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {"themes": []}

    # 변화 감지 → Telegram
    alerts = detect_changes(prev, result)
    if alerts:
        print(f"\n변화 감지: {len(alerts)}개 테마")
        for theme, ps, cs in alerts:
            msg = build_alert(theme, ps, cs)
            print(f"\n--- Telegram ---\n{msg}\n")
            send_telegram(msg)
    else:
        print("\n유의미한 변화 없음")
        if now.weekday() == 0:  # 월요일 → 주간 요약
            send_telegram(build_weekly(result))

    # 백업 후 저장
    if DATA_FILE.exists():
        shutil.copy(DATA_FILE, PREV_FILE)
    DATA_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✓ data/signals.json 저장 완료 ({len(result['themes'])}개 테마, 40개 종목)")
    print(f"  다음 실행: 오전 8시 또는 오후 6시 KST (GitHub Actions)")

if __name__ == "__main__":
    main()
