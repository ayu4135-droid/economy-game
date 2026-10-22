"""Economic Crossroads: classroom real-time polling game. Run: pip install -r requirements.txt && python server.py"""
import asyncio
import io
import re
import json
import os
import random
import secrets
import string
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import qrcode

app = FastAPI(title='경제의 갈림길')
BASE = Path(__file__).resolve().parent
app.mount('/assets', StaticFiles(directory=BASE / 'assets'), name='assets')
ROOMS = {}
LOCK = asyncio.Lock()
INITIAL = {'growth':50,'freedom':50,'equality':50,'stability':50,'happiness':50}
LABELS = {'growth':'경제 성장','freedom':'경제적 자유','equality':'경제적 평등','stability':'경제 안정성','happiness':'국민 만족도'}

# Effects are game design scenarios, not empirical predictions.
ROUNDS = [{'title': '나라의 첫 식량 계획', 'story': '새로운 나라에 식량이 부족합니다. 농경지와 일손은 한정되어 있습니다. 무엇을 얼마나 생산할지 정해야 합니다.', 'options': [('농민과 기업이 소비자의 구매와 가격을 살펴 재배할 작물을 직접 결정하도록 한다.', {'growth': 5, 'freedom': 6, 'equality': -3, 'stability': -2, 'happiness': 2}, '농민들은 잘 팔리는 작물로 빠르게 전환했습니다. 다만 구매력이 낮은 지역에는 식량 공급이 부족해졌습니다.', 'market'), ('정부가 지역별 필요량을 조사해 작물과 생산 목표를 정하고 농장에 할당한다.', {'growth': 3, 'freedom': -4, 'equality': 6, 'stability': 4, 'happiness': 2}, '정부는 기본 식량을 넓게 배분했습니다. 하지만 일부 농장에는 지역 사정과 맞지 않는 생산 목표가 내려왔습니다.', 'plan')]}, {'title': '갑작스러운 간식 유행', 'story': '새 간식의 인기가 빠르게 높아졌지만 정확한 수요는 아직 알 수 없습니다. 공장의 생산 설비를 어떻게 바꿀까요?', 'options': [('정부가 조사한 수요를 토대로 공장별 생산 목표를 정하고, 기본 간식 공급도 유지하도록 한다.', {'growth': 3, 'freedom': -3, 'equality': 4, 'stability': 4, 'happiness': 1}, '기본 간식 공급은 안정됐지만, 새 간식 수요를 정확히 예측하지 못한 지역에서는 품절과 재고가 함께 나타났습니다.', 'plan'), ('각 공장이 판매 추이를 보고 생산량을 조정하며 인기 제품을 놓고 경쟁하도록 한다.', {'growth': 5, 'freedom': 5, 'equality': -2, 'stability': -3, 'happiness': 2}, '인기 간식 종류가 빠르게 늘었지만 유행이 꺾인 뒤 일부 공장은 재고 부담을 겪었습니다.', 'market')]}, {'title': '강을 지키면서 공장을 운영하려면?', 'story': '강 주변 공장이 늘면서 일자리도 생겼지만 수질 관리가 필요해졌습니다. 배출량을 줄이면서 생산을 이어갈 방법을 선택하세요.', 'options': [('정부가 공장별 배출 허용량과 설비 기준을 정하고 직접 점검한다.', {'growth': -2, 'freedom': -3, 'equality': 4, 'stability': 5, 'happiness': 3}, '오염 기준을 일관되게 관리했습니다. 다만 모든 공장에 같은 방식으로 설비를 적용해 일부 업체의 비용 부담이 커졌습니다.', 'regulate'), ('정부가 전체 배출 한도를 정하되, 기업들이 배출권을 거래하며 감축 방법을 결정하도록 한다.', {'growth': 3, 'freedom': 4, 'equality': -2, 'stability': 2, 'happiness': 2}, '감축 비용이 낮은 공장이 먼저 오염을 줄이는 유인이 생겼습니다. 다만 거래 비용과 배출권 가격 변동을 관리해야 했습니다.', 'mixed')]}, {'title': '국가 산업을 키워라', 'story': '새로운 철도망과 발전 시설을 건설해야 합니다. 막대한 자금이 필요한 사업입니다.', 'options': [('각 기업이 수익성을 계산해 투자 사업과 투자 규모를 결정한다.', {'growth': 6, 'freedom': 5, 'equality': -4, 'stability': -3, 'happiness': 2}, '수익성 높은 도시에 투자가 집중되어 경제가 성장했지만 외곽 지역은 뒤처졌습니다.', 'market'), ('정부가 주요 산업을 선정하고 건설 목표와 자원 투입량을 일괄 계획한다.', {'growth': 6, 'freedom': -5, 'equality': 4, 'stability': 4, 'happiness': 1}, '국가 핵심 시설이 빠르게 확충되었지만 필요성이 낮은 일부 시설에도 자원이 투입되었습니다.', 'plan')]}, {'title': '의료 시설을 어디에 늘릴까?', 'story': '도시에서는 병원이 늘지만 인구가 적은 지역에는 의료 시설이 부족합니다. 제한된 예산과 인력을 어떻게 배분할까요?', 'options': [('정부가 지역별 필수 의료 수요를 계산해 공공 의료시설과 의료 인력을 배치한다.', {'growth': -2, 'freedom': -3, 'equality': 6, 'stability': 4, 'happiness': 3}, '의료 취약 지역의 접근성이 개선되었습니다. 그러나 실제 이용 수요와 계획이 어긋난 일부 시설은 운영비가 많이 들었습니다.', 'regulate'), ('민간 병원이 지역 수요를 보고 진출하게 하되, 의료 취약 지역에는 정부가 진료비와 개설 비용을 지원한다.', {'growth': 4, 'freedom': 4, 'equality': 3, 'stability': -2, 'happiness': 3}, '새로운 의료 서비스가 빠르게 생겨났습니다. 다만 보조금이 부족한 지역은 여전히 의료시설 확보에 어려움을 겪었습니다.', 'mixed')]}, {'title': '운동화 주문이 늘었다', 'story': '최근 운동화 주문이 늘고 구두 주문은 줄었습니다. 하지만 수요가 계속될지는 불확실하고 설비를 바꾸는 데도 돈이 듭니다.', 'options': [('국가가 필요한 운동화 수량을 조사하고 공장별 전환 일정과 공급 목표를 정한다.', {'growth': 3, 'freedom': -4, 'equality': 5, 'stability': 4, 'happiness': 2}, '생산 시설을 순차적으로 전환해 필수 물량을 확보했습니다. 다만 예상보다 수요가 늘어난 지역에는 물량이 모자랐습니다.', 'plan'), ('각 공장이 주문량과 가격 변화를 보고 제품과 설비를 직접 바꾸도록 한다.', {'growth': 5, 'freedom': 6, 'equality': -3, 'stability': -3, 'happiness': 3}, '일부 공장이 인기 제품을 빠르게 공급했습니다. 하지만 설비 전환에 실패한 공장들은 손실을 입고 노동자들의 고용도 불안해졌습니다.', 'market')]}, {'title': '경기가 식고 일자리가 줄었다', 'story': '소비가 줄면서 여러 기업이 생산과 채용을 축소합니다. 제한된 국가 재원을 어떤 방식으로 활용할까요?', 'options': [('정부가 공공시설 보수와 필수재 생산 사업을 직접 계획해 일자리와 물자를 확보한다.', {'growth': 3, 'freedom': -3, 'equality': 5, 'stability': 4, 'happiness': 3}, '정부 사업으로 일정한 일자리를 유지했습니다. 다만 사업 우선순위를 잘못 정한 지역에서는 인력과 예산이 비효율적으로 쓰였습니다.', 'regulate'), ('정부가 기업의 대출 부담을 낮추고 신규 투자에 한시적 지원을 제공해 민간 생산 회복을 유도한다.', {'growth': 4, 'freedom': 4, 'equality': -3, 'stability': -2, 'happiness': 2}, '투자 여력이 있는 기업의 생산이 살아났습니다. 반면 회복 속도가 느린 업종에서는 고용 감소가 이어졌습니다.', 'mixed')]}, {'title': '대홍수, 생필품을 공급하라', 'story': '홍수로 도로와 공장이 피해를 입었습니다. 식수와 의료 물품을 신속하게 확보해야 합니다.', 'options': [('기업이 물류와 생산을 신속하게 조정하고 정부는 긴급 구호를 보완한다.', {'growth': 3, 'freedom': 5, 'equality': 1, 'stability': 2, 'happiness': 3}, '여러 공급망이 살아났습니다. 다만 교통망이 끊긴 지역에는 공공 구호가 꼭 필요했습니다.', 'mixed'), ('국가가 보유 물자를 모아 지역별 우선 배분량을 직접 지정한다.', {'growth': -2, 'freedom': -4, 'equality': 6, 'stability': 6, 'happiness': 4}, '긴급 물자가 필요한 지역에 집중 배분되었습니다. 일부 지역의 세부 수요를 파악하는 데는 시간이 걸렸습니다.', 'plan')]}, {'title': '발명가의 새로운 기술', 'story': '한 청년이 획기적인 배터리 기술을 개발했습니다. 기술을 전국으로 확산하려면 어떻게 해야 할까요?', 'options': [('정부가 연구개발을 국가 사업으로 편성하고 지정 공장에서 생산한다.', {'growth': 5, 'freedom': -4, 'equality': 4, 'stability': 3, 'happiness': 2}, '대규모 연구 자원을 모을 수 있었지만 민간의 다양한 시도는 줄어들었습니다.', 'plan'), ('발명가와 기업들이 투자자를 모으고 서로 경쟁하며 제품을 개발한다.', {'growth': 7, 'freedom': 8, 'equality': -4, 'stability': -4, 'happiness': 3}, '다양한 신제품이 등장했습니다. 하지만 실패한 기업들의 투자 손실도 커졌습니다.', 'market')]}, {'title': '앞으로 10년, 생산 방향을 정하라', 'story': '새 산업에 투자해야 하지만 미래에 어떤 물건과 기술이 많이 필요할지는 확실하지 않습니다. 생산의 방향을 누가 결정할까요?', 'options': [('국가가 주요 산업의 생산 목표와 투자 규모를 정해 장기 계획에 따라 추진한다.', {'growth': 4, 'freedom': -5, 'equality': 5, 'stability': 4, 'happiness': 2}, '장기 기반 시설과 생산 능력을 집중적으로 확충했습니다. 그러나 목표가 실제 수요와 맞지 않는 분야에는 자원이 묶였습니다.', 'plan'), ('기업과 소비자가 가격과 수요를 바탕으로 투자 방향을 선택하고 정부는 기본 규칙을 마련한다.', {'growth': 5, 'freedom': 5, 'equality': -3, 'stability': -3, 'happiness': 3}, '여러 기업이 새로운 산업에 도전해 혁신이 활발했습니다. 그러나 수익이 느리게 나는 분야에는 투자가 부족하고 일부 투자가 과열됐습니다.', 'market')]}]

def sanitize(s,n=20):
    return ''.join(c for c in str(s)[:n] if c.isalnum() or c in '가나다라마바사아자차카타파하 -_').strip() or '학생'

def public_state(room, role, pid=None):
    ridx=room['round']; finished=ridx>=len(ROUNDS); current=None if finished else ROUNDS[ridx]
    votes=room['votes']; counts=Counter(votes.values()); revealed=room['phase']=='revealed'
    result=room.get('last_result') if revealed else None
    return {'type':'state','room':room['code'],'role':role,'round':ridx,'total_rounds':len(ROUNDS),'phase':room['phase'],'stats':room['stats'],'labels':LABELS,'players':len(room['players']), 'voted':len(votes), 'votes':counts if role=='host' or revealed else None, 'my_vote':votes.get(pid) if pid else None,'current':({'title':current['title'],'story':current['story'],'options':[o[0] for o in current['options']]} if current else None), 'result':result,'history':room['history'] if finished or role=='host' else None,'ending':ending(room) if finished else None}

def ending(room):
    """Mutually exclusive ending precedence; calibrated against all 2^10 vote outcomes.

    Scores are classroom game abstractions, not rankings of real economic systems.
    """
    s = room['stats']
    n = Counter(h['kind'] for h in room['history'])
    growth, freedom, equality, stability = (s[k] for k in ('growth', 'freedom', 'equality', 'stability'))

    # Severe combined vulnerability, rather than an unreachable 0-point condition.
    if stability <= 38 and equality <= 48:
        title = '국가 운영 위기'
        msg = '경제 안정성과 분배 여건이 동시에 악화되어 어려움이 커졌습니다. 공급과 생활 안정을 회복할 대책이 필요합니다.'
    elif stability <= 43:
        title = '위기에 흔들리는 나라'
        msg = '경제 성장의 성과와 별개로 충격에 대응하는 힘이 부족합니다. 변동에 대비할 장치를 마련해야 합니다.'
    elif freedom >= 75 and equality <= 48:
        title = '혁신은 눈부시지만 격차가 큰 나라'
        msg = '자유로운 경제활동과 혁신은 활발하지만 경제적 격차가 커졌습니다. 성장의 성과를 어떻게 나눌지 고민해야 합니다.'
    elif equality >= 68 and freedom <= 42:
        title = '평등을 추구하지만 선택이 제한된 나라'
        msg = '생활 여건을 고르게 만드는 데 힘썼지만 경제적 선택의 폭이 좁아졌습니다. 다양한 시도를 넓힐 방안을 고민해야 합니다.'
    elif min(s.values()) >= 49 and max(s.values()) - min(s.values()) <= 30:
        title = '균형을 찾아가는 나라'
        msg = '다섯 목표 사이의 격차를 비교적 작게 유지했습니다. 앞으로도 성장·자유·평등·안정을 함께 고려해야 합니다.'
    else:
        title = '새로운 선택을 고민하는 나라'
        msg = '어느 한 방향으로만 설명하기 어려운 성과와 과제가 함께 나타났습니다. 앞으로의 우선순위를 새롭게 정할 때입니다.'
    return {'title': title, 'message': msg, 'counts': dict(n),
            'reflection': '누가 경제 문제를 결정했는가? 자유로운 선택과 계획적 배분은 각각 언제 효과적이었는가?'}

async def broadcast(room):
    dead=[]
    for ws, meta in list(room['sockets'].items()):
        try: await ws.send_json(public_state(room,meta['role'],meta.get('pid')))
        except Exception: dead.append(ws)
    for ws in dead: room['sockets'].pop(ws,None)

@app.get('/')
async def index(): return FileResponse(BASE/'index.html')

@app.get('/api/qr/{room_code}')
async def room_qr(room_code: str, request: Request):
    room_code = room_code.upper()
    if not re.fullmatch(r'[A-Z0-9]{5}', room_code):
        raise HTTPException(status_code=400, detail='Invalid room code')
    # Encode only the public student joining URL. Never include the host token.
    scheme = request.headers.get('x-forwarded-proto', request.url.scheme).split(',')[0].strip()
    if scheme not in ('http', 'https'):
        scheme = 'https'
    host = request.headers.get('host', request.url.netloc)
    url = f'{scheme}://{host}/?room={room_code}'
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    picture = qr.make_image(fill_color='black', back_color='white')
    out = io.BytesIO()
    picture.save(out, format='PNG')
    return Response(content=out.getvalue(), media_type='image/png', headers={'Cache-Control':'no-store'})

@app.get('/health')
async def health(): return {'ok':True}

@app.post('/api/rooms')
async def create_room():
    async with LOCK:
        alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        code=''.join(secrets.choice(alphabet) for _ in range(5))
        while code in ROOMS: code=''.join(secrets.choice(alphabet) for _ in range(5))
        token=secrets.token_urlsafe(24)
        ROOMS[code]={'code':code,'token':token,'stats':dict(INITIAL),'players':{},'votes':{},'phase':'lobby','round':0,'last_result':None,'history':[],'sockets':{}}
    return {'code':code,'host_token':token}

@app.websocket('/ws/{code}')
async def ws_connect(ws:WebSocket,code:str):
    await ws.accept(); code=code.upper()
    room=ROOMS.get(code)
    if not room:
        await ws.send_json({'type':'error','message':'게임방을 찾을 수 없습니다.'}); await ws.close(); return
    role=None; pid=None
    try:
        init=await asyncio.wait_for(ws.receive_json(),timeout=20)
        if init.get('action')!='join': raise ValueError('접속 정보가 올바르지 않습니다.')
        role='host' if init.get('token')==room['token'] else 'student'
        if role=='student':
            pid=str(init.get('pid') or secrets.token_urlsafe(12))[:64]
            room['players'][pid]='익명 참가자'
        room['sockets'][ws]={'role':role,'pid':pid}
        await ws.send_json({'type':'joined','role':role,'pid':pid})
        await broadcast(room)
        while True:
            data=await ws.receive_json(); action=data.get('action')
            if action=='vote' and role=='student' and room['phase']=='voting' and room['round']<len(ROUNDS):
                pick=data.get('choice')
                if type(pick) is int and pick in (0,1): room['votes'][pid]=pick
            elif role=='host' and action=='start' and room['phase']=='lobby':
                room['phase']='voting'
            elif role=='host' and action=='reveal' and room['phase']=='voting' and room['round']<len(ROUNDS):
                counts=Counter(room['votes'].values())
                if not counts: await ws.send_json({'type':'notice','message':'먼저 학생 투표를 받아 주세요.'});continue
                if counts[0]==counts[1]:
                    await ws.send_json({'type':'notice','message':'동점입니다. 교사가 결선 선택을 해주세요.'}); continue
                await apply_result(room,0 if counts[0]>counts[1] else 1,dict(counts))
            elif role=='host' and action=='tiebreak' and room['phase']=='voting':
                counts=Counter(room['votes'].values()); pick=data.get('choice')
                if counts[0]==counts[1] and len(room['votes'])>0 and type(pick) is int and pick in (0,1): await apply_result(room,pick,dict(counts))
            elif role=='host' and action=='next' and room['phase']=='revealed':
                room['round']+=1; room['votes']={};room['last_result']=None;room['phase']='finished' if room['round']>=len(ROUNDS) or min(room['stats'].values())<=0 else 'voting'
            elif role=='host' and action=='reset':
                room['round']=0;room['phase']='lobby';room['votes']={};room['history']=[];room['stats']=dict(INITIAL);room['last_result']=None
            await broadcast(room)
    except (WebSocketDisconnect, asyncio.TimeoutError): pass
    except Exception as e:
        try: await ws.send_json({'type':'error','message':str(e)[:120]})
        except Exception: pass
    finally:
        room['sockets'].pop(ws,None)
        if role=='student' and pid and not any(m.get('pid')==pid for m in room['sockets'].values()):
            # Retain registered voters through reconnect; count joined students only.
            pass
        await broadcast(room)

async def apply_result(room,pick,counts):
    r=ROUNDS[room['round']]; option=r['options'][pick]; effect=dict(option[1]); old=dict(room['stats']); tags=[h['kind'] for h in room['history']]; bonus=[]
    if room['round']==6 and tags.count('market')>=4:
        effect['stability']-=2; bonus.append('이전의 시장 중심 정책이 누적된 상태에서 경기 충격이 더 크게 나타났습니다. (경제 안정성 -2점)')
    if room['round']==7 and ('regulate' in tags):
        effect['happiness']+=2; bonus.append('앞서 마련한 공공 대응 체계가 긴급 구호에 도움이 되었습니다. (국민 만족도 +2점)')
    if room['round']==8 and tags.count('market')>=4 and option[3]=='market':
        effect['growth']+=2; bonus.append('민간 혁신 경험이 쌓여 신기술 상용화가 빨라졌습니다. (경제 성장 +2점)')
    for k,v in effect.items(): room['stats'][k]=max(0,min(100,room['stats'][k]+v))
    result={'pick':pick,'counts':counts,'text':option[2], 'effect':effect,'bonus':bonus,'old':old,'new':dict(room['stats']),'choice':option[0]}
    room['last_result']=result;room['history'].append({'round':room['round']+1,'title':r['title'],'choice':option[0],'kind':option[3],'pick':pick,'effect':effect});room['phase']='revealed'

if __name__=='__main__':
    uvicorn.run(app,host='0.0.0.0',port=int(os.getenv('PORT','8000')))
