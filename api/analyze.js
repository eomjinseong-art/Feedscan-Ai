// Vercel Serverless Function: /api/analyze
// 사용자가 YouTube URL을 입력하면 AI로 깊이 있는 수익화 분석 생성

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  if (req.method === 'OPTIONS') return res.status(200).end()
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' })

  const { url } = req.body
  if (!url) return res.status(400).json({ error: 'URL is required' })

  const videoId = extractVideoId(url)
  if (!videoId) return res.status(400).json({ error: 'Invalid YouTube URL' })

  try {
    // 1. Get video metadata from YouTube API
    const ytApiKey = process.env.YOUTUBE_API_KEY
    const ytRes = await fetch(`https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=${videoId}&key=${ytApiKey}`)
    const ytData = await ytRes.json()

    if (!ytData.items || ytData.items.length === 0) {
      return res.status(404).json({ error: 'Video not found' })
    }

    const video = ytData.items[0]
    const title = video.snippet.title
    const description = video.snippet.description
    const views = parseInt(video.statistics.viewCount || '0')
    const likes = parseInt(video.statistics.likeCount || '0')
    const commentCount = parseInt(video.statistics.commentCount || '0')
    const published = video.snippet.publishedAt?.split('T')[0] || ''
    const channelTitle = video.snippet.channelTitle || ''
    const channelMasked = channelTitle.length > 3 ? channelTitle.slice(0, 3) + '***' : channelTitle + '***'
    const tags = (video.snippet.tags || []).slice(0, 10).join(', ')

    // 2. Deep analysis with OpenAI
    const openaiKey = process.env.OPENAI_API_KEY
    const prompt = `You are a world-class content monetization analyst. Analyze this YouTube video from a pure business/monetization perspective. Be specific, data-driven, and brutally honest.

VIDEO DATA:
- Title: ${title}
- Description: ${description.slice(0, 800)}
- Views: ${views.toLocaleString()}
- Likes: ${likes.toLocaleString()}
- Comments: ${commentCount.toLocaleString()}
- Published: ${published}
- Channel: ${channelTitle}
- Tags: ${tags}

ANALYZE AND RESPOND IN THIS EXACT JSON FORMAT:
{
  "title_ko": "제목 한국어 번역",
  "title_en": "Title in English (keep original if already English)",
  "category": "One of: 제휴마케팅, 디지털상품, 서비스대행, 콘텐츠채널, 드랍쉬핑, 강의판매, 자동화에이전시, 기타",
  "monetization_method": "이 영상/채널의 수익화 방식 (한국어, 구체적으로 2-3문장)",
  "monetization_method_en": "Monetization method (English, specific 2-3 sentences)",
  "core_principle": "이 콘텐츠가 돈이 되는 핵심 메커니즘 (한국어, 구체적으로)",
  "core_principle_en": "Core monetization mechanism (English, specific)",
  "requirements": "시작에 필요한 것: 비용, 도구, 스킬 구체적으로 (한국어)",
  "requirements_en": "What you need to start: cost, tools, skills specifically (English)",
  "revenue_potential": "예상 월 수익 범위와 근거 (한국어, 예: '월 $500~2,000 - 이유: ...')",
  "revenue_potential_en": "Estimated monthly revenue range with reasoning (English)",
  "competition_level": "이 니치의 경쟁 강도와 이유 (한국어)",
  "competition_level_en": "Competition level in this niche and why (English)",
  "reproducibility": "일반인이 따라할 수 있는지, 구체적 장벽은 무엇인지 (한국어)",
  "reproducibility_en": "Can an average person replicate this? What are the specific barriers? (English)",
  "growth_outlook": "이 유형 콘텐츠의 향후 6개월 전망 (한국어)",
  "growth_outlook_en": "6-month outlook for this content type (English)",
  "key_insight": "이 영상이 성공한 (또는 실패한) 진짜 이유 한 줄 (한국어)",
  "key_insight_en": "The real reason this video succeeded (or failed) - one line (English)",
  "action_roadmap": ["1단계: ...", "2단계: ...", "3단계: ..."],
  "action_roadmap_en": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
  "ai_relevance": "높음/중간/낮음 - AI 수익화와의 관련도",
  "ai_relevance_en": "High/Medium/Low - relevance to AI monetization",
  "difficulty": 1-5,
  "initial_cost": 1-5,
  "time_to_profit": 1-5,
  "revenue_score": 1-10,
  "verdict": "한 줄 최종 판단 - 냉정하고 솔직하게 (한국어)",
  "verdict_en": "One-line final verdict - cold and honest (English)"
}

RULES:
- Be brutally honest. If this is a scam or unrealistic, say so clearly.
- If revenue potential is high, explain exactly why with evidence.
- Numbers must be realistic and based on market data.
- Never use vague language like "could be good" - be specific.
- If the video is not about making money (e.g., cat video, music), analyze it from "how could someone monetize THIS type of content" perspective.
- Only respond with valid JSON, nothing else.`

    const aiRes = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${openaiKey}` },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.4,
        max_tokens: 2000,
        response_format: { type: 'json_object' }
      })
    })

    const aiData = await aiRes.json()
    if (!aiData.choices || !aiData.choices[0]) {
      return res.status(500).json({ error: 'AI analysis failed' })
    }
    const analysis = JSON.parse(aiData.choices[0].message.content)

    // 3. Return combined result
    return res.status(200).json({
      video_id: videoId,
      title,
      title_ko: analysis.title_ko || title,
      title_en: analysis.title_en || title,
      channel_masked: channelMasked,
      views,
      likes,
      published,
      language: /[가-힣]/.test(title) ? 'ko' : 'en',
      category: analysis.category || '기타',
      monetization_method: analysis.monetization_method || '',
      monetization_method_en: analysis.monetization_method_en || '',
      core_principle: analysis.core_principle || '',
      core_principle_en: analysis.core_principle_en || '',
      requirements: analysis.requirements || '',
      requirements_en: analysis.requirements_en || '',
      revenue_potential: analysis.revenue_potential || '',
      revenue_potential_en: analysis.revenue_potential_en || '',
      competition_level: analysis.competition_level || '',
      competition_level_en: analysis.competition_level_en || '',
      reproducibility: analysis.reproducibility || '',
      reproducibility_en: analysis.reproducibility_en || '',
      growth_outlook: analysis.growth_outlook || '',
      growth_outlook_en: analysis.growth_outlook_en || '',
      key_insight: analysis.key_insight || '',
      key_insight_en: analysis.key_insight_en || '',
      action_roadmap: analysis.action_roadmap || [],
      action_roadmap_en: analysis.action_roadmap_en || [],
      ai_relevance: analysis.ai_relevance || '중간',
      ai_relevance_en: analysis.ai_relevance_en || 'Medium',
      difficulty: analysis.difficulty || 3,
      initial_cost: analysis.initial_cost || 3,
      time_to_profit: analysis.time_to_profit || 3,
      revenue_score: analysis.revenue_score || 5,
      verdict: analysis.verdict || '',
      verdict_en: analysis.verdict_en || '',
    })
  } catch (err) {
    console.error(err)
    return res.status(500).json({ error: 'Analysis failed. Please try again.' })
  }
}

function extractVideoId(url) {
  const patterns = [
    /youtube\.com\/shorts\/([a-zA-Z0-9_-]+)/,
    /youtu\.be\/([a-zA-Z0-9_-]+)/,
    /youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)/,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]+)/,
  ]
  for (const p of patterns) {
    const m = url.match(p)
    if (m) return m[1]
  }
  return null
}
