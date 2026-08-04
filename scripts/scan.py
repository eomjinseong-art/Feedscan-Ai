"""
AI Money Scanner - 일간 스캐너 v3
- YouTube Data API로 쇼츠 + 일반 영상 분리 수집
- OpenAI API로 브리핑 + 번역 자동 생성
- 주간/월간 랭킹 즉시 생성
"""
import os, json, time
from datetime import datetime, timedelta
from pathlib import Path
from googleapiclient.discovery import build
from openai import OpenAI

# === CONFIG ===
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

KR_KEYWORDS = [
    # AI + 부업/수익
    "AI 부업", "AI 부업 추천", "ChatGPT 돈버는법", "AI 수익화", "AI 재택",
    "AI 온라인 알바", "인공지능 부업", "AI 자동화 수익", "GPT 부업", "AI 투잡",
    "AI 월 100만원", "AI 수익 인증", "AI 무자본 부업", "AI 프리랜서",
    # AI + 콘텐츠
    "AI 유튜브 수익", "AI 콘텐츠 수익", "AI 영상 자동화", "AI 쇼츠 수익",
    "AI 음악 수익", "AI 그림 판매",
    # 제휴마케팅 플랫폼
    "쿠팡파트너스", "링크프라이스", "텐핑", "애드픽",
    "올리브영 큐레이터", "무신사 큐레이터", "에이블리 큐레이터",
    "삼성전자 ACE", "오늘의집 큐레이터", "컴리 큐레이터",
    "마이리얼트립 파트너", "클룩 어필리에이트", "세시간전 크리에이터",
    # AI + 제휴
    "AI 블로그 수익", "AI 스마트스토어", "AI 전자책 판매", "AI 제휴마케팅"
]
EN_KEYWORDS = [
    "make money with AI", "AI side hustle", "AI passive income",
    "ChatGPT earn money", "AI business ideas", "AI automation income",
    "AI freelance money", "GPT side hustle", "AI income online",
    "earn with ChatGPT", "AI money making", "AI job replacement",
    "AI gig economy", "make $1000 with AI", "AI remote work money",
    "AI content monetization", "AI dropshipping", "AI affiliate marketing",
    "AI digital products", "quit job with AI",
    "Amazon affiliate", "Aliexpress affiliate"
]
AITOOL_KEYWORDS = [
    # 한국어
    "ChatGPT 사용법", "미드저니 사용법", "힙스필드", "AI 툴 추천",
    "Runway 사용법", "Suno AI", "Claude 활용", "Cursor AI",
    "Gemini 활용법", "신규 AI 툴", "AI 영상편집", "AI 이미지 생성",
    "AI 앱 추천", "AI 툴 리뷰", "AI 신규 서비스",
    # 영어
    "Midjourney tutorial", "ChatGPT tips 2026", "AI tools 2026",
    "Runway ML tutorial", "Heygen tutorial", "Sora AI",
    "Kling AI", "best AI tools", "AI workflow automation",
    "Claude AI tips", "Cursor AI coding", "Gamma AI",
    "new AI tool", "best AI tools 2026", "AI tool review",
    "AI app of the week", "must have AI tools"
]

MIN_VIEWS = 500
DAYS_BACK = 30
MAX_RESULTS = 20
TOP_N = 10

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
DAILY_DIR = DATA_DIR / "daily"

# === UTILS ===
def has_korean(text):
    """텍스트에 한글이 포함되어 있는지 확인"""
    import re
    return bool(re.search('[가-힣]', text))

def has_non_english(text):
    """힌디어/데바나가리/아랍어 등 비영어 문자 포함 여부 (인도 콘텐츠 필터)"""
    import re
    return bool(re.search('[\u0900-\u097F\u0600-\u06FF\u0980-\u09FF\u0A00-\u0A7F]', text))

def mask_channel(name):
    if len(name) <= 2: return name[0] + "***"
    if len(name) <= 5: return name[:2] + "***"
    return name[:3] + "***"

def search_videos(yt, kw, lang, after, duration_filter=None, region_code=None):
    """duration_filter: 'short' for shorts, 'medium'/'long' for regular videos, None for all"""
    try:
        params = dict(part="snippet", q=kw, type="video",
            order="viewCount", publishedAfter=after, relevanceLanguage=lang, maxResults=MAX_RESULTS)
        if duration_filter:
            params["videoDuration"] = duration_filter
        if region_code:
            params["regionCode"] = region_code
        r = yt.search().list(**params).execute()
        return r.get("items", [])
    except Exception as e:
        print(f"  [ERR] {kw}: {e}"); return []

def get_details(yt, ids):
    if not ids: return {}
    details = {}
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="statistics,snippet,contentDetails", id=",".join(ids[i:i+50])).execute()
        for item in r.get("items", []):
            s = item.get("statistics", {})
            # 영상 길이 파싱 (PT1M30S 형태)
            duration = item.get("contentDetails", {}).get("duration", "")
            is_short = parse_duration_seconds(duration) <= 60
            details[item["id"]] = {
                "video_id": item["id"],
                "title": item["snippet"]["title"],
                "channel_masked": mask_channel(item["snippet"]["channelTitle"]),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "published": item["snippet"]["publishedAt"][:10],
                "description": item["snippet"].get("description", "")[:300],
                "is_short": is_short,
            }
    return details

def parse_duration_seconds(duration_str):
    """ISO 8601 duration (PT1M30S) → seconds"""
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h*3600 + m*60 + s

# === LLM ANALYSIS ===
def analyze_with_llm(client, items):
    titles_info = "\n".join([
        f"{i+1}. [{item['language'].upper()}] \"{item['title']}\" (views: {item['views']}, desc: {item.get('description','')})"
        for i, item in enumerate(items)
    ])

    prompt = f"""You are an AI monetization trend analyst. Analyze these YouTube videos about making money with AI.

For EACH video, provide:
1. title_ko: Korean translation (if already Korean, keep as-is)
2. title_en: English translation (if already English, keep as-is)
3. method: Monetization method in 1 line (Korean)
4. method_en: Monetization method in 1 line (English)
5. principle: Core principle, 1-2 sentences (Korean)
6. principle_en: Core principle, 1-2 sentences (English)
7. requirements: What's needed - cost + tools (Korean)
8. requirements_en: What's needed - cost + tools (English)
9. category: ONE of: "제휴마케팅", "디지털상품", "서비스대행", "콘텐츠채널", "드랍쉬핑", "강의판매", "자동화에이전시", "기타"
10. difficulty: 1-5
11. initial_cost: 1-5
12. time_to_profit: 1-5

Videos:
{titles_info}

Respond in valid JSON array format only. No text outside JSON."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=4000,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(content)
    except Exception as e:
        print(f"  [LLM ERR] {e}"); return None

def apply_analysis(items, analyses):
    if not analyses:
        for item in items:
            item["title_ko"] = item["title"] if item["language"] == "ko" else ""
            item["title_en"] = item["title"] if item["language"] == "en" else ""
            item["method"] = "분석 중..."; item["method_en"] = "Analyzing..."
            item["principle"] = ""; item["principle_en"] = ""
            item["requirements"] = ""; item["requirements_en"] = ""
            item["category"] = "기타"
            item["difficulty"] = 3; item["initial_cost"] = 3; item["time_to_profit"] = 3
        return
    # 부분 매칭 허용 (개수 불일치 시에도 있는 만큼 적용)
    if len(analyses) != len(items):
        print(f"  [WARN] LLM returned {len(analyses)} items, expected {len(items)}. Applying partial.")

    for item, analysis in zip(items, analyses):
        item["title_ko"] = analysis.get("title_ko", item["title"])
        item["title_en"] = analysis.get("title_en", item["title"])
        item["method"] = analysis.get("method", "")
        item["method_en"] = analysis.get("method_en", "")
        item["principle"] = analysis.get("principle", "")
        item["principle_en"] = analysis.get("principle_en", "")
        item["requirements"] = analysis.get("requirements", "")
        item["requirements_en"] = analysis.get("requirements_en", "")
        item["category"] = analysis.get("category", "기타")
        item["difficulty"] = analysis.get("difficulty", 3)
        item["initial_cost"] = analysis.get("initial_cost", 3)
        item["time_to_profit"] = analysis.get("time_to_profit", 3)

    for item in items:
        item.pop("description", None)

# === RANKINGS ===
def update_rankings(period_days, filename, top_n, content_type=None):
    """content_type: 'shorts' or 'videos' or None (all)"""
    data = {}
    today = datetime.now()
    all_prev_ids = set()

    for i in range(period_days):
        fp = DAILY_DIR / f"{(today - timedelta(days=i)).strftime('%Y-%m-%d')}.json"
        if fp.exists():
            day_data = json.loads(fp.read_text(encoding="utf-8"))
            # 쇼츠와 영상 모두 확인
            for key in ["shorts_top10", "videos_top10", "top10"]:
                for item in day_data.get(key, []):
                    # content_type 필터
                    if content_type == "shorts" and not item.get("is_short", True): continue
                    if content_type == "videos" and item.get("is_short", True): continue
                    vid = item["video_id"]
                    if i > 0: all_prev_ids.add(vid)
                    if vid in data:
                        if item["views"] > data[vid]["views"]: data[vid].update(item)
                        data[vid]["appearances"] += 1
                    else:
                        data[vid] = {**item, "appearances": 1}

    for v in data.values():
        v["score"] = v["views"] * v["appearances"]
        v["is_new"] = v["video_id"] not in all_prev_ids

    top = sorted(data.values(), key=lambda x: x["score"], reverse=True)[:top_n]
    start = (today - timedelta(days=period_days-1)).strftime("%Y-%m-%d")
    output = {
        "period": f"{start} ~ {today.strftime('%Y-%m-%d')}",
        "updated_at": datetime.now().isoformat(),
        f"top{top_n}": top
    }
    (DATA_DIR / filename).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

# === MAIN ===
def main():
    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set"); return

    yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    after = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT00:00:00Z")

    # 한국/글로벌 완전 분리
    kr_shorts = {}
    kr_videos = {}
    en_shorts = {}
    en_videos = {}

    # === 한국 수집 ===
    print("=== KR (ALL) ===")
    for kw in KR_KEYWORDS[:12]:
        items = search_videos(yt, kw, "ko", after, None, region_code="KR")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and has_korean(info["title"]):
                info["language"] = "ko"
                if info["is_short"]:
                    if vid not in kr_shorts: kr_shorts[vid] = info
                else:
                    if vid not in kr_videos: kr_videos[vid] = info
    print(f"  KR shorts: {len(kr_shorts)}, KR videos: {len(kr_videos)}")

    # === 글로벌(미국 기반) 쇼츠 ===
    print("\n=== US SHORTS ===")
    for kw in EN_KEYWORDS[:10]:
        items = search_videos(yt, kw, "en", after, "short", region_code="US")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in en_shorts:
                if not has_non_english(info["title"]):
                    info["language"] = "en"; info["is_short"] = True; en_shorts[vid] = info

    # === 글로벌(미국 기반) 일반 영상 (duration 필터 없이 전체 검색 → is_short=False만) ===
    print("\n=== US VIDEOS ===")
    for kw in EN_KEYWORDS[:10]:
        items = search_videos(yt, kw, "en", after, None, region_code="US")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in en_videos and not info["is_short"]:
                if not has_non_english(info["title"]):
                    info["language"] = "en"; en_videos[vid] = info

    # TOP 10 선별 (각각 분리)
    kr_shorts_top10 = sorted(kr_shorts.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    kr_videos_top10 = sorted(kr_videos.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    shorts_top10 = sorted(en_shorts.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    videos_top10 = sorted(en_videos.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]

    # === AI Tool 수집 ===
    print("\n=== AI TOOL ===")
    aitool_shorts = {}
    aitool_videos = {}
    for kw in AITOOL_KEYWORDS[12:]:  # 영어 키워드
        items = search_videos(yt, kw, "en", after, None, region_code="US")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and not has_non_english(info["title"]):
                info["language"] = "en"
                if info["is_short"]:
                    if vid not in aitool_shorts: aitool_shorts[vid] = info
                else:
                    if vid not in aitool_videos: aitool_videos[vid] = info
    # 한국어 AI Tool 키워드
    for kw in AITOOL_KEYWORDS[:15]:  # 한국어 키워드
        items = search_videos(yt, kw, "ko", after, None, region_code="KR")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS:
                info["language"] = "ko" if has_korean(info["title"]) else "en"
                if info["is_short"]:
                    if vid not in aitool_shorts: aitool_shorts[vid] = info
                else:
                    if vid not in aitool_videos: aitool_videos[vid] = info

    aitool_shorts_top10 = sorted(aitool_shorts.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    aitool_videos_top10 = sorted(aitool_videos.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]

    print(f"\nKR Shorts: {len(kr_shorts)} → TOP {len(kr_shorts_top10)}")
    print(f"KR Videos: {len(kr_videos)} → TOP {len(kr_videos_top10)}")
    print(f"EN Shorts: {len(en_shorts)} → TOP {len(shorts_top10)}")
    print(f"EN Videos: {len(en_videos)} → TOP {len(videos_top10)}")
    print(f"AI Tool Shorts: {len(aitool_shorts)} → TOP {len(aitool_shorts_top10)}")
    print(f"AI Tool Videos: {len(aitool_videos)} → TOP {len(aitool_videos_top10)}")

    all_items = kr_shorts_top10 + kr_videos_top10 + shorts_top10 + videos_top10 + aitool_shorts_top10 + aitool_videos_top10
    if not all_items:
        print("No data collected"); return

    # LLM 분석 (실패 시 1회 재시도)
    def analyze_list(client, items, label):
        if not items: return
        print(f"Analyzing {label} with LLM...")
        analyses = analyze_with_llm(client, items)
        if not analyses:
            print("  Retrying..."); time.sleep(3)
            analyses = analyze_with_llm(client, items)
        apply_analysis(items, analyses)

    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        analyze_list(client, kr_shorts_top10, "KR Shorts")
        analyze_list(client, kr_videos_top10, "KR Videos")
        analyze_list(client, shorts_top10, "EN Shorts")
        analyze_list(client, videos_top10, "EN Videos")
    else:
        print("OPENAI_API_KEY not set, skipping analysis")
        for lst in [kr_shorts_top10, kr_videos_top10, shorts_top10, videos_top10]:
            apply_analysis(lst, None)

    # 신규 진입 판별
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_file = DAILY_DIR / f"{yesterday}.json"
    prev_ids = set()
    if prev_file.exists():
        prev_data = json.loads(prev_file.read_text(encoding="utf-8"))
        for key in ["shorts_top10", "videos_top10", "kr_shorts_top10", "kr_videos_top10", "top10"]:
            prev_ids.update(item["video_id"] for item in prev_data.get(key, []))
    for item in all_items:
        item["is_new"] = item["video_id"] not in prev_ids

    # 저장 (한국/글로벌 분리)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily = {
        "date": today_str,
        "scanned_at": datetime.now().isoformat(),
        "shorts_top10": shorts_top10,
        "videos_top10": videos_top10,
        "kr_shorts_top10": kr_shorts_top10,
        "kr_videos_top10": kr_videos_top10,
        "aitool_shorts_top10": aitool_shorts_top10,
        "aitool_videos_top10": aitool_videos_top10,
    }
    (DAILY_DIR / f"{today_str}.json").write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {today_str}")

    # 주간/월간 랭킹 업데이트 (첫 실행 시에도 일간 데이터로 채움)
    update_rankings(7, "weekly_shorts.json", 5, "shorts")
    update_rankings(7, "weekly_videos.json", 5, "videos")
    update_rankings(30, "monthly_shorts.json", 5, "shorts")
    update_rankings(30, "monthly_videos.json", 5, "videos")

    # 주간/월간 파일이 비어있으면 일간 데이터로 채우기
    for fname, src_key in [("weekly_shorts.json", "shorts_top10"), ("weekly_videos.json", "videos_top10"),
                           ("monthly_shorts.json", "shorts_top10"), ("monthly_videos.json", "videos_top10")]:
        fp = DATA_DIR / fname
        if fp.exists():
            content = json.loads(fp.read_text(encoding="utf-8"))
            if not content.get("top5"):
                content["top5"] = daily[src_key][:5]
                fp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Filled {fname} with daily data")

    print("Rankings updated!")

if __name__ == "__main__":
    main()
