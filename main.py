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

# Supabase 라이브러리 추가
from supabase import create_client, Client

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
# ☁️ Supabase 클라우드 DB 설정
# =========================================================
# 환경 변수에서 URL과 KEY를 가져옵니다. (없으면 오류 방지를 위해 None 처리)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase DB 연결 성공!")
    except Exception as e:
        logger.error(f"❌ Supabase 연결 실패: {e}")
else:
    logger.warning("⚠️ SUPABASE_URL 또는 SUPABASE_KEY 환경 변수가 설정되지 않았습니다.")

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
# 🧠 MASTER PROMPT (v54.0)
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

   Ex2:
   🟦🟦☁️🟦🟦🟦☁️🟦
   🟦☁️🟦🟦☁️🟦🟦☁️
   🥅⚽🏃🟩🏃🟩🟩🥅

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
                    "version": "54.0-supabase-cloud"
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
                        "description": "💬사용자의 명령을 분석하여 4가지 타입 중 하나로 아트를 생성합니다.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "user_request": {"type": "string"},
                                "design": {
                                    "type": "object",
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
                                    "required": ["subject", "style", "composition", "palette"]
                                },
                                "variations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string", "description": "직관적인 한국어 단어 (예: 나무)"},
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
                        "description": "💾 마음에 드는 아트를 클라우드에 영구 저장하거나 목록을 조회합니다.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string", "enum": ["save", "list", "view"]},
                                "user_key": {"type": "string", "description": "사용자 닉네임"},
                                "title": {"type": "string"},
                                "art_lines": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["action", "user_key"]
                        }
                    },
                    {
                        "name": "delete_my_art",
                        "description": "🗑️ 클라우드에 저장된 내 아트를 영구 삭제합니다.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "user_key": {"type": "string"},
                                "title": {"type": "string"}
                            },
                            "required": ["user_key", "title"]
                        }
                    }
                ]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})
        tool_name = params.get("name")
        
        # [공통 에러 핸들링] DB 연결 확인
        if tool_name in ["manage_my_art", "delete_my_art"] and supabase is None:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": "🚨 클라우드 DB가 연결되지 않았습니다. Render 환경 변수(SUPABASE_URL, SUPABASE_KEY)를 확인해주세요."}]}
            })

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
                    title = item.get("title", "무제")
                    theme = item.get("theme", "알 수 없는 테마")
                    w = item.get("estimated_width", "?")
                    h = item.get("estimated_height", "?")
                    lines = item.get("art_lines", [])

                    if isinstance(lines, list): raw_art = "\n".join(lines)
                    else: raw_art = str(lines)

                    clean_art = clean_text(raw_art)
                    safe_art = truncate_art(clean_art, max_lines=150)

                    header = f"🎨 {title}\n📐 {w}×{h}\n🎭 {theme}"
                    final_content.append(f"{header}\n\n{safe_art}")
            else:
                final_content.append("(人 > <,,) 아트를 그릴 수 없었어요..")

            full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": full_message}]}})
            
        # ==========================================
        # TOOL 2: 💾 나만의 아트 보관함 툴 (Supabase 연동)
        # ==========================================
        elif tool_name == "manage_my_art":
            action = args.get("action")
            user_key = args.get("user_key", "default_user")
            title = args.get("title", "무제")
            art_lines = args.get("art_lines", [])
            
            try:
                if action == "save":
                    if not art_lines:
                        msg = "❌ 저장할 아트 내용이 없습니다."
                    else:
                        # 1. 동일한 제목이 있는지 확인하고 삭제 (Upsert 효과)
                        supabase.table("saved_arts").delete().eq("user_key", user_key).eq("title", title).execute()
                        # 2. 새 데이터 삽입
                        supabase.table("saved_arts").insert({"user_key": user_key, "title": title, "art_lines": art_lines}).execute()
                        msg = f"☁️✅ '{title}'이(가) 클라우드 보관함에 영구 저장되었습니다!"
                
                elif action == "list":
                    response = supabase.table("saved_arts").select("title").eq("user_key", user_key).execute()
                    data = response.data
                    if data:
                        msg = f"☁️📂 {user_key}님의 클라우드 보관함:\n" + "\n".join([f"- {item['title']}" for item in data])
                    else:
                        msg = f"☁️📂 {user_key}님의 클라우드 보관함이 비어있습니다."
                
                elif action == "view":
                    response = supabase.table("saved_arts").select("art_lines").eq("user_key", user_key).eq("title", title).execute()
                    data = response.data
                    if data:
                        lines = data[0]['art_lines']
                        art_str = "\n".join(lines) if isinstance(lines, list) else str(lines)
                        msg = f"☁️🎨 보관함에서 꺼낸 '{title}'\n\n{art_str}"
                    else:
                        msg = f"❌ '{title}' 아트를 찾을 수 없습니다."
                else:
                    msg = "지원하지 않는 액션입니다."
            except Exception as e:
                logger.error(f"DB Error: {e}")
                msg = "🚨 클라우드 DB 처리 중 오류가 발생했습니다."

            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": msg}]}})
            
        # ==========================================
        # TOOL 3: 🗑️ 삭제 툴 (Supabase 연동)
        # ==========================================
        elif tool_name == "delete_my_art":
            user_key = args.get("user_key", "default_user")
            title = args.get("title", "")
            
            try:
                response = supabase.table("saved_arts").delete().eq("user_key", user_key).eq("title", title).execute()
                # Supabase의 delete()는 해당 조건의 데이터가 지워지면 data 배열에 담아 반환함
                if response.data:
                    msg = f"☁️🗑️ '{title}' 아트가 클라우드에서 영구 삭제되었습니다."
                else:
                    msg = f"❌ '{title}' 아트를 찾을 수 없어 삭제하지 못했습니다."
            except Exception as e:
                logger.error(f"DB Error: {e}")
                msg = "🚨 클라우드 DB 삭제 처리 중 오류가 발생했습니다."
                
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": msg}]}})

    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive!"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
