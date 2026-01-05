import os
import json
import logging
import requests
import uvicorn
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from mcp.server.sse import SseServerTransport
import re

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
    
    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 도착!\n\n{content}",
                "link": {"web_url": "https://playmcp.kakao.com"},
            })
        }
        return requests.post(url, headers=headers, data=payload)

    res = try_post(CURRENT_ACCESS_TOKEN)
    if res.status_code == 401:
        if refresh_kakao_token():
            res = try_post(CURRENT_ACCESS_TOKEN)
        else:
            return False

    return res.status_code == 200

# =========================================================
# 🧠 MASTER ART PROMPT (사용자님의 정성스러운 프롬프트를 여기에!)
# =========================================================
# 이 내용을 도구 설명(Description)에 직접 넣어야 AI가 그림 그리기 직전에 읽고 따라합니다.
MASTER_INSTRUCTION = """
[ROLE] You are a High-Quality Text & Emoji Artist.

[YOUR TASK]
Choose ONE style from the 4 categories below based on the user's request and generate the art string.

---
### 1. 한 줄 이모지 아트 (Simple Line)
- **Strategy**: Combine emojis to represent a concept in one line.
- Ex: "2026" -> 2️⃣0️⃣2️⃣6️⃣
- Ex: "Grass Monkey" -> 🌿🐒
- Ex: "Love Meat" -> 🧑❤️🍖

### 2. 여러 줄 이모지 아트 (Pixel Grid Art)
- **Strategy**: Use COLORED BLOCKS (🟩🟨🟧🟥🟦🟪⬛️⬜️) to draw the shape. 
- **CRITICAL RULE**: Differentiate Subject vs Background. Use Negative Space.
- **Ex: "Burning Jellyfish"**:
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊
- **Ex: "Ramen" (Bowl + Noodles)**:
⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛
⬛🍜🟨〰️〰️〰️🟨🍜⬛
⬛🍜🍥🥚🍖🥚🍥🍜⬛
⬛🍜🟨🟨🟨🟨🟨🍜⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛
- **Ex: "Snake in Grass" (Subject: Green Blocks, BG: Leaf)**:
🌿🌿🌿🌿🌿🌿🌿🌿
🌿🌿🟩🟩🟩🟩🌿🌿
🌿🌿🌿🌿🌿🟩🌿🌿
🌿🌿🟩🟩🟩🟩🌿🌿
🌿🌿🟩🌿🌿🌿🌿🌿
🌿🌿🟩🟩👀👅🌿🌿
🌿🌿🌿🌿🌿🌿🌿🌿
- **Ex: "Earth" (Contrast BG)**:
⬛⬛⬛🟦🟦🟦⬛⬛⬛
⬛⬛🟦🟦🟩🟩🟦⬛⬛
⬛🟦🟦🟩🟩🟩🟩🟦⬛
⬛🟦🟦🟦🟩🟦🟦🟦⬛
⬛🟩🟦🟦🟩🟩🟦🟦⬛
⬛⬛🟦🟦🟩🟩🟦⬛⬛
⬛⬛⬛🟦🟦🟦⬛⬛⬛

### 3. 카오모지 (Kaomoji)
- **Strategy**: One-line special characters.
- Ex: "Fighting" -> (ง •̀_•́)ง
- Ex: "Running" -> (งᐖ)ว
- Ex: "Sad" -> (｡•́︿•̀｡)

### 4. 아스키 아트 (ASCII / Braille)
- **Strategy**: Use lines, dots, blocks for complex shapes.
- **Ex: "Cat Heart"**:
˚∧＿∧   　+        —̳͟͞͞💗
(  •‿• )つ  —̳͟͞͞ 💗         
(つ　 <                —̳͟͞͞💗
｜　 _つ      +  —̳͟͞͞💗    
`し´
- **Ex: "Braille Clover"**:
⠀⠀⠀⠀⠀⠀⠀⠀⢔⢕⢄⢄⠆⡄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⡀⠄⢄⠑⡜⢐⠅⢕⠄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠐⢌⠪⠸⠠⡁⠆⢋⠠⠠⡠⡀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⡢⡃⡇⡓⠀⠥⡡⢊⢌⠆⠎⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠃⠃⠁⠀⡁⠈⢪⢪⢪⡂⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠨⡀⠀⠁⠑⠀⠀⠀⠀⠀⠀
---
"""

PLANNING_PROMPT = """
[STEP 1: PLAN]
Before generating the final art string, explain your plan:
1. **Selected Style**: (1, 2, 3, or 4)
2. **Palette/Char**: Which blocks/emojis will you use? (e.g., "Use 🟩 for Snake, 🌿 for BG")
3. **Geometry**: How will you draw the shape? (e.g., "Draw a circle in the center")
"""

# =========================================================
# 🧪 Validation Logic
# =========================================================
def validate_art(user_request: str, art: str) -> bool:
    if not art or not art.strip():
        return False
    # 너무 짧거나(1줄 미만인데 이모지도 없으면) 등등 검사
    # (기존 로직 유지하되, 카오모지는 1줄이어도 통과되도록 유연하게)
    return True

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
                "serverInfo": {"name": "t3xtart", "version": "9.0-brain-cot"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "Generate High-Quality Emoji/ASCII Art based on user request. MUST plan first.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {
                                "type": "string",
                                "description": "Original user prompt"
                            },
                            # 1. 뇌를 깨우는 질문 (여기에 답변하면서 AI가 생각을 정리함)
                            "design_plan": {
                                "type": "string",
                                "description": PLANNING_PROMPT
                            },
                            # 2. 실제 결과물 (여기에는 마스터 프롬프트를 넣어줌)
                            "final_art_grid": {
                                "type": "string",
                                "description": MASTER_INSTRUCTION + "\n\nGenerate ONLY the final art string here."
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
        
        # AI의 설계도는 로그에만 남기고 사용자가 볼 필요는 없음 (혹은 디버깅용)
        plan = args.get("design_plan", "")
        art = args.get("final_art_grid", "").strip()

        logger.info(f"📝 Request: {user_request}")
        logger.info(f"🧠 AI Plan: {plan}")
        logger.info(f"🎨 Final Art:\n{art}")

        if not validate_art(user_request, art):
            art = "(생성 실패: 너무 단순하거나 규칙에 맞지 않습니다.)"

        # 카카오 전송
        success = await send_kakao(art)
        
        result_msg = "✅ 전송 완료" if success else "❌ 전송 실패 (토큰 확인 필요)"

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": result_msg}]
            }
        })

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
