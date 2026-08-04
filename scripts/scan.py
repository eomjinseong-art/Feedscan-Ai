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
    "AI로 돈벌기", "AI 부업 수익화", "ChatGPT 돈버는법", "AI 수익 자동화",
    "AI 부업 추천", "인공지능 수익", "AI 사이드잡", "GPT 부업",
    "AI 자동화 수익", "AI 콘텐츠 수익화"
]
EN_KEYWORDS = [
    "make money with AI", "AI side hustle", "AI passive income",
    "ChatGPT earn money", "AI business ideas 2026", "AI automation income",
    "AI freelance money", "GPT side hustle"
]
MIN_VIEWS = 1000
DAYS_BACK = 7
MAX_RESULTS = 15
TOP_N = 10

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
DAILY_DIR = DATA_DIR / "daily"

# === UTILS ===
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
    if not analyses or len(analyses) != len(items):
        for item in items:
            item["title_ko"] = item["title"] if item["language"] == "ko" else ""
            item["title_en"] = item["title"] if item["language"] == "en" else ""
            item["method"] = "분석 중..."; item["method_en"] = "Analyzing..."
            item["principle"] = ""; item["principle_en"] = ""
            item["requirements"] = ""; item["requirements_en"] = ""
            item["category"] = "기타"
            item["difficulty"] = 3; item["initial_cost"] = 3; item["time_to_profit"] = 3
        return

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
    shorts_results = {}
    videos_results = {}

    # === 쇼츠 수집 ===
    print("=== SHORTS ===")
    print("Scanning KR Shorts...")
    for kw in KR_KEYWORDS[:5]:  # API 쿼터 절약
        items = search_videos(yt, kw, "ko", after, "short", region_code="KR")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in shorts_results:
                info["language"] = "ko"; info["is_short"] = True; shorts_results[vid] = info

    print("Scanning EN Shorts...")
    for kw in EN_KEYWORDS[:5]:
        items = search_videos(yt, kw, "en", after, "short")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in shorts_results:
                info["language"] = "en"; info["is_short"] = True; shorts_results[vid] = info

    # === 일반 영상 수집 ===
    print("\n=== VIDEOS ===")
    print("Scanning KR Videos...")
    for kw in KR_KEYWORDS[:5]:
        items = search_videos(yt, kw, "ko", after, "medium", region_code="KR")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in videos_results:
                info["language"] = "ko"; info["is_short"] = False; videos_results[vid] = info

    print("Scanning EN Videos...")
    for kw in EN_KEYWORDS[:5]:
        items = search_videos(yt, kw, "en", after, "medium")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in videos_results:
                info["language"] = "en"; info["is_short"] = False; videos_results[vid] = info

    # TOP 10 선별
    shorts_top10 = sorted(shorts_results.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    videos_top10 = sorted(videos_results.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]

    print(f"\nShorts collected: {len(shorts_results)} → TOP {len(shorts_top10)}")
    print(f"Videos collected: {len(videos_results)} → TOP {len(videos_top10)}")

    if not shorts_top10 and not videos_top10:
        print("No data collected"); return

    # LLM 분석
    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        if shorts_top10:
            print("Analyzing Shorts with LLM...")
            analyses = analyze_with_llm(client, shorts_top10)
            apply_analysis(shorts_top10, analyses)
        if videos_top10:
            print("Analyzing Videos with LLM...")
            analyses = analyze_with_llm(client, videos_top10)
            apply_analysis(videos_top10, analyses)
    else:
        print("OPENAI_API_KEY not set, skipping analysis")
        apply_analysis(shorts_top10, None)
        apply_analysis(videos_top10, None)

    # 신규 진입 판별
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_file = DAILY_DIR / f"{yesterday}.json"
    prev_ids = set()
    if prev_file.exists():
        prev_data = json.loads(prev_file.read_text(encoding="utf-8"))
        for key in ["shorts_top10", "videos_top10", "top10"]:
            prev_ids.update(item["video_id"] for item in prev_data.get(key, []))
    for item in shorts_top10 + videos_top10:
        item["is_new"] = item["video_id"] not in prev_ids

    # 저장
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily = {
        "date": today_str,
        "scanned_at": datetime.now().isoformat(),
        "shorts_top10": shorts_top10,
        "videos_top10": videos_top10,
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
