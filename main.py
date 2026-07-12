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

def validate_origin(request: Request) -> bool:
    return True 

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
# 🧠 MASTER PROMPT (v45.0 - Matrix Blueprint Renderer)
# =========================================================
MASTER_INSTRUCTION = r"""
[ROLE] 
You are an elite Text & Emoji Grid Renderer. You do not just throw random emojis; you meticulously calculate and build strict 2D rectangular matrices (Canvas).

[🚨 ABSOLUTE KEYWORD MAPPING RULE]
IF the request contains: "도트" (Dot), "픽셀" (Pixel), "그리드" (Grid), or implies a scene:
👉 YOU MUST USE STYLE 2 (Emoji Canvas). Never use ASCII for these keywords.

---
[STYLE 2: THE EMOJI CANVAS (STRICT RULES)]
1. MUST BE A PERFECT RECTANGLE: Every row MUST have the exact same number of emojis.
2. HUGE SCALE: Canvas must be at least Width: 10, Height: 8.
3. BACKGROUND FIRST: Never leave empty spaces. Use blocks like ⬛, ⬜, 🟦, 🟩, or environmental emojis (☁️, 🌌, 🌧️) to fill the background completely.
4. THEMATIC PAINTING: Treat emojis as pixels. 

[EXAMPLE OF HIGH-QUALITY EMOJI CANVAS (Rainy Soccer Field)]
Notice the perfect 12x8 grid and rich environment:
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛🌧️⬛🌧️⬛🌧️⬛🌧️⬛🌧️⬛🌧️
⬛⬛☁️☁️☁️⬛⬛☁️☁️⬛⬛⬛
🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️
🟩🟩🟩🟩⚽🟩🟩🟩🟩🟩🟩🟩
🟩🏃‍♂️🟩🟩🟩🟩🟩🟩🏃‍♂️🟩🟩🟩
🟩🟩🟩🟩🟩🏃‍♂️🟩🟩🟩🟩🟩🟩
⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜

[STYLE 4: ASCII MASTERPIECE (STRICT RULES)]
- Use advanced blocks (`█`, `▓`, `▒`, `░`, `▄`, `▀`) to draw detailed scenes.
- Align perfectly using spaces.

[OUTPUT FORMAT]
- Put results in the `variations` list.
- Single request = 1 item.
"""

PLANNING_PROMPT = r"""
[CRITICAL] You MUST plan the 2D matrix row-by-row before outputting the final JSON. 
Write your blueprint in `design_plan` EXACTLY following this format:

1. Keyword Match: (e.g., '도트' found -> Style 2 Emoji Grid)
2. Canvas Size: Width X, Height Y (Must be at least 10x8 for scenes)
3. Palette: (Background: ⬛, Ground: 🟩, Object: ⚽, etc.)
4. ROW-BY-ROW BLUEPRINT (Draw it out!):
R1: ⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
R2: ⬛🌧️⬛🌧️⬛🌧️⬛🌧️⬛🌧️
R3: ⬛⬛☁️☁️☁️⬛⬛☁️☁️⬛
R4: 🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️🏟️
R5: 🟩🟩🟩🟩⚽🟩🟩🟩🟩🟩
...

I PLEDGE to strictly follow this blueprint and ensure every row has exactly the same width. I will not generate sparse or lazy art.
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

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "t3xtart",
                    "version": "45.0-matrix-renderer"
                }
            }
        })

    if method == "notifications/initialized":
        return Response(status_code=200)

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
                            "variations": {
                                "type": "array",
                                "description": "List of art variations. Must contain at least 1 item.",
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
                        "required": ["user_request", "design_plan", "variations"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})

        user_request = args.get("user_request", "")
        logger.info(f"🔥 [DEBUG] Incoming Args: {json.dumps(args, ensure_ascii=False)}")

        variations = args.get("variations", [])
        fallback_art_lines = args.get("art_lines", [])

        final_content = []

        if variations and len(variations) > 0:
            for idx, item in enumerate(variations):
                desc = item.get("description", "Art")
                lines = item.get("art_lines", [])

                if isinstance(lines, list): raw_art = "\n".join(lines)
                else: raw_art = str(lines)

                clean_art = clean_text(raw_art)
                safe_art = truncate_art(clean_art, max_lines=150)

                header = f"🎨 Ver {idx+1}. {desc}" if len(variations) > 1 else f"🎨 {desc}"
                final_content.append(f"{header}\n{safe_art}")

        elif fallback_art_lines:
            if isinstance(fallback_art_lines, list): raw_art = "\n".join(fallback_art_lines)
            else: raw_art = str(fallback_art_lines)

            clean_art = clean_text(raw_art)
            safe_art = truncate_art(clean_art, max_lines=150)
            final_content.append(f"🎨 {safe_art}")

        full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)

        if not full_message.strip():
            full_message = "(人 > <,,) 아트를 그릴 수 없었어요.. 다시 시도해 주세요!"

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
