# AI 수익화 트렌드 TOP 10

매일 자동으로 유튜브 쇼츠에서 AI 수익화 관련 인기 콘텐츠를 수집·분석하여 랭킹으로 정리하는 웹사이트.

## 기능
- 일간 TOP 10 / 주간 TOP 5 / 월간 TOP 5
- 클릭 시 상세 브리핑 (수익화 방법, 핵심 원리, 필요한 것, 현실성 미터)
- 한/영 자동 언어 전환 (브라우저 감지 + 수동 토글)
- 수익화 유형 태그 + 필터
- 신규 진입 NEW 뱃지
- 제휴 광고 관리 (ads.json)
- TTS 대본 자동 생성 (한/영)
- Goatcounter 방문자 통계

## 셋업

### 1. GitHub 레포에 파일 업로드
ZIP 안의 파일들을 레포 **루트**에 올리세요. `package.json`이 최상위에 보여야 합니다.

### 2. GitHub Secrets 추가
- `YOUTUBE_API_KEY` — [Google Cloud Console](https://console.cloud.google.com/)에서 발급
- `OPENAI_API_KEY` — [OpenAI](https://platform.openai.com/)에서 발급

### 3. Vercel 배포
- vercel.com → Import → Framework: Vite → Deploy

### 4. Goatcounter 설정
- [goatcounter.com](https://www.goatcounter.com) 가입
- `index.html`과 `src/App.jsx`에서 `YOUR_SITE_ID` 교체

### 5. 광고 링크 설정
`public/config/ads.json`에서 URL 교체

## 구조
```
package.json
index.html
vite.config.js
vercel.json
src/App.jsx              ← 프론트엔드 (단일 파일)
public/
  config/ads.json        ← 광고 설정 (사이드바 5슬롯 + 인라인 + 배너)
  data/daily/*.json      ← 일간 데이터
  data/weekly.json
  data/monthly.json
  tts/latest.json        ← TTS 대본
scripts/
  scan.py                ← 수집 + LLM 분석
  generate_tts_script.py ← TTS 대본 생성
.github/workflows/
  daily-scan.yml         ← 하루 6회 자동 실행
```

## 비용
- YouTube API: 무료
- OpenAI gpt-4o-mini: ~$1-3/월
- Vercel: 무료
- Goatcounter: 무료
