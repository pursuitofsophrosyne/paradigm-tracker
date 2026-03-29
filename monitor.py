"""
Paradigm Shift Tracker — 모니터링 스크립트
- Yahoo Finance에서 PER·EPS·기관지분 데이터 수집
- Finnhub에서 EPS 서프라이즈 히스토리 수집
- 번스타인 사이클 신호 변화 감지
- 변화 감지 시 Telegram 알림 발송
- data/signals.json 업데이트 (Vercel 웹 대시보드용)
"""

import os, json, time, datetime, requests
from pathlib import Path

# ── 환경 변수 (GitHub Secrets에서 주입) ──────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
FINNHUB_KEY        = os.environ.get("FINNHUB_KEY", "")
EARNINGSFEED_KEY   = os.environ.get("EARNINGSFEED_KEY", "")

DATA_FILE = Path("data/signals.json")
PREV_FILE = Path("data/signals_prev.json")

# ── 추적 종목 ────────────────────────────────────────────────────
THEMES = [
    {
        "id": "ai_infra",
        "name": "AI / LLM 인프라",
        "icon": "⬡",
        "stocks": [
            {"ticker": "NVDA", "name": "엔비디아",  "market": "US"},
            {"ticker": "AMD",  "name": "AMD",       "market": "US"},
            {"ticker": "ANET", "name": "Arista",    "market": "US"},
        ],
    },
    {
        "id": "quantum",
        "name": "양자컴퓨팅",
        "icon": "◈",
        "stocks": [
            {"ticker": "IONQ", "name": "IonQ",    "market": "US"},
            {"ticker": "RGTI", "name": "Rigetti", "market": "US"},
            {"ticker": "IBM",  "name": "IBM",     "market": "US"},
        ],
    },
    {
        "id": "space",
        "name": "Space Tech / 위성",
        "icon": "◎",
        "stocks": [
            {"ticker": "RKLB", "name": "Rocket Lab",        "market": "US"},
            {"ticker": "ASTS", "name": "AST SpaceMobile",   "market": "US"},
            {"ticker": "LUNR", "name": "Intuitive Machines", "market": "US"},
        ],
    },
    {
        "id": "ai_dc",
        "name": "AI Datacenter / 전력",
        "icon": "▣",
        "stocks": [
            {"ticker": "EQIX",   "name": "Equinix",    "market": "US"},
            {"ticker": "VST",    "name": "Vistra",     "market": "US"},
            {"ticker": "005930", "name": "삼성전자",   "market": "KR"},
            {"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        ],
    },
]

# ── 데이터 수집 ──────────────────────────────────────────────────

def yahoo_summary(ticker, market):
    """Yahoo Finance에서 PER·EPS·기관지분 수집"""
    y_ticker = ticker + ".KS" if market == "KR" else ticker
    modules = "defaultKeyStatistics,financialData,earningsTrend,institutionOwnershipSummary"
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{y_ticker}?modules={modules}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        s = r.json().get("quoteSummary", {}).get("result", [{}])[0]
        ks = s.get("defaultKeyStatistics", {})
        fd = s.get("financialData", {})
        et = s.get("earningsTrend", {}).get("trend", [{}])
        inst = s.get("institutionOwnershipSummary", {})

        eps_now  = et[0].get("epsTrend", {}).get("current", {}).get("raw") if et else None
        eps_30d  = et[0].get("epsTrend", {}).get("30daysAgo", {}).get("raw") if et else None
        eps_90d  = et[0].get("epsTrend", {}).get("90daysAgo", {}).get("raw") if et else None

        rev_dir = None
        rev_pct = None
        if eps_now and eps_30d and eps_30d != 0:
            rev_pct = round((eps_now - eps_30d) / abs(eps_30d) * 100, 2)
            rev_dir = "상향" if rev_pct > 1 else "하향" if rev_pct < -1 else "유지"

        return {
            "per":               round(ks.get("trailingPE", {}).get("raw", 0), 1),
            "forward_per":       round(ks.get("forwardPE", {}).get("raw", 0), 1),
            "eps":               round(ks.get("trailingEps", {}).get("raw", 0), 2),
            "market_cap":        ks.get("marketCap", {}).get("raw"),
            "revenue_growth":    round((fd.get("revenueGrowth", {}).get("raw") or 0) * 100, 1),
            "operating_margins": round((fd.get("operatingMargins", {}).get("raw") or 0) * 100, 1),
            "target_price":      round(fd.get("targetMeanPrice", {}).get("raw") or 0, 1),
            "inst_pct":          round((inst.get("ownershipPercent", {}).get("raw") or 0) * 100, 2),
            "eps_revision_dir":  rev_dir,
            "eps_revision_pct":  rev_pct,
            "eps_now":           eps_now,
            "eps_30d":           eps_30d,
            "eps_90d":           eps_90d,
        }
    except Exception as e:
        print(f"  Yahoo 오류 {ticker}: {e}")
        return {}

def yahoo_price(ticker, market):
    """현재 주가·등락률·3개월 모멘텀"""
    y_ticker = ticker + ".KS" if market == "KR" else ticker
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_ticker}?interval=1d&range=3mo"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json().get("chart", {}).get("result", [{}])[0]
        meta = d.get("meta", {})
        closes = d.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c]
        mom3m = round((closes[-1] - closes[0]) / closes[0] * 100, 1) if len(closes) > 5 else None
        price = meta.get("regularMarketPrice")
        prev  = meta.get("chartPreviousClose")
        change1d = round((price - prev) / prev * 100, 2) if price and prev else None
        return {"price": price, "change_1d": change1d, "mom_3m": mom3m}
    except Exception as e:
        print(f"  Price 오류 {ticker}: {e}")
        return {}

def finnhub_earnings(ticker):
    """Finnhub EPS 서프라이즈 히스토리"""
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

def top_institutions(ticker, market):
    """Yahoo Finance 상위 기관 보유자"""
    y_ticker = ticker + ".KS" if market == "KR" else ticker
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{y_ticker}?modules=institutionOwnership"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        holders = r.json().get("quoteSummary", {}).get("result", [{}])[0]\
                          .get("institutionOwnership", {}).get("ownershipList", [])
        return [
            {
                "name":     h.get("organization"),
                "pct_held": round((h.get("pctHeld", {}).get("raw") or 0) * 100, 3),
                "value":    h.get("value", {}).get("raw"),
                "date":     h.get("reportDate", {}).get("fmt"),
            }
            for h in holders[:8]
        ]
    except:
        return []

# ── 신호 점수 계산 ────────────────────────────────────────────────

def compute_signal_score(stock_data_list):
    """
    테마 내 종목들의 평균 지표로 번스타인 사이클 신호 점수 산출
    반환: {tam, institutional, policy, earnings, short_int, composite, stage}
    """
    revisions, inst_pcts, moms, eps_surprises = [], [], [], []

    for s in stock_data_list:
        fin = s.get("financials", {})
        price = s.get("price", {})
        earnings = s.get("earnings", [])

        if fin.get("eps_revision_pct") is not None:
            revisions.append(fin["eps_revision_pct"])
        if fin.get("inst_pct"):
            inst_pcts.append(fin["inst_pct"])
        if price.get("mom_3m") is not None:
            moms.append(price["mom_3m"])
        if earnings:
            recent = [e["surprise_pct"] for e in earnings[:3] if e.get("surprise_pct")]
            eps_surprises.extend(recent)

    def safe_avg(lst): return round(sum(lst)/len(lst), 2) if lst else None

    avg_rev     = safe_avg(revisions)
    avg_inst    = safe_avg(inst_pcts)
    avg_mom     = safe_avg(moms)
    avg_eps_sur = safe_avg(eps_surprises)

    # 점수화 (0~100)
    def rev_score(v):
        if v is None: return 50
        if v > 10: return 90
        if v > 5:  return 80
        if v > 1:  return 65
        if v > -1: return 50
        if v > -5: return 35
        return 20

    def inst_score(v):
        if v is None: return 50
        if v > 80: return 92
        if v > 70: return 82
        if v > 60: return 70
        if v > 50: return 58
        return 45

    def mom_score(v):
        if v is None: return 50
        if v > 30: return 88
        if v > 15: return 75
        if v > 5:  return 62
        if v > -5: return 50
        if v > -15:return 35
        return 20

    def eps_sur_score(v):
        if v is None: return 50
        if v > 10: return 90
        if v > 5:  return 78
        if v > 1:  return 62
        if v > -1: return 50
        if v > -5: return 35
        return 20

    s_earnings = eps_sur_score(avg_eps_sur)
    s_inst     = inst_score(avg_inst)
    s_mom      = mom_score(avg_mom)
    s_rev      = rev_score(avg_rev)

    # Composite: TAM(25) + 기관(25) + 정책(20) + 실적(20) + 공매도역(10)
    # TAM·정책은 정적 값 유지, 나머지는 실데이터
    composite = round(
        50 * 0.25 +          # TAM — 정적 (별도 업데이트 필요)
        s_inst * 0.25 +
        55 * 0.20 +          # 정책 — 정적
        s_earnings * 0.20 +
        s_mom * 0.10
    )

    # 번스타인 단계 추론
    if s_rev >= 75 and s_inst >= 75:
        stage, stage_label = 9, "이익추정치 상향 수정"
    elif s_rev >= 60 and s_inst >= 60:
        stage, stage_label = 8, "긍정적 어닝 서프라이즈 모델"
    elif s_rev >= 50 and avg_eps_sur and avg_eps_sur > 0:
        stage, stage_label = 7, "긍정적 어닝 서프라이즈"
    elif s_rev >= 40:
        stage, stage_label = 6, "역발상 투자"
    elif s_rev >= 30:
        stage, stage_label = 5, "무시"
    elif s_rev >= 20:
        stage, stage_label = 4, "소외"
    else:
        stage, stage_label = 3, "이익추정치 하향 수정"

    return {
        "earnings_score":     s_earnings,
        "institutional_score":s_inst,
        "momentum_score":     s_mom,
        "revision_score":     s_rev,
        "composite":          composite,
        "bernstein_stage":    stage,
        "bernstein_label":    stage_label,
        "avg_eps_revision":   avg_rev,
        "avg_inst_pct":       avg_inst,
        "avg_mom_3m":         avg_mom,
        "avg_eps_surprise":   avg_eps_sur,
    }

# ── Telegram 알림 ────────────────────────────────────────────────

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 미설정 — 알림 스킵")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram 발송: {r.status_code}")
    except Exception as e:
        print(f"Telegram 오류: {e}")

def format_alert(theme_id, theme_name, icon, prev_sig, curr_sig, changed_stocks):
    """Telegram 알림 메시지 포맷"""
    prev_stage = prev_sig.get("bernstein_stage", "?")
    curr_stage = curr_sig.get("bernstein_stage", "?")
    prev_score = prev_sig.get("composite", "?")
    curr_score = curr_sig.get("composite", "?")

    score_diff = curr_score - prev_score if isinstance(curr_score, int) and isinstance(prev_score, int) else 0
    score_arrow = "▲" if score_diff > 0 else "▼" if score_diff < 0 else "━"

    stage_changed = prev_stage != curr_stage

    lines = [
        f"{'🚨' if stage_changed else '📊'} <b>Inflection Point Tracker</b>",
        f"━━━━━━━━━━━━━━━━━━━",
        f"{icon} <b>{theme_name}</b>",
        "",
        f"📍 번스타인 단계: <b>{curr_sig['bernstein_label']}</b>" +
        (f" ← {prev_sig.get('bernstein_label','?')}" if stage_changed else ""),
        f"📈 복합 점수: <b>{curr_score}</b> {score_arrow} ({score_diff:+d})",
        "",
        "<b>핵심 신호</b>",
        f"  • EPS 추정치 수정: {curr_sig.get('avg_eps_revision', '—')}%",
        f"  • 기관 지분율 평균: {curr_sig.get('avg_inst_pct', '—')}%",
        f"  • 3M 모멘텀 평균: {curr_sig.get('avg_mom_3m', '—')}%",
        f"  • EPS 서프라이즈 평균: {curr_sig.get('avg_eps_surprise', '—')}%",
    ]

    if stage_changed:
        action_map = {
            9: "🟢 GROWTH 매수 구간 진입",
            8: "🟢 긍정적 서프라이즈 모델 — 매수 검토",
            7: "🔵 Value→Growth 전환 시작",
            6: "🔵 역발상 포지션 구축 고려",
            5: "🟡 무시 단계 — 관망",
            4: "🔴 소외 단계 — 진입 불가",
        }
        action = action_map.get(curr_stage, "⚪ 관망")
        lines += ["", f"<b>투자 액션</b>: {action}"]

    if changed_stocks:
        lines += ["", "<b>변화 감지 종목</b>"]
        for s in changed_stocks[:4]:
            lines.append(f"  • {s['ticker']} {s['name']}: {s['change']}")

    lines += [
        "",
        f"🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
        "⚠ 투자 참고용 · 투자 권유 아님",
    ]
    return "\n".join(lines)

# ── 변화 감지 ─────────────────────────────────────────────────────

CHANGE_THRESHOLD = {
    "composite":          5,    # 복합점수 5점 이상 변화
    "eps_revision_pct":   3.0,  # EPS 추정치 수정 3% 이상
    "mom_3m":             10.0, # 3개월 모멘텀 10% 이상
    "inst_pct":           2.0,  # 기관 지분율 2% 이상
}

def detect_changes(prev_data, curr_data):
    """전일 대비 유의미한 변화 감지"""
    alerts = []
    for theme in curr_data["themes"]:
        tid = theme["id"]
        prev_theme = next((t for t in prev_data.get("themes", []) if t["id"] == tid), None)
        if not prev_theme:
            continue

        curr_sig = theme["signal"]
        prev_sig = prev_theme.get("signal", {})

        # 번스타인 단계 변화
        stage_changed = curr_sig.get("bernstein_stage") != prev_sig.get("bernstein_stage")
        # 복합 점수 급변
        score_diff = abs((curr_sig.get("composite") or 0) - (prev_sig.get("composite") or 0))
        score_changed = score_diff >= CHANGE_THRESHOLD["composite"]

        if not (stage_changed or score_changed):
            continue

        # 종목 수준 변화 감지
        changed_stocks = []
        for stock in theme["stocks"]:
            prev_stock = next(
                (s for t in prev_data.get("themes", []) if t["id"] == tid
                 for s in t.get("stocks", []) if s["ticker"] == stock["ticker"]),
                {}
            )
            fin_curr = stock.get("financials", {})
            fin_prev = prev_stock.get("financials", {})

            rev_curr = fin_curr.get("eps_revision_pct") or 0
            rev_prev = fin_prev.get("eps_revision_pct") or 0
            if abs(rev_curr - rev_prev) >= CHANGE_THRESHOLD["eps_revision_pct"]:
                arrow = "▲" if rev_curr > rev_prev else "▼"
                changed_stocks.append({
                    "ticker": stock["ticker"],
                    "name":   stock["name"],
                    "change": f"EPS수정 {arrow}{abs(rev_curr - rev_prev):.1f}%",
                })

        alerts.append({
            "theme_id":     tid,
            "theme_name":   theme["name"],
            "icon":         theme["icon"],
            "stage_changed":stage_changed,
            "score_diff":   score_diff,
            "prev_sig":     prev_sig,
            "curr_sig":     curr_sig,
            "changed_stocks": changed_stocks,
        })

    return alerts

# ── 메인 ─────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*50}")
    print(f"Paradigm Tracker 실행: {datetime.datetime.now()}")
    print(f"{'='*50}\n")

    result = {
        "updated_at": datetime.datetime.now().isoformat(),
        "themes": [],
    }

    for theme in THEMES:
        print(f"\n[{theme['name']}]")
        theme_stocks = []

        for stock in theme["stocks"]:
            ticker, market = stock["ticker"], stock["market"]
            print(f"  {ticker} 수집 중…")

            fin   = yahoo_summary(ticker, market)
            price = yahoo_price(ticker, market)
            earn  = finnhub_earnings(ticker) if market == "US" else []
            inst  = top_institutions(ticker, market)

            theme_stocks.append({
                "ticker":       ticker,
                "name":         stock["name"],
                "market":       market,
                "financials":   fin,
                "price":        price,
                "earnings":     earn,
                "institutions": inst,
            })
            time.sleep(1.2)  # rate limit 방지

        signal = compute_signal_score(theme_stocks)
        print(f"  → 복합 점수: {signal['composite']} | 단계: {signal['bernstein_label']}")

        result["themes"].append({
            "id":     theme["id"],
            "name":   theme["name"],
            "icon":   theme["icon"],
            "signal": signal,
            "stocks": theme_stocks,
        })

    # 데이터 저장
    DATA_FILE.parent.mkdir(exist_ok=True)
    prev_data = json.loads(PREV_FILE.read_text()) if PREV_FILE.exists() else {"themes": []}

    # 변화 감지 & Telegram 발송
    if DATA_FILE.exists():
        prev_data = json.loads(DATA_FILE.read_text())
    alerts = detect_changes(prev_data, result)

    if alerts:
        print(f"\n변화 감지: {len(alerts)}개 테마")
        for alert in alerts:
            msg = format_alert(
                alert["theme_id"], alert["theme_name"], alert["icon"],
                alert["prev_sig"], alert["curr_sig"], alert["changed_stocks"]
            )
            print(f"\n--- Telegram 알림 ---\n{msg}\n")
            send_telegram(msg)
    else:
        print("\n유의미한 변화 없음 — Telegram 알림 스킵")
        # 매주 월요일엔 요약 리포트 발송
        if datetime.datetime.now().weekday() == 0:
            weekly = build_weekly_summary(result)
            send_telegram(weekly)

    # 백업 후 저장
    if DATA_FILE.exists():
        import shutil
        shutil.copy(DATA_FILE, PREV_FILE)
    DATA_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n✓ data/signals.json 저장 완료")

def build_weekly_summary(data):
    lines = [
        "📋 <b>Inflection Point Tracker — Weekly Summary</b>",
        f"━━━━━━━━━━━━━━━━━━━",
        f"📅 {datetime.datetime.now().strftime('%Y년 %m월 %d일')} 기준\n",
    ]
    for t in data["themes"]:
        sig = t["signal"]
        score = sig.get("composite", "?")
        label = sig.get("bernstein_label", "?")
        emoji = "🟢" if score >= 75 else "🔵" if score >= 60 else "🟡" if score >= 45 else "🔴"
        lines.append(f"{t['icon']} <b>{t['name']}</b>")
        lines.append(f"   {emoji} {label} | 점수 {score}")
        lines.append(f"   EPS수정 {sig.get('avg_eps_revision','—')}% | 기관 {sig.get('avg_inst_pct','—')}%\n")
    lines.append("⚠ 투자 참고용 · 투자 권유 아님")
    return "\n".join(lines)

if __name__ == "__main__":
    main()
