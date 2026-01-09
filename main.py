import os
import json
import logging
import requests
import uvicorn
import asyncio
import re
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

# =========================================================
# 기본 설정
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("t3xtart")

app = FastAPI()

# 보안: CORS 및 Origin 검증을 위한 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 실제 운영 시에는 PlayMCP 도메인 등으로 제한하는 것이 좋습니다.
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
# 🧹 데이터 정제
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
│  田 │ 田│
  ]
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
"""

PLANNING_PROMPT = """
Before generating the `art_lines`, explain your plan in `design_plan`:
1. Selected Style: (1, 2, 3, or 4)
2. Palette/Char:
   - If Style 4: Which creative Unicode symbols or blocks will you use? (e.g., "Use ▓ for battery level", "Use ᘏ for ears")
3. Geometry: How will you draw the shape?
"""

# =========================================================
# 🚀 MCP Streamable HTTP Transport (New Spec 2025-03-26)
# =========================================================

# 심사 통과를 위한 단일 엔드포인트 정의 (/mcp)
@app.get("/mcp")
async def handle_mcp_get(request: Request):
    """
    Streamable HTTP: GET 요청은 SSE 스트림을 열어 서버 알림을 수신하는 용도입니다.
    """
    async def event_generator():
        # 연결 확인용 초기 이벤트 (선택사항이나 연결 유지에 도움됨)
        yield ": keep-alive\n\n"
        while True:
            # 서버에서 클라이언트로 보낼 알림이 있다면 여기서 yield 합니다.
            # 현재는 단순 도구 실행이므로 keep-alive만 유지합니다.
            await asyncio.sleep(10)
            yield ": keep-alive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

@app.post("/mcp")
async def handle_mcp_post(request: Request):
    """
    Streamable HTTP: 모든 JSON-RPC 요청(Initialize, CallTool 등)은 POST로 처리합니다.
    """
    try:
        body = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    # JSON-RPC 배치가 아닌 단일 요청이라고 가정하고 처리
    # (배치 처리가 필요하다면 리스트 순회 로직 추가 필요)
    if isinstance(body, list):
        body = body[0] # 편의상 첫 번째만 처리

    method = body.get("method")
    msg_id = body.get("id")

    # 1. 초기화 요청 (Initialize) - 버전 체크 중요!
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                # [중요] 심사 통과를 위해 최신 스펙 버전 명시
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {} # 도구 기능 활성화
                },
                "serverInfo": {
                    "name": "t3xtart",
                    "version": "27.0-streamable-http"
                }
            }
        })

    # 2. 초기화 알림 (Initialized)
    if method == "notifications/initialized":
        # 클라이언트가 초기화 완료를 알림. 별도 응답 없음.
        return Response(status_code=200)

    # 3. 도구 목록 요청 (Tools List)
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "💬사용자의 대화 명령을 기반으로 창의적으로 생성한 🎨이모지 아트를 카카오톡으로 전송해요..",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {"type": "string"},
                            "design_plan": {
                                "type": "string",
                                "description": PLANNING_PROMPT
                            },
                            "art_lines": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "The art grid, row by row. Example: ['⬜️⬜️', '🟥🟥']."
                            }
                        },
                        "required": ["user_request", "design_plan", "art_lines"]
                    }
                }]
            }
        })

    # 4. 도구 실행 요청 (Call Tool)
    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})

        user_request = args.get("user_request", "")
        plan = args.get("design_plan", "")
        art_lines = args.get("art_lines", [])

        # --- 기존 아트 생성 로직 ---
        if isinstance(art_lines, list):
            raw_art = "\n".join(art_lines)
        else:
            raw_art = str(art_lines)

        clean_art = clean_text(raw_art)

        if not clean_art.strip():
            logger.warning("⚠️ Empty Art. Fallback triggered.")
            clean_art = "(人 > <,,) 아트를 그릴 수 없었어요.. 채팅을 살짝 바꾸어 시도해보세요!"

        final_art = truncate_art(clean_art, max_lines=15)

        logger.info(f"📝 Request: {user_request}")
        logger.info(f"🎨 Final Art:\n{final_art}")

        # 카카오 전송
        success = await send_kakao(final_art)
        result_msg = "✅ 전송 완료" if success else "❌ 전송 실패"
        # -------------------------

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": result_msg}]
            }
        })

    # 그 외 Ping 등 기타 요청에 대한 기본 응답
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive (Streamable HTTP Ready)"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
