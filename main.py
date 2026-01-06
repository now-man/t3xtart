import os
import json
import logging
import requests
import uvicorn
import asyncio
import re
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from mcp.server.sse import SseServerTransport

# =========================================================
# 기본 설정
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("t3xtart")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# 🔐 Kakao Token
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ.get("KAKAO_CLIENT_ID"),
        "refresh_token": os.environ.get("KAKAO_REFRESH_TOKEN"),
        "client_secret": os.environ.get("KAKAO_CLIENT_SECRET"),
    }
    try:
        res = requests.post(url, data=data, timeout=5)
        if res.status_code == 200:
            CURRENT_ACCESS_TOKEN = res.json().get("access_token")
            return True
    except Exception as e:
        logger.error(f"Kakao token refresh failed: {e}")
    return False

async def send_kakao(content: str):
    global CURRENT_ACCESS_TOKEN
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def post_request(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 도착!\n\n{content}",
                "link": {"web_url": "https://playmcp.kakao.com"},
            })
        }
        return requests.post(url, headers=headers, data=payload)

    res = post_request(CURRENT_ACCESS_TOKEN)
    
    if res.status_code == 401:
        if refresh_kakao_token():
            res = post_request(CURRENT_ACCESS_TOKEN)
        else:
            return False

    return res.status_code == 200

# =========================================================
# 🧹 데이터 정제 및 유틸리티
# =========================================================
def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r"^```[a-zA-Z]*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    text = text.strip().strip('"').strip("'")
    return text

def truncate_art(text: str, max_lines: int = 15) -> str:
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + "\n...(너무 길어서 잘림 ✂️)"
    return text

def append_disclaimer(user_request: str, plan: str, art: str) -> str:
    is_ascii = "4" in plan or "ASCII" in plan.upper() or "BLOCK" in plan.upper()
    if not is_ascii:
        return art

    has_hangul = bool(re.search(r'[가-힣]', user_request))
    if has_hangul:
        return art + "\n\n(人 > <,,) 한글 아스키아트는 아직 미지원이에요.."
    else:
        return art + "\n\n(人 > <,,) 텍스트 아스키아트는 아직 불완전할 수 있어요."

# =========================================================
# 🧠 MASTER PROMPT (List Format 강제)
# =========================================================
MASTER_INSTRUCTION = """
[ROLE] You are a Witty & High-Quality Text + Emoji Artist.

[YOUR TASK]
Choose ONE style from the 4 categories below based on the user's request and generate the art string.

---
### 1. 한 줄 이모지 아트 (Simple Line) ; 한 줄 이모지 아트 ; 간단한 도트 아트
- Strategy: Combine emojis to represent a concept in one line.
- Ex: "2026" -> 2️⃣0️⃣2️⃣6️⃣
- Ex: "Grass Monkey" -> 🌿🐒
- Ex: "Love Meat" -> 🧑❤️🍖

### 2. 여러 줄 이모지 아트 (Pixel Grid Art) ; 도트 아트 ; 픽셀 아트
- Strategy: Use COLORED BLOCKS (🟩🟨🟧🟥🟦🟪🟫⬛️⬜️) to draw the shape.
- CRITICAL RULE: Differentiate Subject vs Background. Use Negative Space.
- Ex: "Burning Jellyfish":
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊
- Ex: "Ramen" (Bowl + Noodles):
⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛
⬛🍜🟨〰️〰️〰️🟨🍜⬛
⬛🍜🍥🥚🍖🥚🍥🍜⬛
⬛🍜🟨🟨🟨🟨🟨🍜⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛
- Ex: "Snake in Grass" (Subject: Green Blocks, BG: Leaf):
🌿🌿🌿🌿🌿🌿🌿🌿
🌿🌿🟩🟩🟩🟩🌿🌿
🌿🌿🌿🌿🌿🟩🌿🌿
🌿🌿🟩🟩🟩🟩🌿🌿
🌿🌿🟩🌿🌿🌿🌿🌿
🌿🌿🟩🟩👀👅🌿🌿
🌿🌿🌿🌿🌿🌿🌿🌿
- Ex: "Earth" (Contrast BG):
⬛⬛⬛🟦🟦🟦⬛⬛⬛
⬛⬛🟦🟦🟩🟩🟦⬛⬛
⬛🟦🟦🟩🟩🟩🟩🟦⬛
⬛🟦🟦🟦🟩🟦🟦🟦⬛
⬛🟩🟦🟦🟩🟩🟦🟦⬛
⬛⬛🟦🟦🟩🟩🟦⬛⬛
⬛⬛⬛🟦🟦🟦⬛⬛⬛

### 3. 카오모지 (Kaomoji) ; 특수문자 ; 간단한 이모티콘
- Strategy: One-line special characters.
- Ex: "Fighting" -> (ง •̀_•́)ง
- Ex: "Running" -> (งᐖ)ว
- Ex: "Sad" -> (｡•́︿•̀｡)

### 4. 아스키 아트 (ASCII / Braille) ; 특수기호나 점자를 이용한 아트
- Strategy: Use lines, dots, blocks for complex shapes.
- Ex: "Cat Heart":
˚∧＿∧   　+        —̳͟͞͞💗
(  •‿• )つ  —̳͟͞͞ 💗
(つ　 <                —̳͟͞͞💗
｜　 _つ      +  —̳͟͞͞💗
`し´
- Ex: "Braille Clover":
⠀⠀⠀⠀⠀⠀⠀⠀⢔⢕⢄⢄⠆⡄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⡀⠄⢄⠑⡜⢐⠅⢕⠄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠐⢌⠪⠸⠠⡁⠆⢋⠠⠠⡠⡀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⡢⡃⡇⡓⠀⠥⡡⢊⢌⠆⠎⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠃⠃⠁⠀⡁⠈⢪⢪⢪⡂⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠨⡀⠀⠁⠑⠀⠀⠀⠀⠀⠀
---

[CRITICAL RULES FOR RECTANGULAR GRID]
1. 🧱 FILL THE VOID: Do NOT stop drawing in the middle of a line.
   - ❌ BAD (Jagged):
     ❄️❄️❄️❄️
     🏠🎄🏠
     ⛄️⛄️
   - ✅ GOOD (Rectangular):
     ❄️❄️❄️❄️
     🏠🎄🏠❄️ (Filled with Background)
     ⛄️⛄️❄️❄️ (Filled with Background)
2. 📐 EQUAL WIDTH: Every row MUST have the exact same number of emojis.
3. 📏 ALIGNMENT: For ASCII/Box art, use '　' (Full-width space) for alignment.

Choose the best style and generate ONLY the final art string.
"""

PLANNING_PROMPT = """
[STEP 1: PLAN]
Before generating the final art string, explain your plan:
1. Selected Style: (1, 2, 3, or 4)
2. Palette/Char: Which blocks/emojis will you use? & What is the Background emoji? (e.g., "Use 🟩 for Snake, 🌿 for BG")
3. Geometry: How will you draw the shape? (e.g., "Draw a circle in the center")
"""

# =========================================================
# MCP (SSE)
# =========================================================
sse_transport = None

@app.get("/sse")
async def sse(request: Request):
    global sse_transport
    sse_transport = SseServerTransport("/messages")

    async def stream():
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            while True:
                await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/sse")
async def sse_post(request: Request):
    try:
        body = await request.json()
    except:
        return JSONResponse({"status": "error"})

    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "t3xtart", "version": "18.0-list-structure"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "Generate Witty Text Art. Must Plan first.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {"type": "string"},
                            "design_plan": {
                                "type": "string",
                                "description": PLANNING_PROMPT
                            },
                            # [핵심] 문자열(String) 대신 배열(Array) 사용!
                            "art_lines": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "The art grid, row by row. Example: ['⬜️⬜️', '🟥🟥']"
                            }
                        },
                        "required": ["user_request", "design_plan", "art_lines"]
                    }
                }]
            }
        })

    if method == "tools/call":
        args = body["params"]["arguments"]
        user_request = args.get("user_request", "")
        plan = args.get("design_plan", "")
        
        # 1. 리스트 받기
        art_lines = args.get("art_lines", [])
        
        # 2. 리스트를 문자열로 합치기
        # (혹시 LLM이 실수로 문자열을 보냈다면 그대로 씀)
        if isinstance(art_lines, str):
            raw_art = art_lines
        else:
            raw_art = "\n".join(art_lines)

        # 3. 정제
        clean_art = clean_text(raw_art)
        
        # 4. 빈 값 방어 (Plan이라도 보내기)
        if not clean_art.strip():
            logger.warning("⚠️ Empty Art generated. Sending fallback message.")
            clean_art = f"(🎨 열심히 고민했는데 그림을 완성하지 못했어요.. 다시 한번 부탁드려요!)\n\n[AI의 변명]\n{plan}"

        # 5. 안전장치
        safe_art = truncate_art(clean_art, max_lines=15)
        final_art = append_disclaimer(user_request, plan, safe_art)

        logger.info(f"📝 Request: {user_request}")
        logger.info(f"🧠 Plan: {plan}")
        logger.info(f"🎨 Final Art:\n{final_art}")

        success = await send_kakao(final_art)
        result_msg = "✅ 전송 완료" if success else "❌ 전송 실패"

        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"content": [{"type": "text", "text": result_msg}]}
        })

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
