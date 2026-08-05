"""
FeedScan AI - 일간 스캐너 v6
- YouTube Data API로 쇼츠 + 일반 영상 분리 수집
- 콘텐츠 필터링: 블랙리스트 + AI 관련성 검증 + 인도 차단
- OpenAI API로 브리핑 + 번역 자동 생성
- 주간/월간 랭킹 즉시 생성
"""
import os, json, time, re
from datetime import datetime, timedelta
from pathlib import Path
from googleapiclient.discovery import build
from openai import OpenAI

# === CONFIG ===
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

KR_KEYWORDS = [
    "AI 부업", "AI 부업 추천", "ChatGPT 돈버는법", "AI 수익화", "AI 재택",
    "AI 온라인 알바", "인공지능 부업", "AI 자동화 수익", "GPT 부업", "AI 투잡",
    "AI 월 100만원", "AI 수익 인증", "AI 무자본 부업", "AI 프리랜서",
    "AI 유튜브 수익", "AI 콘텐츠 수익", "AI 영상 자동화", "AI 쇼츠 수익",
    "AI 음악 수익", "AI 그림 판매",
    "쿠팡파트너스", "링크프라이스", "텐핑", "애드픽",
    "올리브영 큐레이터", "무신사 큐레이터", "에이블리 큐레이터",
    "삼성전자 ACE", "오늘의집 큐레이터", "컬리 큐레이터",
    "마이리얼트립 파트너", "클룩 어필리에이트", "세시간전 크리에이터",
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
    "ChatGPT 사용법", "미드저니 사용법", "힉스필드", "AI 툴 추천",
    "Runway 사용법", "Suno AI", "Claude 활용", "Cursor AI",
    "Gemini 활용법", "신규 AI 툴", "AI 영상편집", "AI 이미지 생성",
    "AI 앱 추천", "AI 툴 리뷰", "AI 신규 서비스",
    "Midjourney tutorial", "ChatGPT tips 2026", "AI tools 2026",
    "Runway ML tutorial", "Heygen tutorial", "Sora AI",
    "Kling AI", "best AI tools", "AI workflow automation",
    "Claude AI tips", "Cursor AI coding", "Gamma AI",
    "new AI tool", "best AI tools 2026", "AI tool review",
    "AI app of the week", "must have AI tools"
]

MIN_VIEWS = 500
DAYS_BACK = 30
MAX_RESULTS = 25
TOP_N = 10
SHORTS_MAX_SEC = 180

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
DAILY_DIR = DATA_DIR / "daily"

# === CONTENT FILTERING ===
# 제목 블랙리스트 (뮤직비디오, 예고편, 영화, 게임, 정치, 폭력 등)
TITLE_BLACKLIST = [
    # 뮤직비디오 / 예고편 / 엔터테인먼트
    "official mv", "music video", "official video", "m/v", "뮤비", "뮤직비디오",
    "trailer", "teaser", "예고편", "티저", "official trailer",
    "avengers", "어벤저스", "marvel", "마블", "dc comics",
    "movie clip", "film scene", "영화", "드라마",
    # 정치 / 정부 / 폭력 / 성 / 학대
    "modi", "government", "정부", "대통령", "국회", "정치",
    "trump", "biden", "election", "선거", "투표",
    "violence", "폭력", "abuse", "학대", "sexual", "성인",
    "war", "전쟁", "military", "군사", "terrorism", "테러",
    "murder", "살인", "crime", "범죄", "drug", "마약",
    # 게임 / 스포츠 (AI 수익화와 무관)
    "gameplay", "walkthrough", "let's play", "esports",
    "highlights", "goals", "match",
    # 종교
    "sermon", "prayer", "설교", "기도",
    # ASMR / 먹방 (AI 무관)
    "asmr", "mukbang", "먹방",
]

# 인도 관련 차단 (힌디어 + 키워드)
INDIA_BLACKLIST = [
    "india", "indian", "hindi", "bollywood", "desi",
    "rupee", "lakh", "crore", "भारत", "हिंदी",
]

# AI 관련성 키워드 (제목+설명에 최소 1개 포함 필수)
AI_RELEVANCE_KEYWORDS = [
    # 영어
    "ai", "artificial intelligence", "chatgpt", "gpt", "openai",
    "midjourney", "stable diffusion", "dall-e", "claude", "gemini",
    "automation", "automate", "passive income", "side hustle",
    "make money", "earn", "income", "monetize", "monetization",
    "affiliate", "dropshipping", "digital product", "freelance",
    "online business", "remote work", "no code", "saas",
    "cursor", "runway", "suno", "heygen", "kling", "sora",
    "prompt", "llm", "machine learning", "deep learning",
    # 한국어
    "인공지능", "자동화", "수익", "부업", "돈벌기", "돈버는",
    "수익화", "재택", "투잡", "프리랜서", "제휴", "파트너스",
    "스마트스토어", "전자책", "블로그", "쿠팡", "큐레이터",
    "챗지피티", "미드저니", "클로드", "제미나이",
]

def has_korean(text):
    return bool(re.search('[가-힣]', text))

def has_indian_script(text):
    """힌디어/데바나가리/벵골어/구자라트어/타밀어 등 인도 문자 감지"""
    return bool(re.search('[\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F]', text))

def has_arabic(text):
    """아랍어 문자 감지"""
    return bool(re.search('[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]', text))

def is_blacklisted(title, description=""):
    """블랙리스트 키워드 포함 여부 확인"""
    combined = (title + " " + description).lower()
    for kw in TITLE_BLACKLIST:
        if kw in combined:
            return True
    return False

def is_india_content(title, description=""):
    """인도 관련 콘텐츠 여부"""
    combined = (title + " " + description).lower()
    # 인도 문자 포함
    if has_indian_script(title) or has_indian_script(description):
        return True
    # 인도 키워드 포함
    for kw in INDIA_BLACKLIST:
        if kw in combined:
            return True
    return False

def has_ai_relevance(title, description=""):
    """AI/수익화 관련성 검증 - 최소 1개 키워드 포함 필수"""
    combined = (title + " " + description).lower()
    for kw in AI_RELEVANCE_KEYWORDS:
        if kw in combined:
            return True
    return False

def passes_content_filter(title, description=""):
    """모든 필터를 통과하는지 확인"""
    # 1. 블랙리스트 체크
    if is_blacklisted(title, description):
        return False
    # 2. 인도 콘텐츠 차단
    if is_india_content(title, description):
        return False
    # 3. 아랍어 차단
    if has_arabic(title):
        return False
    # 4. AI 관련성 검증
    if not has_ai_relevance(title, description):
        return False
    return True

def mask_channel(name):
    if len(name) <= 2: return name[0] + "***"
    if len(name) <= 5: return name[:2] + "***"
    return name[:3] + "***"

def parse_duration_seconds(duration_str):
    """ISO 8601 duration (PT1M30S) → seconds"""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h*3600 + m*60 + s

def search_videos(yt, kw, lang, after, duration_filter=None, region_code=None):
    try:
        params = dict(part="snippet", q=kw, type="video",
            order="viewCount", publishedAfter=after,
            relevanceLanguage=lang, maxResults=MAX_RESULTS)
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
        try:
            r = yt.videos().list(part="statistics,snippet,contentDetails",
                                 id=",".join(ids[i:i+50])).execute()
            for item in r.get("items", []):
                s = item.get("statistics", {})
                duration = item.get("contentDetails", {}).get("duration", "")
                seconds = parse_duration_seconds(duration)
                title = item["snippet"]["title"]
                desc = item["snippet"].get("description", "")[:300]

                # 콘텐츠 필터 적용
                if not passes_content_filter(title, desc):
                    continue

                details[item["id"]] = {
                    "video_id": item["id"],
                    "title": title,
                    "channel_masked": mask_channel(item["snippet"]["channelTitle"]),
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "published": item["snippet"]["publishedAt"][:10],
                    "description": desc,
                    "is_short": seconds <= SHORTS_MAX_SEC,
                    "duration_sec": seconds,
                }
        except Exception as e:
            print(f"  [ERR details] {e}")
    return details

# === LLM ANALYSIS ===
def analyze_with_llm(client, items, context="AI monetization"):
    titles_info = "\n".join([
        f"{i+1}. [{item.get('language','en').upper()}] \"{item['title']}\" (views: {item['views']}, desc: {item.get('description','')})"
        for i, item in enumerate(items)
    ])

    if "tool" in context.lower():
        category_options = '"AI코딩", "AI영상", "AI이미지", "AI음악", "AI문서", "AI자동화", "AI비즈니스", "기타"'
    else:
        category_options = '"제휴마케팅", "디지털상품", "서비스대행", "콘텐츠채널", "드랍쉬핑", "강의판매", "자동화에이전시", "기타"'

    prompt = f"""You are an AI trend analyst. Analyze these YouTube videos about {context}.

For EACH video, provide:
1. title_ko: Korean translation (if already Korean, keep as-is)
2. title_en: English translation (if already English, keep as-is)
3. method: Main method/topic in 1 line (Korean)
4. method_en: Main method/topic in 1 line (English)
5. principle: Core principle, 1-2 sentences (Korean)
6. principle_en: Core principle, 1-2 sentences (English)
7. requirements: What's needed - cost + tools (Korean)
8. requirements_en: What's needed - cost + tools (English)
9. category: ONE of: {category_options}
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
            item["title_ko"] = item["title"] if item.get("language") == "ko" else ""
            item["title_en"] = item["title"] if item.get("language") == "en" else ""
            item["method"] = "분석 중..."; item["method_en"] = "Analyzing..."
            item["principle"] = ""; item["principle_en"] = ""
            item["requirements"] = ""; item["requirements_en"] = ""
            item["category"] = "기타"
            item["difficulty"] = 3; item["initial_cost"] = 3; item["time_to_profit"] = 3
        return

    if len(analyses) != len(items):
        print(f"  [WARN] LLM returned {len(analyses)} items, expected {len(items)}.")

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

    # description/duration_sec 제거
    for item in items:
        item.pop("description", None)
        item.pop("duration_sec", None)

# === RANKINGS ===
def update_rankings(period_days, filename, top_n, content_type=None):
    data = {}
    today = datetime.now()
    all_prev_ids = set()

    for i in range(period_days):
        fp = DAILY_DIR / f"{(today - timedelta(days=i)).strftime('%Y-%m-%d')}.json"
        if fp.exists():
            day_data = json.loads(fp.read_text(encoding="utf-8"))
            for key in ["shorts_top10", "videos_top10", "kr_shorts_top10", "kr_videos_top10",
                        "aitool_shorts_top10", "aitool_videos_top10", "top10"]:
                for item in day_data.get(key, []):
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

    kr_shorts = {}
    kr_videos = {}
    en_shorts = {}
    en_videos = {}

    # ============================================================
    # 1. 한국 수집
    # ============================================================
    print("=== KR COLLECTION ===")
    for kw in KR_KEYWORDS:
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

    # ============================================================
    # 2. 글로벌(US) 수집
    # ============================================================
    print("\n=== US COLLECTION ===")
    for kw in EN_KEYWORDS:
        items = search_videos(yt, kw, "en", after, None, region_code="US")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS:
                info["language"] = "en"
                if info["is_short"]:
                    if vid not in en_shorts: en_shorts[vid] = info
                else:
                    if vid not in en_videos: en_videos[vid] = info
    print(f"  US shorts: {len(en_shorts)}, US videos: {len(en_videos)}")

    # ============================================================
    # 3. AI Tool 수집
    # ============================================================
    print("\n=== AI TOOL COLLECTION ===")
    aitool_shorts = {}
    aitool_videos = {}
    for kw in AITOOL_KEYWORDS[15:]:
        items = search_videos(yt, kw, "en", after, None, region_code="US")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS:
                info["language"] = "en"
                if info["is_short"]:
                    if vid not in aitool_shorts: aitool_shorts[vid] = info
                else:
                    if vid not in aitool_videos: aitool_videos[vid] = info
    for kw in AITOOL_KEYWORDS[:15]:
        items = search_videos(yt, kw, "ko", after, None, region_code="KR")
        ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        for vid, info in get_details(yt, ids).items():
            if info["views"] >= MIN_VIEWS:
                info["language"] = "ko" if has_korean(info["title"]) else "en"
                if info["is_short"]:
                    if vid not in aitool_shorts: aitool_shorts[vid] = info
                else:
                    if vid not in aitool_videos: aitool_videos[vid] = info
    print(f"  AI Tool shorts: {len(aitool_shorts)}, videos: {len(aitool_videos)}")

    # ============================================================
    # TOP 10 선별
    # ============================================================
    kr_shorts_top10 = sorted(kr_shorts.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    kr_videos_top10 = sorted(kr_videos.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    shorts_top10 = sorted(en_shorts.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    videos_top10 = sorted(en_videos.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    aitool_shorts_top10 = sorted(aitool_shorts.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]
    aitool_videos_top10 = sorted(aitool_videos.values(), key=lambda x: x["views"], reverse=True)[:TOP_N]

    print(f"\n=== RESULTS ===")
    print(f"KR Shorts: {len(kr_shorts)} -> TOP {len(kr_shorts_top10)}")
    print(f"KR Videos: {len(kr_videos)} -> TOP {len(kr_videos_top10)}")
    print(f"EN Shorts: {len(en_shorts)} -> TOP {len(shorts_top10)}")
    print(f"EN Videos: {len(en_videos)} -> TOP {len(videos_top10)}")
    print(f"AI Tool Shorts: {len(aitool_shorts)} -> TOP {len(aitool_shorts_top10)}")
    print(f"AI Tool Videos: {len(aitool_videos)} -> TOP {len(aitool_videos_top10)}")

    all_items = kr_shorts_top10 + kr_videos_top10 + shorts_top10 + videos_top10 + aitool_shorts_top10 + aitool_videos_top10
    if not all_items:
        print("No data collected"); return

    # ============================================================
    # LLM 분석
    # ============================================================
    def analyze_list(client, items, label, context="AI monetization"):
        if not items:
            print(f"  {label}: empty, skipping")
            return
        print(f"  Analyzing {label} ({len(items)} items)...")
        analyses = analyze_with_llm(client, items, context)
        if not analyses:
            print(f"  Retrying {label}..."); time.sleep(3)
            analyses = analyze_with_llm(client, items, context)
        apply_analysis(items, analyses)
        print(f"  {label}: done")

    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        analyze_list(client, kr_shorts_top10, "KR Shorts")
        analyze_list(client, kr_videos_top10, "KR Videos")
        analyze_list(client, shorts_top10, "EN Shorts")
        analyze_list(client, videos_top10, "EN Videos")
        analyze_list(client, aitool_shorts_top10, "AI Tool Shorts", "AI tools and tutorials")
        analyze_list(client, aitool_videos_top10, "AI Tool Videos", "AI tools and tutorials")
    else:
        print("OPENAI_API_KEY not set, skipping analysis")
        for lst in [kr_shorts_top10, kr_videos_top10, shorts_top10, videos_top10,
                    aitool_shorts_top10, aitool_videos_top10]:
            apply_analysis(lst, None)

    # 신규 진입 판별
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_file = DAILY_DIR / f"{yesterday}.json"
    prev_ids = set()
    if prev_file.exists():
        prev_data = json.loads(prev_file.read_text(encoding="utf-8"))
        for key in ["shorts_top10", "videos_top10", "kr_shorts_top10", "kr_videos_top10",
                    "aitool_shorts_top10", "aitool_videos_top10", "top10"]:
            prev_ids.update(item["video_id"] for item in prev_data.get(key, []))
    for item in all_items:
        item["is_new"] = item["video_id"] not in prev_ids

    # 저장
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
    (DAILY_DIR / f"{today_str}.json").write_text(
        json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {today_str}")

    # 주간/월간 랭킹
    update_rankings(7, "weekly_shorts.json", 5, "shorts")
    update_rankings(7, "weekly_videos.json", 5, "videos")
    update_rankings(30, "monthly_shorts.json", 5, "shorts")
    update_rankings(30, "monthly_videos.json", 5, "videos")

    # 주간/월간 비어있으면 일간 데이터로 채우기
    for fname, src_key in [("weekly_shorts.json", "shorts_top10"), ("weekly_videos.json", "videos_top10"),
                           ("monthly_shorts.json", "shorts_top10"), ("monthly_videos.json", "videos_top10")]:
        fp = DATA_DIR / fname
        if fp.exists():
            content = json.loads(fp.read_text(encoding="utf-8"))
            if not content.get("top5"):
                content["top5"] = daily[src_key][:5]
                fp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Filled {fname} with daily data")

    print("Done!")

if __name__ == "__main__":
    main()
