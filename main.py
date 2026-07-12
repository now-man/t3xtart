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
# 💾 나만의 이모지 아트 DB (파일 기반 저장소)
# =========================================================
MY_ART_DB_FILE = "my_art_db.json"

def load_arts():
    if os.path.exists(MY_ART_DB_FILE):
        try:
            with open(MY_ART_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_arts(data):
    with open(MY_ART_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
# 🧠 MASTER PROMPT (v52.0)
# =========================================================
MASTER_INSTRUCTION = r"""
# ROLE
You are TextArtGPT. You are an expert emoji artist.
Your goal is NOT to answer. Your goal is to CREATE ART.

------------------------------------------------------------
4 SUPPORTED ART STYLES (CRITICAL)
------------------------------------------------------------
You MUST generate art in one of these four explicit formats:

1. 한 줄 이모지 아트 (Single-line Emoji Art)
   Ex: 🧙‍♂️⚡🧹🦉

2. 여러 줄 이모지 아트 (Multi-line Emoji Art)
   Ex: 
   🍜🍜🍜🍜🍜
   🍜🌿🌿🌿🍜
   🍜🍜🍜🍜🍜

3. 한 줄 특수문자 아트 (Kaomoji)
   Ex: (；・∀・)🍞💨

4. 여러 줄 특수문자 아트 (ASCII Art)
   Ex:
   ╱◥◣╱◥◣╱◥◣
   │田││田││田│

------------------------------------------------------------
THINK LIKE AN ARTIST
------------------------------------------------------------
Before drawing mentally determine:
1. Subject & Emotion.
2. The optimal viewing angle.
3. Choose the EXACT style (1, 2, 3, or 4) that fits best.
4. Decide foreground, background, and empty space.

------------------------------------------------------------
QUALITY RULES
------------------------------------------------------------
- NO BORDERS/FRAMES: Never use box-drawing characters (╭, ╰, │, ─) to frame the artwork.
- Use negative space naturally.
- Avoid repetitive emoji spam.

------------------------------------------------------------
OUTPUT FORMAT
Return JSON only matching the schema.
Populate the 16-parameter design object carefully, then create artwork matching that design.
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
                    "version": "52.0-multi-tool"
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
                "tools": [
                    {
                        "name": "render_and_send",
                        "description": "💬사용자의 명령을 분석하여 4가지 타입(한 줄/여러 줄 이모지, 카오모지, 아스키 아트) 중 하나로 아트를 생성합니다.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "user_request": {"type": "string"},
                                "design": {
                                    "type": "object",
                                    "properties": {
                                        "subject": {"type": "string"},
                                        "style": {"type": "string", "description": "Choose from: 1.한줄이모지, 2.여러줄이모지, 3.한줄특수문자, 4.여러줄특수문자"},
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
                                    "required": ["subject", "style", "composition", "palette"]
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
                    },
                    {
                        "name": "manage_my_art",
                        "description": "💾 마음에 드는 이모지/아스키 아트를 저장하거나, 사용자가 직접 입력한 아트를 보관하고 다시 불러오는 기억(Memory) 도구입니다.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string", 
                                    "enum": ["save", "list", "view"],
                                    "description": "'save'는 아트 저장, 'list'는 저장된 목록 확인, 'view'는 특정 아트 불러오기"
                                },
                                "user_key": {
                                    "type": "string", 
                                    "description": "사용자 닉네임 (개인 보관함 구분용)"
                                },
                                "title": {
                                    "type": "string",
                                    "description": "저장하거나 불러올 아트의 제목"
                                },
                                "art_lines": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "저장할 아트의 내용 (action이 'save'일 때만 필요)"
                                }
                            },
                            "required": ["action", "user_key"]
                        }
                    }
                ]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})
        tool_name = params.get("name")
        
        # ==========================================
        # TOOL 1: 🎨 렌더링 툴
        # ==========================================
        if tool_name == "render_and_send":
            user_request = args.get("user_request", "")
            logger.info(f"🔥 [RENDER] Request: {user_request}")

            variations = args.get("variations", [])
            final_content = []

            if variations and isinstance(variations, list) and len(variations) > 0:
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
                final_content.append("(人 > <,,) 아트를 그릴 수 없었어요..")

            full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": full_message}]}
            })
            
        # ==========================================
        # TOOL 2: 💾 나만의 아트 보관함 툴
        # ==========================================
        elif tool_name == "manage_my_art":
            action = args.get("action")
            user_key = args.get("user_key", "default_user")
            title = args.get("title", "Untitled")
            art_lines = args.get("art_lines", [])
            
            logger.info(f"💾 [MEMORY] Action: {action}, User: {user_key}, Title: {title}")

            db = load_arts()
            if user_key not in db:
                db[user_key] = {}

            if action == "save":
                if not art_lines:
                    msg = "❌ 저장할 아트 내용(art_lines)이 없습니다."
                else:
                    db[user_key][title] = art_lines
                    save_arts(db)
                    msg = f"✅ 나만의 이모지 아트 '{title}'이(가) {user_key}님의 보관함에 성공적으로 저장되었습니다!"
            
            elif action == "list":
                saved_titles = list(db[user_key].keys())
                if saved_titles:
                    msg = f"📂 {user_key}님의 보관함 목록:\n" + "\n".join([f"- {t}" for t in saved_titles])
                else:
                    msg = f"📂 {user_key}님의 보관함이 비어있습니다. 새로운 아트를 저장해보세요!"
            
            elif action == "view":
                if title in db[user_key]:
                    lines = db[user_key][title]
                    art_str = "\n".join(lines) if isinstance(lines, list) else str(lines)
                    msg = f"🎨 보관함에서 꺼낸 '{title}'\n\n{art_str}"
                else:
                    msg = f"❌ '{title}' 아트를 보관함에서 찾을 수 없습니다. 목록을 먼저 확인해주세요."
            else:
                msg = "지원하지 않는 액션입니다. (save, list, view 중 하나를 선택하세요)"

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": msg}]}
            })

    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive!"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
