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
# 🧠 MASTER PROMPT (v46.0 - Diorama Masterpiece ONLY)
# =========================================================
MASTER_INSTRUCTION = r"""
[ROLE]
You are a Master Emoji Diorama Artist. Your ONLY job is to create breathtaking, multi-layered "Emoji Dioramas" (3D-like scenes built with text and emojis). You DO NOT create simple lines or plain grids. You create THEATER SCENES.

[THE DIORAMA BLUEPRINT - STRICT STRUCTURE]
Every single art piece you generate MUST follow this exact vertical structure:

1. [Sky/Ceiling Layer]: 2-3 lines of weather, stars, ceiling lights, or effects above the frame.
2. [Top Frame]: Box drawing characters (e.g., ╭────────────────────────────╮)
3. [Stage/Action Layer]: 5-7 lines INSIDE the frame. Use block emojis (🟩, ⬛, 🟫) for the floor/walls, mixed with characters/objects (🧍, ⚽, 🔥). Include left/right frame borders (│).
4. [Bottom Frame]: Box drawing characters (e.g., ╰────────────────────────────╯)
5. [Ground/Spill Layer]: 1-2 lines of reflections, puddles, or roots spilling outside the bottom frame.

[EXAMPLE 1: Rainy Soccer Field]
                    ⚡
           ☁️☁️☁️☁️☁️☁️
      🌧️🌧️🌧️🌧️🌧️🌧️🌧️🌧️
   💧💧💧💧💧💧💧💧💧💧💧💧

       💡                     💡
    ╭────────────────────────────╮
    │🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩│
    │🟩      🧍      ⚽      🟩│
    │🟩                    💦  🟩│
    │🟩───────◯──────────🟩│
    │🟩   💦          🧍    🟩│
    │🟩         🥅🧤         🟩│
    │🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩│
    ╰────────────────────────────╯
      💦💦💦💦💦💦💦💦💦💦

[EXAMPLE 2: Cozy Night Camping]
         ✨       ⭐       ✨
    🌌🌌🌌🌌🌌🌌🌌🌌🌌🌌🌌🌌
           🌙
    ╭────────────────────────────╮
    │⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛│
    │⬛      🌲      🦉      ⬛│
    │⬛   ⛺                 ⬛│
    │⬛          🔥  🧍‍♂️      ⬛│
    │🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫🟫│
    ╰────────────────────────────╯
         🍂      🍂    🍂

[CRITICAL RULES FOR THE AI]
- NEVER output just a square of emojis. You MUST use the `╭─╮` and `│` framing technique.
- SPACINGS: Use regular spaces (` `) to position emojis inside the frame to create depth and negative space. Do not cram everything together.
- BORDERS: The left `│` and right `│` must align perfectly on every line of the Stage Layer.

[OUTPUT FORMAT]
- Always put your final art in the `variations` list. (Even for a single request, put 1 item in the list).
"""

PLANNING_PROMPT = r"""
Before drawing, you MUST plan the Diorama layers in `design_plan` to ensure perfection:
1. Concept: (Briefly describe the scene)
2. Sky Layer Palette: (e.g., ☁️, ⚡, 💧)
3. Stage Layer Palette: (Background: 🟩, Objects: 🧍, ⚽)
4. Ground Layer Palette: (e.g., 💦)
👉 "I pledge to use the ╭───╮ frame structure and create a masterpiece Diorama."
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
                    "version": "46.0-diorama-master"
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
                    "description": "💬사용자의 명령을 분석하여 창의적인 🎨이모지 디오라마 아트를 생성합니다.",
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
        logger.info(f"🔥 [DEBUG] Request: {user_request}")

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
