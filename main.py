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
# 🧠 MASTER PROMPT (Integrated System Prompt)
# =========================================================
MASTER_INSTRUCTION = r"""
# ROLE
You are TextArtGPT.
You are an expert emoji artist.
Your goal is NOT to answer.
Your goal is to CREATE ART.
Every response should look handcrafted by a professional emoji artist.

------------------------------------------------------------
THINK LIKE AN ARTIST
------------------------------------------------------------
Before drawing mentally determine:
1. What is the main subject?
2. What emotion should the artwork convey?
3. What viewing angle works best?
   Examples: Front, Top, Perspective, Close-up, Side
4. Which emojis best represent each object?
   Never randomly place emojis.
   Every emoji has a purpose.
5. Decide foreground. Decide background. Decide empty space.
   Negative space is important.
6. Create a silhouette first. Only then fill details.
7. Balance left/right. Balance top/bottom. Artwork should feel centered.
8. Large subjects deserve large artwork. Tiny requests may stay compact.

------------------------------------------------------------
QUALITY RULES
------------------------------------------------------------
Artwork should feel like it took time.
Avoid repetitive emoji spam.
Avoid random symmetry.
Add depth. Layer objects.
Use decorations. Use atmosphere.
Rain, Clouds, Light, Smoke, Water, Stars, Grass, Fire, Sparkles, Shadows if appropriate.

------------------------------------------------------------
SCENE COMPOSITION
------------------------------------------------------------
Every artwork should contain: Main object, Supporting elements, Environment, Mood.
Instead of ⚽, Draw: Clouds, Rain, Goal, Grass, Players, Field lines, Ball, Lighting.

------------------------------------------------------------
CHARACTER RULES
------------------------------------------------------------
Characters should have Face, Hands, Legs, Pose, Movement, Accessories, Emotion.
Don't simply output 🙂. Create an entire body.

------------------------------------------------------------
EMOJI SELECTION
------------------------------------------------------------
Prefer 🟩⬜⬛🟦🟫🟨🟥🟪 for structure.
Use decorative emojis only where meaningful.

------------------------------------------------------------
SIZE
------------------------------------------------------------
Simple request: 10~20 lines
Scene: 20~40 lines
Epic request: 40~80 lines

------------------------------------------------------------
STYLE
------------------------------------------------------------
Never explain the artwork.
Output only the artwork.
No markdown. No code block. No commentary.

------------------------------------------------------------
OUTPUT FORMAT
Return JSON only matching the schema.
Populate the design object carefully.
Then create artwork matching that design.
The artwork should feel handcrafted.
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
                    "version": "48.0-schema-driven"
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
                    "description": MASTER_INSTRUCTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {
                                "type": "string"
                            },
                            "design": {
                                "type": "object",
                                "description": "Mental sandbox to design the art before generating lines.",
                                "properties": {
                                    "subject": {"type": "string"},
                                    "style": {"type": "string"},
                                    "view": {"type": "string"},
                                    "scene": {"type": "string"},
                                    "mood": {"type": "string"},
                                    "size": {"type": "string"},
                                    "composition": {"type": "string"},
                                    "foreground": {"type": "string"},
                                    "midground": {"type": "string"},
                                    "background": {"type": "string"},
                                    "lighting": {"type": "string"},
                                    "palette": {"type": "string"},
                                    "density": {"type": "string"},
                                    "symmetry": {"type": "string"},
                                    "motion": {"type": "string"},
                                    "negative_space": {"type": "string"}
                                },
                                "required": ["subject", "composition", "palette"]
                            },
                            "variations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "theme": {"type": "string"},
                                        "estimated_width": {"type": "integer"},
                                        "estimated_height": {"type": "integer"},
                                        "art_lines": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    },
                                    "required": ["title", "theme", "estimated_width", "estimated_height", "art_lines"]
                                }
                            }
                        },
                        "required": ["user_request", "design", "variations"]
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
        final_content = []

        if variations and len(variations) > 0:
            for idx, item in enumerate(variations):
                title = item.get("title", "Untitled")
                theme = item.get("theme", "Unknown Theme")
                w = item.get("estimated_width", "?")
                h = item.get("estimated_height", "?")
                lines = item.get("art_lines", [])

                if isinstance(lines, list): 
                    raw_art = "\n".join(lines)
                else: 
                    raw_art = str(lines)

                clean_art = clean_text(raw_art)
                safe_art = truncate_art(clean_art, max_lines=150)

                header = f"🎨 {title}\n📐 {w}×{h}\n🎭 {theme}"
                final_content.append(f"{header}\n\n{safe_art}")
        else:
            final_content.append("(人 > <,,) 아트를 그릴 수 없었어요.. 다시 시도해 주세요!")

        full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)

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
