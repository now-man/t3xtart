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
# 🧠 [스마트 리스트] 엘리트 모델 우선 선발 로직
# =========================================================
def get_prioritized_models():
    """
    구글에서 사용 가능한 모델 리스트를 가져온 뒤,
    '그림 잘 그리는 순서(Pro > Flash > 기타)'로 정렬합니다.
    """
    if not GOOGLE_API_KEY:
        return []
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            data = res.json()
            all_models = [
                m['name'] for m in data.get('models', []) 
                if 'generateContent' in m.get('supportedGenerationMethods', [])
            ]
            
            # [우선순위 로직]
            # 1. 1.5-pro (가장 똑똑함, 픽셀 아트 이해도 높음)
            # 2. 1.5-flash (빠르고 준수함)
            # 3. 1.0-pro (구관이 명관)
            # 4. 나머지 (gemma 등 경량 모델은 멍청해서 뒤로 뺌)
            
            prioritized = []
            others = []
            
            for m in all_models:
                if "1.5-pro" in m:
                    prioritized.insert(0, m) # 1순위
                elif "1.5-flash" in m:
                    prioritized.append(m)    # 2순위
                elif "gemini-pro" in m:
                    prioritized.append(m)    # 3순위
                else:
                    others.append(m)         # 4순위
            
            final_list = prioritized + others
            logger.info(f"📋 [엘리트 모델 순서]: {final_list[:5]}...") # 상위 5개만 로그 출력
            return final_list
        else:
            logger.error(f"❌ 모델 리스트 실패: {res.text}")
            return []
    except Exception as e:
        logger.error(f"❌ 연결 에러: {e}")
        return []

def generate_art_with_gemini(user_prompt: str):
    if not GOOGLE_API_KEY:
        return "❌ 설정 오류: API 키 없음", "None"

    # 1. 사용 가능한 모델 리스트 가져오기 (똑똑한 순서)
    candidate_models = get_prioritized_models()
    
    if not candidate_models:
        return "🎨 (오류) 사용 가능한 모델이 없습니다.", "None"

    # [프롬프트] 예시를 통해 구조적 사고 강요
    system_prompt = """
    Role: You are a master of 'Emoji Pixel Art'. 
    Task: Convert the user's request into a strict 10x12 grid art using mostly square blocks.

    [STRICT RULES]
    1. ❌ DO NOT output simple emojis (e.g., just 🥩). You must DRAW the shape using colored blocks.
    2. 🧱 Use these blocks mainly: ⬛(Black), ⬜(White), 🟥(Red), 🟦(Blue), 🟩(Green), 🟨(Yellow), 🟧(Orange), 🟫(Brown).
    3. 🎨 You can use specific emojis for details (e.g., 👁️ for eyes), but the main body must be blocks.
    4. 📐 Output format: ONLY the grid string. No introduction. No text.

    [Reference Examples - Follow this style]

    User: "Ramen"
    Output:
    ⬛⬛⬛⬛⬛⬛⬛⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛🍜🟨〰️〰️🟨🍜⬛
    ⬛🍜🍥🥚🍖🥚🍜⬛
    ⬛🍜🟨🟨🟨🟨🍜⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛⬛⬛⬛⬛⬛⬛⬛

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

    # 2. 순서대로 시도
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        headers = {"Content-Type": "application/json"}
        # temperature 0.4: 창의성 약간 억제, 규칙 준수
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 400}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    logger.info(f"✅ 생성 성공! (Model: {model_name})")
                    return text.strip(), model_name # 성공한 아트와 모델명 반환
            
            # 실패 시 다음 모델로
            logger.warning(f"⚠️ 실패 ({model_name}): {response.status_code}")
            continue 

        except Exception as e:
            logger.error(f"❌ 에러 ({model_name}): {e}")
            continue
            
    return "🎨 (전체 실패) 모든 모델이 응답하지 않습니다.", "All Failed"

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

async def send_kakao_logic(final_art: str, original_prompt: str, model_used: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    # 모델명을 깔끔하게 다듬기 (models/gemini-1.5-pro -> gemini-1.5-pro)
    display_model = model_used.replace("models/", "")

    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 작품 도착!\n(주제: {original_prompt})\n\n{final_art}\n\n🖌️ Artist: {display_model}",
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
                "serverInfo": {"name": "t3xtart", "version": "5.0"}
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
            
            # 1. 그림 생성 + 모델 이름 받아오기
            art_content, model_used = generate_art_with_gemini(user_prompt)
            
            # 2. 카톡 전송 (모델 이름 포함)
            success, msg = await send_kakao_logic(art_content, user_prompt, model_used)
            
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
