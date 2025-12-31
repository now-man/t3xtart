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

# 로그 설정
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

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# =========================================================
# 🧠 [업그레이드] 고퀄리티 아트 생성 엔진
# =========================================================
def generate_art_with_gemini(user_prompt: str):
    if not GOOGLE_API_KEY:
        return "❌ 서버 설정 오류: GOOGLE_API_KEY 없음"

    # [핵심] AI에게 주는 강력한 지령 (Few-Shot Prompting)
    # 예시를 직접 보여줘서 이대로만 하게 강제합니다.
    system_prompt = """
    Role: You are a master of 'Emoji Pixel Art'. 
    Task: Convert the user's request into a strict 10x12 grid art using mostly square blocks.

    [STRICT RULES]
    1. ❌ DO NOT output simple emojis (e.g., 🥩). You must DRAW the shape using colored blocks.
    2. 🧱 Use these blocks mainly: ⬛(Black), ⬜(White), 🟥(Red), 🟦(Blue), 🟩(Green), 🟨(Yellow), 🟧(Orange), 🟫(Brown).
    3. 🎨 You can use specific emojis for details (e.g., 👁️ for eyes, ⚡ for spark), but the main body must be blocks.
    4. 📐 Output format: ONLY the grid string. No introduction. No text.

    [High-Quality Examples]

    User: "Ramen"
    Output:
    ⬛⬛⬛⬛⬛⬛⬛⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛🍜🟨〰️〰️🟨🍜⬛
    ⬛🍜🍥🥚🍖🥚🍜⬛
    ⬛🍜🟨🟨🟨🟨🍜⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛⬛⬛⬛⬛⬛⬛⬛

    User: "Blue Star"
    Output:
    ⬛⬛⬛🟦⬛⬛⬛
    ⬛⬛🟦🟦🟦⬛⬛
    ⬛🟦🟦🟦🟦🟦⬛
    ⬛⬛🟦🟦🟦⬛⬛
    ⬛🟦⬛⬛⬛🟦⬛
    
    User: "Burning Jellyfish"
    Output:
    🌊🌊🌊🌊🌊🌊🌊
    🌊🌊🔥🔥🔥🔥🌊
    🌊🔥👁️🔥👁️🔥🌊
    🌊🔥🔥👄🔥🔥🌊
    🌊⚡️⚡️⚡️⚡️⚡️🌊
    🌊⚡️🌊⚡️🌊⚡️🌊
    
    User: "Frozen Pork Belly" (Concept: Pink/Red meat layers with Ice)
    Output:
    ❄️❄️❄️❄️❄️❄️❄️
    ❄️🥩🟥⬜🟥⬜❄️
    ❄️🟥⬜🟥⬜🟥❄️
    ❄️⬜🟥⬜🟥⬜❄️
    ❄️🟥⬜🟥⬜🟥❄️
    ❄️❄️❄️❄️❄️❄️❄️

    Now, generate art for the user's request.
    """

    # ✅ 정식 모델명 고정 (새 키가 있다면 무조건 됩니다)
    # 1.5 Flash가 가성비/지능 밸런스가 아트 생성에 가장 좋습니다.
    target_model = "models/gemini-1.5-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # temperature를 낮춰서(0.3) AI가 창의성보다 '규칙'을 따르게 합니다.
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and result['candidates']:
                text = result['candidates'][0]['content']['parts'][0]['text']
                logger.info(f"✅ 생성 성공 ({target_model})")
                return text.strip()
        
        # 만약 Flash가 안 되면 Pro로 한 번 더 시도
        logger.warning(f"⚠️ Flash 실패 ({response.status_code}). Pro 모델 시도.")
        return try_fallback_model(user_prompt, system_prompt)

    except Exception as e:
        logger.error(f"❌ 에러: {e}")
        return "🎨 (서버 에러) 잠시 후 다시 시도해주세요."

def try_fallback_model(user_prompt, system_prompt):
    """Flash 실패 시 Pro 모델(더 똑똑함)로 재시도"""
    target_model = "models/gemini-1.5-pro"
    url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}]
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(payload))
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass
    return "🎨 (오류) API 키를 확인해주세요."

# =========================================================
# 🔐 카카오 토큰 관리
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    rest_api_key = os.environ.get("KAKAO_CLIENT_ID")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")
    
    if not rest_api_key or not refresh_token:
        return False

    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token
    }
    if client_secret:
        data["client_secret"] = client_secret
    
    try:
        res = requests.post(url, data=data)
        if res.status_code == 200:
            new_tokens = res.json()
            CURRENT_ACCESS_TOKEN = new_tokens.get("access_token")
            return True
        return False
    except:
        return False

async def send_kakao_logic(final_art: str, original_prompt: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 작품 도착!\n(주제: {original_prompt})\n\n{final_art}",
                "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
                "button_title": "자세히 보기"
            })
        }
        return requests.post(url, headers=headers, data=payload)

    res = try_post(CURRENT_ACCESS_TOKEN)
    if res.status_code == 401:
        if refresh_kakao_token():
            res = try_post(CURRENT_ACCESS_TOKEN)
        else:
            return False, "토큰 갱신 실패"

    if res.status_code == 200:
        return True, "전송 성공"
    else:
        return False, f"카카오 에러: {res.text}"

# =========================================================
# 📝 도구 설명
# =========================================================
TOOL_DESCRIPTION = "사용자가 원하는 그림의 주제(예: '라면 그려줘', '사랑해 점자')를 텍스트로 받아 t3xtart 엔진으로 전달합니다."
INPUT_DESCRIPTION = "사용자의 요청 내용 그대로 입력하세요. (AI가 직접 이모지 아트를 생성하지 마십시오. 단지 요청 텍스트만 전달하세요.)"

# ---------------------------------------------------------
# 라우팅
# ---------------------------------------------------------
sse_transport = None

@app.get("/sse")
async def handle_sse(request: Request):
    global sse_transport
    sse_transport = SseServerTransport("/messages")
    async def stream():
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            while True:
                await asyncio.sleep(1) 
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/sse")
async def handle_sse_post(request: Request):
    try:
        body = await request.json()
    except:
        return JSONResponse({"status": "error"})

    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "t3xtart", "version": "4.0"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "generate_and_send_art",
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": INPUT_DESCRIPTION
                            }
                        },
                        "required": ["prompt"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "generate_and_send_art":
            user_prompt = args.get("prompt", "")
            art_content = generate_art_with_gemini(user_prompt)
            success, msg = await send_kakao_logic(art_content, user_prompt)
            
            result_text = "✅ 작품 생성 및 전송 완료!" if success else f"❌ 실패: {msg}"
            
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": not success
                }
            })
        
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "No tool"}})

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.post("/messages")
async def handle_messages(request: Request):
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
