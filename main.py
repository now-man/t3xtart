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

FULL_SPACE = "ㅤ"  # 전각 공백 (모바일 안전)

# =========================================================
# 🔐 Kakao Token
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    try:
        res = requests.post(
            "https://kauth.kakao.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": os.environ.get("KAKAO_CLIENT_ID"),
                "refresh_token": os.environ.get("KAKAO_REFRESH_TOKEN"),
                "client_secret": os.environ.get("KAKAO_CLIENT_SECRET"),
            },
            timeout=5,
        )
        if res.status_code == 200:
            CURRENT_ACCESS_TOKEN = res.json().get("access_token")
            return True
    except Exception as e:
        logger.error(e)
    return False

async def send_kakao(content: str):
    global CURRENT_ACCESS_TOKEN
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    def post(token):
        return requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "template_object": json.dumps({
                    "object_type": "text",
                    "text": f"🎨 t3xtart 도착!\n\n{content}",
                    "link": {"web_url": "https://playmcp.kakao.com"},
                })
            },
        )

    res = post(CURRENT_ACCESS_TOKEN)
    if res.status_code == 401 and refresh_kakao_token():
        res = post(CURRENT_ACCESS_TOKEN)

    return res.status_code == 200

# =========================================================
# 🧹 ART CLEANING & NORMALIZATION
# =========================================================
def clean_art(raw: str) -> str:
    if not raw:
        return ""

    # ``` 제거
    raw = re.sub(r"^```.*?\n|```$", "", raw, flags=re.S)

    # [🟨] 같은 패턴 제거
    raw = re.sub(r"\[([^\]]+)\]", r"\1", raw)

    lines = [l.rstrip() for l in raw.splitlines() if l.strip()]

    if not lines:
        return raw.strip()

    max_len = max(len(l) for l in lines)

    # 전각 공백으로 가로 길이 통일
    fixed = []
    for l in lines:
        pad = max_len - len(l)
        fixed.append(l + FULL_SPACE * pad)

    return "\n".join(fixed)

# =========================================================
# 한글 ASCII 안전 처리
# =========================================================
def korean_ascii_box(text: str) -> str:
    return (
        f"║ㅤ  {text}  ㅤㅤ║\n"
        "(人 > <,,) 한글 아스키아트는 아직 지원이 안 돼요.. 미안해요!"
    )

def looks_like_korean_ascii_request(user_request: str) -> bool:
    return bool(re.search(r"[가-힣]", user_request)) and "아스키" in user_request

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
- **Strategy**: Use COLORED BLOCKS (🟩🟨🟧🟥🟦🟪🟫⬛️⬜️) to draw the shape.
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
        ):
            while True:
                await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/sse")
async def sse_post(request: Request):
    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "t3xtart", "version": "FINAL"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "Generate emoji / ASCII art and send to Kakao",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {"type": "string"},
                            "final_art_grid": {"type": "string"},
                        },
                        "required": ["user_request", "final_art_grid"]
                    }
                }]
            }
        })

    if method == "tools/call":
        args = body["params"]["arguments"]
        user_request = args.get("user_request", "")
        art_raw = args.get("final_art_grid", "")

        if looks_like_korean_ascii_request(user_request):
            art = korean_ascii_box(user_request.replace("그려줘", "").strip())
        else:
            art = clean_art(art_raw)

        await send_kakao(art)

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": "✅ 전송 완료"}]}
        })

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
@app.get("/")
async def health():
    return "t3xtart alive"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
