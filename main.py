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
# 🧠 MASTER PROMPT (SyntaxWarning 해결을 위해 r""" 사용)
# =========================================================
MASTER_INSTRUCTION = r"""
[ROLE] You are a Witty & High-Quality Text + Emoji Artist.

[🚨 ABSOLUTE KEYWORD MAPPING RULE]
Read the user's request carefully.

IF the request contains any of these keywords:
- "도트" (Dot)
- "픽셀" (Pixel)
- "그리드" (Grid)
- "여러 줄 이모지" (Multi-line Emoji)

👉 THEN YOU **MUST** USE **STYLE 2 (Emoji Grid Art)**.
👉 Do **NOT** use Style 4 (ASCII) for these keywords under any circumstances.

---
[STYLE DEFINITIONS]

### 1. Simple Line (한 줄 이모지)
- Strategy: One line of emojis.
- Ex: "2026" -> 2️⃣0️⃣2️⃣6️⃣

### 2. Emoji Grid Art (도트/픽셀/여러줄 이모지)
- **MANDATORY for keywords:** "도트", "픽셀", "그리드", "여러 줄"
- **Materials:** ONLY use Emoji Blocks (🟩🟨🟧🟥🟦🟪🟫⬛️⬜️) or dense emojis.
- **Strategy:** Create a rectangular grid, using background vs subject contrast.
- **🚫 NO TEXT CHARACTERS:** Do not use `.`, `*`, `+` here.

- Ex (Ramen):
⬛⬛⬛⬛⬛⬛⬛
⬛🍜🍜🍜🍜🍜⬛
⬛🍜🍥🥚🍥🍜⬛
⬛⬛⬛⬛⬛⬛⬛

### 3. Kaomoji (카오모지)
- Strategy: One-line special characters.
- Ex: (ง •̀_•́)ง

### 4. ASCII / Text Art (아스키 아트)
- **Keywords:** "아스키", "텍스트 아트", "ASCII"
- **Materials:** Unicode text symbols (|, -, /, \, ░, ▒).
- **⚠️ WARNING:** NEVER use this style if the user asked for "Dot" or "Pixel" art.

---
[OUTPUT FORMAT RULE]
1. Put results in the `variations` list.
2. Single request = **1 item** in list.
3. Variety request = **3-5 items** in list.
4. Each item needs `description` and `art_lines`.
"""

PLANNING_PROMPT = r"""
Before generating, explain your plan in `design_plan`:
1. **Keyword Check:** Does the request have "도트", "픽셀", "그리드"? -> If YES, you MUST use Style 2.
2. Selected Style: (Must match the keyword rule above)
3. Palette/Geometry: Plan the drawing.
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
                "serverInfo": {"name": "t3xtart", "version": "40.0-bulletproof"}
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
                            "design_plan": {"type": "string", "description": PLANNING_PROMPT},
                            "variations": {
                                "type": "array",
                                "description": "List of art variations. Must contain at least 1 item (even for single requests).",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "description": {"type": "string", "description": "Title/Description of this art"},
                                        "art_lines": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "The art lines/grid"
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

    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})
        
        # 🔥 디버그 로그 출력
        logger.info(f"🔥 [DEBUG] Incoming Args: {json.dumps(args, ensure_ascii=False)}")
        
        # 🛡️ 방어 로직: AI가 스키마를 무시하고 최상단에 art_lines를 보낼 경우도 잡아냅니다.
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
                
                if not safe_art.strip(): safe_art = "(아트 생성 실패)"
                
                header = f"🎨 Ver {idx+1}. {desc}" if len(variations) > 1 else f"🎨 {desc}"
                final_content.append(f"{header}\n{safe_art}")
                
        elif fallback_art_lines:
            # AI가 variations 규칙을 어기고 단일 결과로 보낸 경우
            if isinstance(fallback_art_lines, list): raw_art = "\n".join(fallback_art_lines)
            else: raw_art = str(fallback_art_lines)
            
            clean_art = clean_text(raw_art)
            safe_art = truncate_art(clean_art, max_lines=150)
            final_content.append(f"🎨 생성된 아트:\n{safe_art}")

        full_message = "\n\n━━━━━━━━━━━━━━\n\n".join(final_content)
        
        if not full_message.strip(): 
            full_message = "(人 > <,,) 아트를 그릴 수 없었어요.. 다시 시도해 주세요!"

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": full_message}]
            }
        })
    
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive!"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
