# 패러다임 시프트 트래커

번스타인 어닝 사이클 + BlackRock·Vanguard 기관 자금 흐름 기반 신호 감지 시스템

**Telegram 알림 + Vercel 웹 대시보드**

---

## 파일 구조

```
paradigm-tracker/
├── monitor.py                      ← 데이터 수집 + Telegram 발송 (GitHub Actions 실행)
├── requirements.txt
├── vercel.json
├── data/
│   └── signals.json                ← 수집 결과 (자동 생성)
├── dashboard/
│   └── index.html                  ← 웹 대시보드 (Vercel 배포)
└── .github/workflows/
    └── monitor.yml                 ← 자동 스케줄 (매일 08시·18시 KST)
```

---

## 1단계 — GitHub 저장소 생성

1. https://github.com/new 접속
2. Repository name: `paradigm-tracker`
3. **Public** 선택 (Vercel 무료 연동)
4. Create repository 클릭
5. 이 폴더 전체를 업로드하거나 git push

```bash
git init
git add .
git commit -m "init: paradigm tracker"
git remote add origin https://github.com/[내_아이디]/paradigm-tracker.git
git push -u origin main
```

---

## 2단계 — Telegram 봇 생성

1. Telegram에서 **@BotFather** 검색 → 대화 시작
2. `/newbot` 입력
3. 봇 이름 입력 (예: `ParadigmTrackerBot`)
4. 봇 username 입력 (예: `my_paradigm_bot`)
5. **API Token** 복사해두기 (예: `7123456789:AAF...`)

**Chat ID 확인:**
1. 본인 Telegram에서 방금 만든 봇에게 아무 메시지 전송
2. 브라우저에서 접속:
   ```
   https://api.telegram.org/bot[TOKEN]/getUpdates
   ```
3. 응답에서 `"chat":{"id":XXXXXXX}` 숫자가 Chat ID

---

## 3단계 — GitHub Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions → **New repository secret**

| Secret 이름         | 값                          | 필수 |
|--------------------|-----------------------------|------|
| `TELEGRAM_BOT_TOKEN` | BotFather에서 받은 토큰      | ✅   |
| `TELEGRAM_CHAT_ID`   | 본인 Chat ID (숫자)          | ✅   |
| `FINNHUB_KEY`        | finnhub.io 무료 API 키       | 권장  |
| `EARNINGSFEED_KEY`   | earningsfeed.com 무료 키     | 선택  |

**Finnhub 키 발급:** https://finnhub.io/register (1분, 무료)

---

## 4단계 — Vercel 배포

1. https://vercel.com 접속 → GitHub 계정으로 로그인
2. **Add New Project** → GitHub 저장소 선택 (`paradigm-tracker`)
3. Framework Preset: **Other**
4. Root Directory: 그대로 (`./`)
5. **Deploy** 클릭
6. 완료 후 `https://paradigm-tracker.vercel.app` 접속 확인

---

## 5단계 — 첫 실행 테스트

GitHub 저장소 → **Actions** 탭 → `Paradigm Tracker — Daily Monitor` → **Run workflow** 클릭

약 2~3분 후:
- ✅ Telegram으로 첫 알림 수신
- ✅ `data/signals.json` 자동 업데이트
- ✅ Vercel 대시보드에 실제 데이터 반영

---

## 알림 기준

다음 중 하나라도 발생하면 Telegram 즉시 발송:

| 조건 | 설명 |
|------|------|
| 번스타인 단계 변화 | Stage 7→8 등 사이클 단계 이동 |
| 복합 점수 ±5점 이상 | 주요 신호 복합 변화 |
| EPS 추정치 수정 ±3% | 애널리스트 컨센서스 급변 |

매주 **월요일 오전 8시**에는 변화 없어도 주간 요약 리포트 발송

---

## 신호 가중치

```
복합 점수 = TAM×0.25 + 기관자금×0.25 + 정책×0.20 + 실적×0.20 + 공매도역×0.10
```

**VC 투자 가중치 = 0** (상장주이므로 완전 제외)
**기관 자금 흐름 (13F)** = BlackRock·Vanguard·Blackstone 포지션 변화로 대체

---

## 비용 요약

| 항목 | 비용 |
|------|------|
| GitHub Actions | 무료 (월 2,000분) |
| Vercel 호스팅 | 무료 |
| Yahoo Finance API | 무료 (키 불필요) |
| Finnhub API | 무료 (월 30만 콜) |
| Telegram Bot API | 무료 |
| **합계** | **$0** |

---

⚠ 투자 참고용 · 투자 권유 아님
