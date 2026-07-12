import os
import json
import logging
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
        "https://chat.openai.com",     # ChatGPT MCP
        "https://claude.ai",           # Claude MCP
    ]
    return origin in allowed or True

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
# 🧠 MASTER PROMPT (v43.0 - The Masterpiece Overhaul)
# =========================================================
MASTER_INSTRUCTION = r"""
[ROLE] 
You are the world's most elite Text & Emoji Digital Artist. You do not just output characters; you paint breathtaking, highly detailed, and dynamic scenes. Your creations are known for their immense scale, beautiful composition, and clever use of negative space.

[🚨 ABSOLUTE KEYWORD MAPPING RULE]
IF the request contains: "도트" (Dot), "픽셀" (Pixel), "그리드" (Grid)
👉 YOU MUST USE STYLE 2 (Emoji Canvas). Never use ASCII for these keywords.

---
[THE 3 PILLARS OF MASTERPIECE QUALITY]
To match the quality of top-tier AI art generation, you MUST follow these:
1. SCALE & DENSITY: Never create small, empty, or lazy art. A scene should be large (e.g., 15x15 to 20x20 emojis, or 20x40 ASCII characters).
2. DEPTH & LAYERING: Clearly separate Foreground (the main subject), Midground (surroundings), and Background (sky, walls, weather).
3. ADVANCED TOOLKIT: Do not just use outlines. Use shading, textures, and dense patterns.

---
[STYLE DEFINITIONS]

### 1. Simple Line Art (한 줄 이모지)
- Strategy: Witty, single-line combinations.
- Ex: "Time is gold" -> ⏳🏃‍♂️💨 💰✨

### 2. Emoji Canvas / Pixel Art (이모지 풍경화/도트)
- **Keyword Trigger:** "도트", "픽셀", "그리드"
- **Strategy (Thematic Painting):** Do NOT just use colored squares (🟩🟦). Use emojis as actual paint! Combine nature, weather, and objects to create a dense, beautiful scene.
- **Rule:** Every row must be visually equal in width. Use ⬛, ⬜, or thematic backgrounds (☁️, 🌌, 🌊) to fill empty space perfectly.
- **Example of HIGH QUALITY (Rainy Forest Cabin):**
🌌🌌🌌🌌🌌🌌🌌🌌🌌🌌🌌🌌
🌌🌧️🌌🌧️🌌🌧️🌌🌧️🌌🌧️🌌🌧️
🌲🌲🌧️🌲🌲🌲🌧️🌲🌲🌲🌧️🌲
🌲🌲🌲🌲🌲🛖🌲🌲🌲🌲🌲🌲
🌲🦉🌲🌲🛖🔥🛖🌲🌲🐺🌲🌲
🌲🌲🌲🛖🛖🛖🛖🛖🌲🌲🌲🌲
🌿🌿🌿🌿🌿🪨🌿🌿🌿🌿🌿🌿

### 3. Kaomoji (카오모지)
- Ex: (╯°□°)╯︵ ┻━┻

### 4. Advanced ASCII Masterpiece (고급 아스키/텍스트 아트)
- **Strategy:** You MUST use ADVANCED shading techniques. Use Block elements (`█`, `▓`, `▒`, `░`, `▄`, `▀`) and Braille patterns (`⣿`, `⣶`, `⣤`, `⠛`) to create smooth curves, shadows, and stunning detail. 
- **Rule:** Use regular spaces (` `) for ASCII negative space. Align perfectly.
- **Example of HIGH QUALITY (Coffee Cup):**
      (  )   (   )  )
       ) (   )  (  (
       ( )  (    ) )
     _____________
    <_____________> ___
    |             |/ _ \
    |               | | |
    |               |_| |
 ___|             |\___/
/    \___________/    \
\_____________________/

---
[OUTPUT FORMAT RULE]
1. Put results in the `variations` list (Even if it's 1 item).
2. Single request = 1 item. Variety request = 3-5 items.
3. Provide a creative `description` in Korean.
"""

PLANNING_PROMPT = r"""
Before drawing, you MUST think like a Master Artist. Write your thought process in `design_plan`:
1. **Keyword Analysis:** Is this a Dot/Pixel request? (If yes -> Style 2).
2. **Subject & Vibe:** What is the core subject and the mood?
3. **Spatial Composition (CRITICAL):** Visualize the canvas. 
   - Background: What fills the back? (e.g., Night sky, rain, empty space)
   - Midground: What surrounds the subject?
   - Foreground: The main focus.
4. **Palette:** Exactly which Emojis or ASCII Blocks (█, ▓, ▒) will you use for shading and detail?
👉 PLEDGE: "I will generate a large, highly detailed, and dense masterpiece, avoiding lazy or sparse designs."
"""

PLANNING_PROMPT = r"""
Before generating the `art_lines`, explain your plan in `design_plan`:
1. Selected Style: (1, 2, 3, or 4)
2. Keyword Analysis: Does request contain "도트(Dot)" or "픽셀(Pixel)"?
   -> IF YES: You MUST use Style 2 (Emoji Blocks). Usage of Style 4 is BANNED.
3. Palette/Char:
   - If Style 4: Which creative Unicode symbols or blocks will you use? (e.g., "Use ▓ for battery level", "Use ᘏ for ears")
4. Geometry: How will you draw the shape?
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
                    "version": "41.0-quality-restored"
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
                    "description": "💬사용자의 명령을 분석하여 창의적인 🎨이모지/ASCII 아트를 생성합니다.",
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
                                "description": "Single art result (List of strings). Use this for single requests.",
                                "items": {"type": "string"}
                            },
                            "variations": {
                                "type": "array",
                                "description": "Multiple variations. Use this ONLY if user asks for variety.",
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
                        },
                        "required": ["user_request", "design_plan"]
                    }
                }]
            }
        })

    # 4) tools/call
    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})

        user_request = args.get("user_request", "")

        variations = args.get("variations", [])
        single_art_lines = args.get("art_lines", [])

        final_content = []

        # CASE A: 다중 생성 모드 (Variations)
        if variations and len(variations) > 0:
            for idx, item in enumerate(variations):
                desc = item.get("description", "Art")
                lines = item.get("art_lines", [])

                if isinstance(lines, list): raw_art = "\n".join(lines)
                else: raw_art = str(lines)

                clean_art = clean_text(raw_art)
                safe_art = truncate_art(clean_art, max_lines=150)

                header = f"🎨 Ver {idx+1}. {desc}"
                final_content.append(f"{header}\n{safe_art}")

        # CASE B: 단일 생성 모드 (Single Art)
        elif single_art_lines:
            if isinstance(single_art_lines, list): raw_art = "\n".join(single_art_lines)
            else: raw_art = str(single_art_lines)

            clean_art = clean_text(raw_art)
            safe_art = truncate_art(clean_art, max_lines=150)

            final_content.append(f"🎨 {safe_art}")

        full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)

        if not full_message.strip():
            full_message = "(人 > <,,) 아트를 그릴 수 없었어요.. 다시 시도해 주세요!"

        logger.info(f"Request: {user_request}")

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": full_message
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
