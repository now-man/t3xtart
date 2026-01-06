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
# 🔐 Kakao Token Management
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
# 🧹 데이터 정제 (가위질 로직 추가)
# =========================================================

def clean_text(text: str) -> str:
    """Markdown 및 불필요한 기호 제거"""
    if not text: return ""
    text = re.sub(r"^```[a-zA-Z]*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    text = text.strip().strip('"').strip("'")
    return text

def truncate_art(text: str, max_lines: int = 15) -> str:
    """
    [핵심 수정] AI가 폭주해서 너무 길게 그리면 강제로 자름.
    카톡 화면을 고려해 15~20줄이 적당함.
    """
    lines = text.splitlines()
    if len(lines) > max_lines:
        logger.warning(f"⚠️ Art too long ({len(lines)} lines). Truncating.")
        # 잘린 부분 알림
        return "\n".join(lines[:max_lines]) + "\n...(너무 길어서 잘림 ✂️)"
    return text

# =========================================================
# 🧠 MASTER ART PROMPT (길이 제한 규칙 추가)
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
                "serverInfo": {"name": "t3xtart", "version": "14.0-safety-cut"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "Generate Witty & Rectangular Text Art. Must Plan first.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {"type": "string"},
                            "design_plan": {
                                "type": "string",
                                "description": PLANNING_PROMPT
                            },
                            "final_art_grid": {
                                "type": "string",
                                "description": MASTER_INSTRUCTION + "\n\nOUTPUT ONLY THE ART STRING."
                            }
                        },
                        "required": ["user_request", "design_plan", "final_art_grid"]
                    }
                }]
            }
        })

    if method == "tools/call":
        args = body["params"]["arguments"]
        user_request = args.get("user_request", "")
        plan = args.get("design_plan", "")
        raw_art = args.get("final_art_grid", "")

        # 1. 정제 (Markdown 제거)
        clean_art = clean_text(raw_art)

        # [NEW] 2. 안전장치: 길이 제한 (15줄 넘어가면 자름)
        safe_art = truncate_art(clean_art, max_lines=15)

        logger.info(f"📝 Request: {user_request}")
        logger.info(f"🎨 Art (Safe):\n{safe_art}")

        if not safe_art.strip():
            safe_art = "(🎨 생성된 아구가 비어있습니다. 다시 시도해주세요.)"

        success = await send_kakao(safe_art)
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
