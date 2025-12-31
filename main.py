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
# 🕵️‍♂️ [지능형 스카우터] 쓸 수 있는 '최고의 모델' 2개 찾기
# =========================================================
def get_battle_candidates():
    """
    구글 API에 접속해 현재 사용 가능한 모델 리스트를 받아온 뒤,
    'Pro'급과 'Flash'급 모델 중 가장 적합한 2개를 선별합니다.
    """
    if not GOOGLE_API_KEY:
        logger.error("❌ API 키가 없습니다.")
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code != 200:
            logger.error(f"❌ 모델 리스트 조회 실패: {res.text}")
            return []
            
        data = res.json()
        all_models = [
            m['name'] for m in data.get('models', []) 
            if 'generateContent' in m.get('supportedGenerationMethods', [])
        ]
        
        # [엄격한 필터링] 멍청한 모델(nano, gemma) 절대 사절
        # 우선순위: 1.5 Pro > 1.5 Flash > 1.0 Pro
        
        pro_models = [m for m in all_models if '1.5-pro' in m and 'vision' not in m]
        flash_models = [m for m in all_models if '1.5-flash' in m and 'vision' not in m]
        legacy_pro = [m for m in all_models if 'gemini-pro' in m and 'vision' not in m]
        
        candidates = []
        
        # 1번 선수: 지능형 (Pro 계열 최신)
        if pro_models:
            candidates.append(pro_models[0]) # 리스트의 첫 번째(보통 최신)
        elif legacy_pro:
            candidates.append(legacy_pro[0])
            
        # 2번 선수: 속도형 (Flash 계열 최신)
        if flash_models:
            candidates.append(flash_models[0])
            
        # 만약 리스트가 비었다면(권한 문제 등), 있는 것 중 아무거나 'gemini' 들어간 걸로 채움
        if len(candidates) < 2:
            others = [m for m in all_models if 'gemini' in m and m not in candidates]
            candidates.extend(others[:2-len(candidates)])
            
        logger.info(f"⚔️ [배틀 참가 선수 확정]: {candidates}")
        return candidates

    except Exception as e:
        logger.error(f"❌ 스카우팅 에러: {e}")
        return []

# =========================================================
# 🧠 [배틀 모드] 자동 선발된 모델로 생성
# =========================================================
def generate_art_battle_mode(user_prompt: str):
    # 1. 선수 선발
    battle_models = get_battle_candidates()
    
    if not battle_models:
        return [("❌ 사용 가능한 Gemini 모델을 찾지 못했습니다. (API Key 권한 확인)", "System Error")]

    # [프롬프트] 픽셀 아트 전문가 모드
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
    
    User: "Monkey under leaf"
    Output:
    🌿🌿🌿🌿🌿🌿🌿🌿
    🌿🌿🌿🌿🌿🌿🌿🌿
    🌿🌿🙈🙈🙈🙈🌿🌿
    🌿🌿🙈🐵🐵🙈🌿🌿
    🌿🌿💪🟫🟫💪🌿🌿
    🌿🌿🌿🟫🟫🌿🌿🌿

    Now, generate art for:
    """

    battle_results = []

    for model_name in battle_models:
        # model_name은 이미 'models/...' 형태임
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 500}
        }
        
        try:
            logger.info(f"🤖 {model_name} 생성 시도...")
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    battle_results.append((text.strip(), model_name))
                    logger.info(f"✅ {model_name} 성공!")
                else:
                    battle_results.append(("(내용 없음)", model_name))
            else:
                # 에러 메시지 간소화
                error_msg = f"Error {response.status_code}"
                if response.status_code == 404: error_msg = "Not Found (404)"
                if response.status_code == 403: error_msg = "Permission Denied (403)"
                battle_results.append((f"({error_msg})", model_name))
                logger.warning(f"⚠️ {model_name} 실패: {response.status_code}")

        except Exception as e:
            battle_results.append(("(통신 에러)", model_name))
            logger.error(f"❌ {model_name} 에러: {e}")
            
    return battle_results

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

async def send_kakao_battle_result(results_list: list, original_prompt: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    final_message = f"🎨 t3xtart 모델 배틀\n(주제: {original_prompt})\n\n"
    for art, model_name in results_list:
        # 모델명 깔끔하게 (models/gemini-1.5-pro-latest -> GEMINI-1.5-PRO...)
        short_name = model_name.replace("models/", "").split("-00")[0].upper()
        final_message += f"➖➖➖➖➖➖➖➖\n🏆 [{short_name}]\n\n{art}\n\n"
    final_message += "➖➖➖➖➖➖➖➖"

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
TOOL_DESCRIPTION = "사용자가 원하는 그림의 주제를 받아, 최고의 Gemini 모델들이 경쟁하여 생성한 이모지 아트를 카카오톡으로 전송합니다."
INPUT_DESCRIPTION = "사용자의 요청 내용 (예: '나뭇잎에 덮인 원숭이 그려줘')"

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
                "serverInfo": {"name": "t3xtart", "version": "7.0-auto-battle"}
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
            results = generate_art_battle_mode(user_prompt)
            success, msg = await send_kakao_battle_result(results, user_prompt)
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
