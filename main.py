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
# 🧠 [배틀 모드] 엘리트 모델 2종 동시 출격
# =========================================================
def generate_art_battle_mode(user_prompt: str):
    if not GOOGLE_API_KEY:
        return [("❌ API 키 없음", "System Error")]

    # [강화된 프롬프트] 중도 포기 방지 및 구조 강제
    system_prompt = """
    Role: You are a master of 'Emoji Pixel Art'. 
    Task: Convert the user's request into a strict 10x12 grid art.

    [CRITICAL RULES - DO NOT BREAK]
    1. 📐 MUST fill the ENTIRE 10x12 grid. Do not output partial images or give up mid-way.
    2. 🧱 Use colored blocks (⬛⬜🟥🟦🟩🟨🟧🟫) to construct the main shape.
    3. 🎨 Use specific emojis ONLY for crucial details (e.g., eyes, wings).
    4. 🚫 NO explanation text. Output ONLY the grid string.

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

    Now, generate art for:
    """

    # ✅ 테스트를 위한 가장 안정적인 엘리트 모델 2종 고정
    battle_models = [
        "models/gemini-1.5-pro",   # 기호 1번: 똑똑이
        "models/gemini-1.5-flash"  # 기호 2번: 날쌘돌이
    ]
    
    battle_results = []

    for model_name in battle_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        headers = {"Content-Type": "application/json"}
        # temperature를 약간 높여서(0.5) 창의성을 부여하되 규칙은 지키게 함
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 500}
        }
        
        try:
            logger.info(f"🤖 {model_name} 생성 시작...")
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    battle_results.append((text.strip(), model_name)) # 결과 저장
                    logger.info(f"✅ {model_name} 성공!")
                else:
                    battle_results.append(("(생성된 내용 없음)", model_name))
            else:
                battle_results.append((f"(에러: {response.status_code})", model_name))
                logger.warning(f"⚠️ {model_name} 실패: {response.status_code}")

        except Exception as e:
            battle_results.append((f"(통신 에러: {e})", model_name))
            logger.error(f"❌ {model_name} 에러: {e}")
            
    return battle_results

# =========================================================
# 🔐 카카오 토큰 관리 (기존 유지)
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
# 📨 [수정됨] 카카오 전송 로직 (배틀 결과 합치기)
# =========================================================
async def send_kakao_battle_result(results_list: list, original_prompt: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    # 메시지 내용 구성 (결과 합치기)
    final_message = f"🎨 t3xtart 모델 성능 테스트\n(주제: {original_prompt})\n\n"
    for art, model_name in results_list:
        display_name = model_name.replace("models/", "").upper()
        final_message += f"➖➖➖➖➖➖➖➖\n🏆 [Artist: {display_name}]\n\n{art}\n\n"
    final_message += "➖➖➖➖➖➖➖➖"

    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": final_message,
                "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
                "button_title": "테스트 결과 자세히 보기"
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
TOOL_DESCRIPTION = "사용자가 원하는 그림의 주제를 받아, 최고의 Gemini 모델들이 경쟁하여 생성한 이모지 아트를 카카오톡으로 전송합니다."
INPUT_DESCRIPTION = "사용자의 요청 내용 (예: '날개 달린 모자 그려줘')"

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
                "serverInfo": {"name": "t3xtart", "version": "6.0-battle"}
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
            
            # 1. 배틀 모드 실행 (결과 리스트 반환)
            battle_results = generate_art_battle_mode(user_prompt)
            
            # 2. 카톡 전송 (결과 합쳐서)
            success, msg = await send_kakao_battle_result(battle_results, user_prompt)
            
            result_text = "✅ 모델 성능 테스트 결과 전송 완료!" if success else f"❌ 실패: {msg}"
            
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
