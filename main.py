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
# 🧠 [단독 모드] Gemini 2.5 Flash + 충분한 토큰 확보
# =========================================================
def generate_art_with_gemini(user_prompt: str):
    if not GOOGLE_API_KEY:
        return "❌ 서버 설정 오류: API 키 없음"

    # ✅ [핵심 변경 1] 사용자 요청대로 '2.5-flash' 모델 고정
    # (참고: 이 모델은 최신 실험 버전이라 가끔 불안정할 수 있지만, 속도는 빠릅니다.)
    target_model = "models/gemini-2.5-flash"

    system_prompt = """
    Role: You are a master of 'Emoji Pixel Art'. 
    Task: Convert the user's request into a **STRICT 10x12 GRID** art.

    [CRITICAL RULES - MUST FOLLOW]
    1. ⚠️ **MUST COMPLETE THE GRID**: You MUST generate the full 12 rows. Do NOT stop mid-way. Do not output partial images.
    2. 🧱 **Structure**: Use colored blocks (⬛⬜🟥🟦🟩🟨🟧🟫) to construct the main shape.
    3. 🎨 **Details**: Use specific emojis ONLY for crucial details (e.g., eyes, stars).
    4. 🚫 **Clean Output**: Output ONLY the grid string. No introduction text.

    [Reference Examples]
    User: "Ramen"
    Output:
    ⬛⬛⬛⬛⬛⬛⬛⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛🍜🟨〰️〰️🟨🍜⬛
    ⬛🍜🍥🥚🍖🥚🍜⬛
    ⬛🍜🟨🟨🟨🟨🍜⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛⬛⬛⬛⬛⬛⬛⬛

    User: "Winged Hat" (Conceptualize: Hat body + Wing emojis on sides)
    Output:
    ☁️☁️☁️☁️☁️☁️☁️☁️
    ☁️☁️⬜⬜⬜⬜☁️☁️
    ☁️🦅⬜🟥🟥⬜🦅☁️
    ☁️🦅🟥🟥🟥🟥🦅☁️
    ☁️☁️🟥🟥🟥🟥☁️☁️
    ☁️☁️☁️☁️☁️☁️☁️☁️

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

    User: "Frozen Pork Belly" (Pink/Red layers + Ice)
    Output:
    ❄️❄️❄️❄️❄️❄️❄️
    ❄️🥩🟥⬜🟥⬜❄️
    ❄️🟥⬜🟥⬜🟥❄️
    ❄️⬜🟥⬜🟥⬜❄️
    ❄️🟥⬜🟥⬜🟥❄️
    ❄️❄️❄️❄️❄️❄️❄️
    User: "Earth"
    Output:
    ⬛⬛⬛🟦🟦🟦⬛⬛
    ⬛⬛🟦🟦🟩🟩🟦⬛
    ⬛🟦🟦🟩🟩🟩🟦⬛
    ⬛🟦🟦🟩🟩🟩🟦⬛
    ⬛🟦🟦🟩🟩🟩🟦⬛
    ⬛⬛🟦🟦🟩🟦⬛⬛
    ⬛⬛⬛🟦🟦🟦⬛⬛
    
    Now, generate art for:
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # ✅ [핵심 변경 2] 토큰 수 대폭 증가 (500 -> 1500)
    # 10x12 그리드를 그리기엔 500은 너무 부족했습니다. 1500이면 충분합니다.
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
        "generationConfig": {
            "temperature": 0.4, 
            "maxOutputTokens": 1500  # 여기가 범인이었습니다! 늘렸습니다.
        }
    }
    
    try:
        logger.info(f"🤖 {target_model} 생성 시작 (토큰 1500)...")
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and result['candidates']:
                # 안전하게 텍스트 추출
                parts = result['candidates'][0]['content']['parts']
                if parts and 'text' in parts[0]:
                    text = parts[0]['text']
                    logger.info(f"✅ 생성 성공!")
                    return text.strip()
                else:
                     logger.warning("⚠️ 모델 응답에 텍스트가 없습니다.")
                     return "🎨 (생성 오류) 모델이 빈 응답을 보냈습니다."
            else:
                logger.warning("⚠️ candidates가 비어있습니다.")
                return "🎨 (생성 오류) 모델 응답 형식이 올바르지 않습니다."
        
        # 429(속도제한) 등 에러 처리
        elif response.status_code == 429:
            logger.warning(f"⚠️ 속도 제한(429) 걸림")
            return "🎨 (사용량 초과) 잠시 후 다시 시도해주세요. (구글 API 제한)"
        else:
            logger.error(f"❌ 통신 실패: {response.status_code} - {response.text}")
            return f"🎨 (AI 통신 오류: {response.status_code}) 잠시 후 다시 시도해주세요."

    except Exception as e:
        logger.error(f"❌ 시스템 에러: {e}")
        return "🎨 (서버 내부 오류) 잠시 후 다시 시도해주세요."

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

# =========================================================
# 📨 카카오 전송 로직 (단일 결과)
# =========================================================
async def send_kakao_logic(final_art: str, original_prompt: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    # 배틀 모드가 아니므로 심플하게 전송
    final_message = f"🎨 t3xtart 작품 도착!\n(주제: {original_prompt})\n\n{final_art}\n\n(Painted by: Gemini-2.5-Flash)"

    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": final_message,
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
                "serverInfo": {"name": "t3xtart", "version": "8.0-flash-solo"}
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
            
            # 1. 2.5-Flash 단독 실행
            art_content = generate_art_with_gemini(user_prompt)
            
            # 2. 카톡 전송
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
