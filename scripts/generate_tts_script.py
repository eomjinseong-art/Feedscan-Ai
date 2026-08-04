"""
TTS 대본 자동 생성기
- 오늘의 TOP 10 데이터를 읽어서
- 틱톡/쇼츠용 읽기 대본(한국어 + 영어) 생성
- public/tts/ 폴더에 저장
"""
import os, json
from datetime import datetime
from pathlib import Path
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
TTS_DIR = BASE_DIR / "public" / "tts"

def get_latest_daily():
    """최신 일간 데이터 로드"""
    daily_dir = DATA_DIR / "daily"
    today = datetime.now().strftime("%Y-%m-%d")
    fp = daily_dir / f"{today}.json"
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    # 오늘 파일 없으면 최신 파일 찾기
    files = sorted(daily_dir.glob("*.json"), reverse=True)
    if files:
        return json.loads(files[0].read_text(encoding="utf-8"))
    return None

def generate_scripts(client, data):
    """한국어/영어 TTS 대본 생성"""
    date = data["date"]
    items = data["top10"]

    # 순위 요약 텍스트
    ranking_text = ""
    for i, item in enumerate(items[:5], 1):  # TOP 5만 읽기 (쇼츠 길이 제한)
        ranking_text += f"{i}위: {item['title']} (조회수 {item['views']:,})\n"
        ranking_text += f"   방법: {item.get('method','')}\n"

    # 한국어 대본 생성
    ko_prompt = f"""당신은 틱톡/유튜브 쇼츠 나레이터입니다. 아래 AI 수익화 트렌드 TOP 5를 15초~30초 분량의 짧은 대본으로 만들어주세요.

규칙:
- 첫 문장은 강력한 후킹 (예: "오늘 AI로 돈 버는 트렌드 1위가 바뀌었습니다!")
- 각 순위를 1~2문장으로 간결하게
- 마지막에 "자세한 내용은 프로필 링크에서 확인하세요" CTA
- 자연스럽게 읽히도록 구어체
- 총 150자~250자 이내

날짜: {date}
데이터:
{ranking_text}

대본만 출력하세요. 다른 설명 없이."""

    en_prompt = f"""You are a TikTok/YouTube Shorts narrator. Create a 15-30 second script for the AI monetization trend TOP 5 below.

Rules:
- First sentence: strong hook (e.g., "The #1 AI money-making trend just changed!")
- Each rank in 1-2 concise sentences
- End with CTA: "Check the link in bio for full details"
- Conversational, natural speaking tone
- Total 100-180 words

Date: {date}
Data:
{ranking_text}

Output ONLY the script. No other explanation."""

    try:
        ko_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": ko_prompt}],
            temperature=0.7, max_tokens=500
        )
        ko_script = ko_resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERR] KO script: {e}")
        ko_script = ""

    try:
        en_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": en_prompt}],
            temperature=0.7, max_tokens=500
        )
        en_script = en_resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERR] EN script: {e}")
        en_script = ""

    return ko_script, en_script

def main():
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY not set, skipping TTS script generation")
        return

    data = get_latest_daily()
    if not data:
        print("No daily data found")
        return

    client = OpenAI(api_key=OPENAI_API_KEY)
    ko_script, en_script = generate_scripts(client, data)

    # 저장
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    today = data["date"]
    now = datetime.now().strftime("%H%M")

    output = {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "ko_script": ko_script,
        "en_script": en_script,
        "source_data": f"/data/daily/{today}.json",
        "usage_note": "이 대본을 TTS 도구(ElevenLabs, OpenAI TTS 등)에 넣어 음성 생성 후 영상에 합성하세요."
    }

    filepath = TTS_DIR / f"{today}_{now}.json"
    filepath.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # 최신 대본을 latest.json으로도 저장 (웹에서 접근용)
    latest_path = TTS_DIR / "latest.json"
    latest_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"TTS scripts generated: {filepath.name}")
    print(f"KO ({len(ko_script)} chars): {ko_script[:80]}...")
    print(f"EN ({len(en_script)} chars): {en_script[:80]}...")

if __name__ == "__main__":
    main()
