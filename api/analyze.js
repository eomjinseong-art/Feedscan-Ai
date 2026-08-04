// Vercel Serverless Function: /api/analyze
// 사용자가 YouTube URL을 입력하면 AI로 분석하여 브리핑 생성

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  if (req.method === 'OPTIONS') return res.status(200).end()
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' })

  const { url } = req.body
  if (!url) return res.status(400).json({ error: 'URL is required' })

  // Extract video ID from YouTube URL
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
    const published = video.snippet.publishedAt?.split('T')[0] || ''
    const channelTitle = video.snippet.channelTitle || ''
    // Mask channel name
    const channelMasked = channelTitle.length > 3 ? channelTitle.slice(0, 3) + '***' : channelTitle + '***'

    // 2. Analyze with OpenAI
    const openaiKey = process.env.OPENAI_API_KEY
    const prompt = `You are an AI monetization analyst. Analyze this YouTube Shorts video about making money with AI.

Title: ${title}
Description: ${description.slice(0, 500)}
Views: ${views}
Channel: ${channelTitle}

Respond in this exact JSON format:
{
  "method": "수익화 방법 한국어 설명 (1줄)",
  "method_en": "Monetization method in English (1 line)",
  "principle": "핵심 원리 한국어 (1-2문장)",
  "principle_en": "Core principle in English (1-2 sentences)",
  "requirements": "필요한 것 한국어",
  "requirements_en": "Requirements in English",
  "title_ko": "제목 한국어 번역",
  "title_en": "Title in English",
  "category": "One of: 제휴마케팅, 디지털상품, 서비스대행, 콘텐츠채널, 드랍쉬핑, 강의판매, 자동화에이전시, 기타",
  "difficulty": 1-5 integer,
  "initial_cost": 1-5 integer,
  "time_to_profit": 1-5 integer
}

Only respond with valid JSON, nothing else.`

    const aiRes = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${openaiKey}` },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        response_format: { type: 'json_object' }
      })
    })

    const aiData = await aiRes.json()
    const analysis = JSON.parse(aiData.choices[0].message.content)

    // 3. Return combined result
    return res.status(200).json({
      video_id: videoId,
      title: title,
      title_ko: analysis.title_ko || title,
      title_en: analysis.title_en || title,
      channel_masked: channelMasked,
      views,
      likes,
      published,
      language: /[가-힣]/.test(title) ? 'ko' : 'en',
      category: analysis.category || '기타',
      method: analysis.method || '',
      method_en: analysis.method_en || '',
      principle: analysis.principle || '',
      principle_en: analysis.principle_en || '',
      requirements: analysis.requirements || '',
      requirements_en: analysis.requirements_en || '',
      difficulty: analysis.difficulty || 3,
      initial_cost: analysis.initial_cost || 3,
      time_to_profit: analysis.time_to_profit || 3,
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
