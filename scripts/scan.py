"""
AI 수익화 쇼츠 일간 스캐너 v2
- YouTube Data API로 수집
- OpenAI API로 브리핑(수익화방법/핵심원리/필요한것/유형태그) + 번역 자동 생성
"""
import os, json, time
from datetime import datetime, timedelta
from pathlib import Path
from googleapiclient.discovery import build
from openai import OpenAI

# === CONFIG ===
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

KR_KEYWORDS = ["AI로 돈벌기", "AI 부업 수익화", "ChatGPT 돈버는법", "AI 수익 자동화"]
EN_KEYWORDS = ["make money with AI", "AI side hustle", "AI passive income", "ChatGPT earn money"]
MIN_VIEWS = 5000
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

def search_shorts(yt, kw, lang, after):
    try:
        r = yt.search().list(part="snippet", q=kw, type="video", videoDuration="short",
            order="viewCount", publishedAfter=after, relevanceLanguage=lang, maxResults=MAX_RESULTS).execute()
        return r.get("items", [])
    except Exception as e:
        print(f"  [ERR] {kw}: {e}"); return []

def get_details(yt, ids):
    if not ids: return {}
    details = {}
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="statistics,snippet", id=",".join(ids[i:i+50])).execute()
        for item in r.get("items", []):
            s = item.get("statistics", {})
            details[item["id"]] = {
                "video_id": item["id"],
                "title": item["snippet"]["title"],
                "channel_masked": mask_channel(item["snippet"]["channelTitle"]),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "published": item["snippet"]["publishedAt"][:10],
                "description": item["snippet"].get("description", "")[:300],
            }
    return details

# === LLM ANALYSIS ===
def analyze_with_llm(client, items):
    """LLM으로 각 영상에 대해 브리핑+번역+태그 생성"""
    titles_info = "\n".join([
        f"{i+1}. [{item['language'].upper()}] \"{item['title']}\" (views: {item['views']}, desc: {item.get('description','')})"
        for i, item in enumerate(items)
    ])

    prompt = f"""You are an AI monetization trend analyst. Analyze these YouTube Shorts about making money with AI.

For EACH video, provide:
1. title_ko: Korean translation of title (if already Korean, keep as-is)
2. title_en: English translation of title (if already English, keep as-is)
3. method: The monetization method in 1 line (Korean)
4. method_en: The monetization method in 1 line (English)
5. principle: Core principle of how money is made, 1-2 sentences (Korean)
6. principle_en: Core principle of how money is made, 1-2 sentences (English)
7. requirements: What's needed to start - cost + tools (Korean)
8. requirements_en: What's needed to start - cost + tools (English)
9. category: ONE of these tags: "제휴마케팅", "디지털상품", "서비스대행", "콘텐츠채널", "드랍쉬핑", "강의판매", "자동화에이전시", "기타"
10. difficulty: 1-5 (1=very easy, 5=very hard)
11. initial_cost: 1-5 (1=free, 5=expensive)
12. time_to_profit: 1-5 (1=immediate, 5=6months+)

Videos:
{titles_info}

Respond in valid JSON array format. Each element corresponds to one video in order.
Do NOT add any text outside the JSON array.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        content = response.choices[0].message.content.strip()
        # JSON 파싱 (코드블록 제거)
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        analyses = json.loads(content)
        return analyses
    except Exception as e:
        print(f"  [LLM ERR] {e}")
        return None

def apply_analysis(items, analyses):
    """분석 결과를 아이템에 병합"""
    if not analyses or len(analyses) != len(items):
        # 분석 실패 시 기본값
        for item in items:
            item["title_ko"] = item["title"] if item["language"] == "ko" else ""
            item["title_en"] = item["title"] if item["language"] == "en" else ""
            item["method"] = "분석 중..."
            item["method_en"] = "Analyzing..."
            item["principle"] = ""
            item["principle_en"] = ""
            item["requirements"] = ""
            item["requirements_en"] = ""
            item["category"] = "기타"
            item["difficulty"] = 3
            item["initial_cost"] = 3
            item["time_to_profit"] = 3
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

    # description 제거 (저장 불필요)
    for item in items:
        item.pop("description", None)

# === RANKINGS ===
def update_rankings(period_days, filename, top_n):
    data = {}
    today = datetime.now()
    all_prev_ids = set()

    for i in range(period_days):
        fp = DAILY_DIR / f"{(today - timedelta(days=i)).strftime('%Y-%m-%d')}.json"
        if fp.exists():
            day_data = json.loads(fp.read_text(encoding="utf-8"))
            for item in day_data.get("top10", []):
                vid = item["video_id"]
                if i > 0:
                    all_prev_ids.add(vid)
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
    results = {}

    print("Scanning KR...")
    for kw in KR_KEYWORDS:
        items = search_shorts(yt, kw, "ko", after)
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in results:
                info["language"] = "ko"; results[vid] = info

    print("Scanning EN...")
    for kw in EN_KEYWORDS:
        items = search_shorts(yt, kw, "en", after)
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS and vid not in results:
                info["language"] = "en"; results[vid] = info

    top10 = sorted(results.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    if not top10:
        print("No data collected"); return

    # LLM 분석
    if OPENAI_API_KEY:
        print("Analyzing with LLM...")
        client = OpenAI(api_key=OPENAI_API_KEY)
        analyses = analyze_with_llm(client, top10)
        apply_analysis(top10, analyses)
    else:
        print("OPENAI_API_KEY not set, skipping analysis")
        apply_analysis(top10, None)

    # 신규 진입 판별
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_file = DAILY_DIR / f"{yesterday}.json"
    prev_ids = set()
    if prev_file.exists():
        prev_data = json.loads(prev_file.read_text(encoding="utf-8"))
        prev_ids = {item["video_id"] for item in prev_data.get("top10", [])}
    for item in top10:
        item["is_new"] = item["video_id"] not in prev_ids

    # 저장
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily = {"date": today_str, "scanned_at": datetime.now().isoformat(), "top10": top10}
    (DAILY_DIR / f"{today_str}.json").write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {today_str} ({len(top10)} items)")

    update_rankings(7, "weekly.json", 5)
    update_rankings(30, "monthly.json", 5)
    print("Done!")

if __name__ == "__main__":
    main()
