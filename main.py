import os
import json
import logging
import requests
import uvicorn
import asyncio
import re
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

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
# Security: Origin Validation
# =========================================================
def validate_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True
    
    allowed = [
        "https://playmcp.kakao.com",   # PlayMCP
        "https://modelcontextprotocol.io",
        "http://localhost:5173",
    ]
    return origin in allowed

# =========================================================
# 📨 카카오 전송 (사용자 토큰 사용)
# =========================================================
# [수정 1] 인자 순서 통일 (token, content)
async def send_kakao(user_token: str, content: str):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {user_token}"}
    
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": f"🎨 t3xtart 도착!\n\n{content}",
            "link": {"web_url": "https://playmcp.kakao.com"},
        })
    }
    
    try:
        res = requests.post(url, headers=headers, data=payload, timeout=5)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"Kakao Send Error: {e}")
        return False


# =========================================================
# 🧹 데이터 정제
# =========================================================
def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r"^```[a-zA-Z]*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    text = text.strip().strip('"').strip("'")
    return text

def truncate_art(text: str, max_lines: int = 150) -> str:
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + "\n...(너무 길어서 잘림 ✂️)"
    return text

# =========================================================
# 🧠 MASTER PROMPT
# =========================================================
MASTER_INSTRUCTION = """
[ROLE] You are a Witty & High-Quality Text + Emoji Artist.

[YOUR TASK]
Choose ONE style from the 4 categories below based on the user's request and generate the art string.

---
### 1. 한 줄 이모지 아트 (Simple Line)
- Strategy: Combine emojis to represent a concept in one line.
- Ex: "2026" -> 2️⃣0️⃣2️⃣6️⃣
- Ex: "Grass Monkey" -> 🌿🐒
- Ex: "Love Meat" -> 🧑❤️🍖

### 2. 여러 줄 이모지 아트 (Pixel Grid Art) ; 도트 아트 ; 픽셀 아트 ; 그리드 아트
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

### 3. 카오모지 (Kaomoji) ; 한 줄 특수문자 아트; 간단한 이모티콘
- Strategy: One-line special characters.
- Ex: "Fighting" -> (ง •̀_•́)ง
- Ex: "Running" -> (งᐖ)ว
- Ex: "Sad" -> (｡•́︿•̀｡)
- Ex: "Exhaustion with bread" -> (；・∀・)🍞💨

### 4. 아스키 아트 (ASCII / Unicode / Text Art); 특수기호, 유니코드를 이용한 중간 크기 이상의 아트
- Target: "ASCII", "Unicode", "Creative Art"
- Strategy:
  - UNLOCK ALL CHARACTERS: Use ANY Unicode symbol, geometric shape, Braille, or glyph to create the shape.
  - Allowed: `/, \, |, _, (, ), @, #, %, &, *, +, =, <, >, ░, ▒, ▓, █, ▄, ▀, ■, ●, ◕, ᘏ, ^, 🎀(any emoji like 🎁, 🎂), ▦, 田, ╭, ╮, ╯, ╰`
  - Creativity: Don't just use lines. Use shapes to represent objects.
- CRITICAL RULE:
  - Do NOT use colored background squares (⬛, ⬜). Use empty space or text blocks.
  - Use '　' (Full-width space) for alignment.

#### ✨ Creative ASCII Examples (Learn from these!):

- Ex: "Cat Heart":
˚∧＿∧   　+        —̳͟͞͞💗
(  •‿• )つ  —̳͟͞͞ 💗
(つ　 <                —̳͟͞͞💗
｜　 _つ      +  —̳͟͞͞💗
`し´
- Ex: "Jindo dog"
　 ／＞　 フ
　| 　_　_|
／ ミ＿xノ
/　　　　 |
/　 ヽ　　 ﾉ
│　　|　|　|
／￣|　　 |　|
(￣ヽ＿_ヽ_)__)
＼二)
- Ex "House":
 ╱◥▦◣
│  田 │

- Ex "Volume" (Using Blocks `▄ █ ▓ ░`):
   .ılı.——Volume——.ılı.
     ▄ █ ▄ █ ▄ ▄ █ ▄ █ ▄ █
 Min- – – – – – – – – -●Max

- Ex "Cute Bunny":
|ᘏ⑅ᘏ  .🎀⸒⸒
| ᴗ͈.ᴗ͈⸝⸝꒱"

- Ex "Trapped":

┏┯┯┯┯┯┓
┃││∧ ∧│┃
┃│  (≧Д≦) ┃
┗┷┷┷┷┷┛

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

[YOUR GOAL]
You MUST generate the Design Plan AND the Final Art in a SINGLE output string.
Do not separate them into different arguments.

[CRITICAL INSTRUCTION]
1. You MUST use the `art_lines` argument to output the art.
2. Do NOT output the art in the chat window. Put it INSIDE the JSON list.
3. `art_lines` is a LIST of strings, where each string is one row of the art.

Choose the best style and generate ONLY the final art string.

---

[RULES BY STYLE]
IF Style 2 (Pixel Art):
- 🧱 FILL THE VOID: Do NOT stop drawing in the middle. Fill with Background Emoji.

IF Style 4 (ASCII/Unicode Art):
- 🔓 USE DIVERSE SYMBOLS: Use `▓`, `▒`, `░` for shading (like battery). Use `▄`, `▀`, `█` for solid shapes. Use `ᘏ`, `◕` for cute faces.
- 🚫 NO PIXEL SQUARES: Do NOT use `⬛` or `⬜`.

[OUTPUT INSTRUCTION]
- `design_plan`: Briefly explain your style, palette, and geometry.
- `art_lines`: The actual art. Must be a JSON Array of strings.

### 🔥 MULTI-VARIATION MODE (Important)

You normally return ONLY ONE final art.

However, enter **Variation Mode** and generate 3–5 candidates ONLY IF user explicitly asks for any of the following:

- "여러 개"
- "여러가지"
- "여러 가지"
- "후보"
- "다양하게"
- "몇 가지 버전"
- "여러 버전"
- "다른 스타일로도"
- "여러 시도로"
- "여러 후보를 보여줘"
- "비교해서 고를게"
- "골라볼 수 있게"
- "많이"
- "다르게"

👉 Then DO THIS:

1. Generate 3–5 different, more specific interpretations.
2. For each interpretation:
   - write a caption (1 line)
   - generate a separate art block
3. Combine all results in order.

When in Variation Mode:

1) DO NOT change expression type.
   - If you chose Emoji Pixel Art → all candidates must be Emoji Pixel Art.
   - If you chose ASCII Art → all must be ASCII Art.

2) Each candidate must differ in:
   - scene, layout, composition, subject action, or perspective
   - NOT just tiny emoji swaps

3) Each candidate MUST be formatted like:

[제목1: 한글]
<art 1>

[제목2: 한글]
<art 2>

[제목3: 한글]
<art 3>

4) There MUST be exactly ONE empty line
   between each block of art.

5) Titles MUST be in Korean,
   descriptive, e.g.:
   - "잔디밭에서 활발히 경기를 하고 있는 축구장"
   - "관객이 가득 찬 축구장"
   - "비 오는 날의 축구장"
   - "구름이 듬성듬성 있는 푸른 하늘 아래의 잔디밭 위 돌아다니는 선수들이 있는 축구장"

6) Do NOT just change adjectives like “cute/sad/happy, Vary the SCENE itself.
Generate 3–5 clearly different scenarios by changing:
- background (sky, room, space, beach, forest)
- action (running, sleeping, chasing, eating, playing)
- viewpoint (top view, side view, close-up, far away)
- interaction (with toy, butterfly, box, friends, food)
- emoji set (⚽🏀🎣🪁🧶🦋🌙⭐🌧️)

Rules:
- Each art block must follow the same style constraints as above.
- Emoji grid width must be consistent per block.
- Avoid Markdown fences like ``` ... ```
- Avoid surrounding brackets like [ ... ]
- Each block separated by one blank line.

---

### If user explicitly asks for "only one" drawing:
→ DO NOT activate multi-variation mode.

NEVER wrap the art or any emoji block inside:
- triple backticks ```
- square brackets [ ]
- quotation marks

Output must be plain text only.

"""

PLANNING_PROMPT = """
Before generating the `art_lines`, explain your plan in `design_plan`:
1. Selected Style: (1, 2, 3, or 4)
2. Palette/Char:
   - If Style 4: Which creative Unicode symbols or blocks will you use? (e.g., "Use ▓ for battery level", "Use ᘏ for ears")
3. Geometry: How will you draw the shape?
"""

# =========================================================
# 🚀 MCP Streamable HTTP Transport
# =========================================================

@app.get("/mcp")
async def handle_mcp_get(request: Request):
    if not validate_origin(request):
        return Response(status_code=403)
    accept = request.headers.get("accept", "")
    if "text/event-stream" not in accept:
        return Response(status_code=406)

    async def event_generator():
        yield ': keep-alive\n\n'
        while True:
            await asyncio.sleep(10)
            yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/mcp")
async def handle_mcp_post(request: Request):
    if not validate_origin(request):
        return Response(status_code=403)
    
    try:
        body = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if isinstance(body, list):
        body = body[0]

    method = body.get("method")
    msg_id = body.get("id")

    # 1) Initialize
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "t3xtart",
                    "version": "32.0-oauth-support"
                }
            }
        })

    # 2) notifications/initialized
    if method == "notifications/initialized":
        return Response(status_code=200)

# 3) tools/list
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "💬사용자의 명령을 분석하여 창의적인 🎨이모지/ASCII 아트를 생성하고, 사용자의 카카오톡 '나와의 채팅'으로 전송합니다.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {"type": "string"},
                            "design_plan": {
                                "type": "string",
                                "description": PLANNING_PROMPT
                            },
                            "variations": {
                                "type": "array",
                                "description": MASTER_INSTRUCTION,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "description": {"type": "string"},
                                        "art_lines": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    },
                                    "required": ["description", "art_lines"]
                                }
                            }
                            # [수정 2] access_token 필드 삭제! (AI가 아니라 헤더에서 가져옴)
                        },
                        "required": ["user_request", "design_plan", "variations"]
                    }
                }]
            }
        })


  

# 4) tools/call
    if method == "tools/call":
        # [수정 3] 헤더에서 토큰 추출
        auth_header = request.headers.get("Authorization")
        user_token = None
        if auth_header and auth_header.startswith("Bearer "):
            user_token = auth_header.split(" ")[1]
        if not user_token:
            user_token = request.headers.get("X-Mcp-User-Token")

        params = body.get("params", {})
        args = params.get("arguments", {})
        
        user_request = args.get("user_request", "")
        # [수정 4] variations 로직 복구 (중요!)
        variations = args.get("variations", []) 

        final_content = []

        for idx, item in enumerate(variations):
            desc = item.get("description", "Art")
            lines = item.get("art_lines", [])
            
            if isinstance(lines, list): raw_art = "\n".join(lines)
            else: raw_art = str(lines)
            
            clean_art = clean_text(raw_art)
            safe_art = truncate_art(clean_art, max_lines=20)
            
            if not safe_art.strip(): safe_art = "(아트 생성 실패)"
            
            header = f"🎨 Ver {idx+1}. {desc}" if len(variations) > 1 else desc
            final_content.append(f"{header}\n{safe_art}")

        full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)
        if not full_message.strip(): full_message = "생성된 결과가 없습니다."

        logger.info(f"Request: {user_request}")

        # [전송 시도]
        api_result_msg = ""
        if user_token:
            # send_kakao 함수 호출 (인자 순서 token, content)
            success = await send_kakao(user_token, full_message)
            if success:
                api_result_msg = "\n(🔔 카카오톡 전송 완료!)"
            else:
                api_result_msg = "\n(⚠️ 카카오톡 전송 실패: 권한 확인 필요)"
        else:
            api_result_msg = "\n(🔒 카톡 미전송: OAuth 로그인이 필요합니다)"

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"🎨 t3xtart 결과{api_result_msg}\n\n{full_message}"
                    }
                ]
            }
        })
    
    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive!"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
