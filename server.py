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
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import qrcode

app = FastAPI(title='경제의 갈림길')
BASE = Path(__file__).resolve().parent
ROOMS = {}
LOCK = asyncio.Lock()
INITIAL = {'growth':50,'freedom':50,'equality':50,'stability':50,'happiness':50}
LABELS = {'growth':'경제 성장','freedom':'자율성·창의성','equality':'경제적 평등','stability':'경제 안정성','happiness':'국민 만족도'}

# Effects are game design scenarios, not empirical predictions.
ROUNDS = [
 dict(title='나라의 첫 식량 계획',story='새로운 나라에 식량이 부족합니다. 농경지와 일손은 한정되어 있습니다. 무엇을 얼마나 생산할지 정해야 합니다.',options=[('농민과 기업이 소비자의 구매와 가격을 살펴 재배할 작물을 직접 결정하도록 한다.',{'growth':5,'freedom':6,'equality':-3,'stability':-2,'happiness':2},'농민들은 잘 팔리는 작물로 빠르게 전환했습니다. 다만 구매력이 낮은 지역에는 식량 공급이 부족해졌습니다.','market'),('정부가 지역별 필요량을 조사해 작물과 생산 목표를 정하고 농장에 할당한다.',{'growth':3,'freedom':-4,'equality':6,'stability':4,'happiness':2},'정부는 기본 식량을 넓게 배분했습니다. 하지만 일부 농장에는 지역 사정과 맞지 않는 생산 목표가 내려왔습니다.','plan')]),
 dict(title='새로운 간식 열풍',story='갑자기 전국에서 새로운 간식이 유행합니다. 기존 간식만 생산하던 공장은 어떻게 해야 할까요?',options=[('정부가 수요를 조사한 뒤 공장별 새 간식 생산 목표를 다시 정한다.',{'growth':3,'freedom':-3,'equality':4,'stability':3,'happiness':-2},'공장별 계획을 바꾸는 동안 시간이 걸려 한동안 인기 상품이 부족했습니다.','plan'),('공장들이 판매량과 소비자 반응을 보고 제품 생산을 자유롭게 바꾼다.',{'growth':6,'freedom':6,'equality':-3,'stability':-3,'happiness':2},'여러 공장이 신제품을 내놓아 선택지가 늘었지만 일부 업체는 과잉 생산으로 손실을 보았습니다.','market')]),
 dict(title='공장 폐수가 강으로!',story='한 공장이 비용을 아끼려고 오염 처리 시설을 설치하지 않았습니다. 강이 오염되어 주민들이 피해를 보고 있습니다.',options=[('정부가 오염 배출 기준과 부담금을 정하고 위반 기업을 제재한다.',{'growth':-2,'freedom':-2,'equality':5,'stability':5,'happiness':4},'기업의 생산비가 늘었지만 수질이 개선되었습니다. 시장 경제에서도 정부의 규제가 필요하다는 사실을 확인했습니다.','regulate'),('기업이 소비자의 선택과 지역사회의 압력을 보고 자율적으로 개선하도록 한다.',{'growth':3,'freedom':4,'equality':-5,'stability':-4,'happiness':-3},'일부 기업은 친환경 생산으로 전환했지만 변화가 더딘 기업이 있어 오염 피해가 계속되었습니다.','market')]),
 dict(title='국가 산업을 키워라',story='새로운 철도망과 발전 시설을 건설해야 합니다. 막대한 자금이 필요한 사업입니다.',options=[('각 기업이 수익성을 계산해 투자 사업과 투자 규모를 결정한다.',{'growth':6,'freedom':5,'equality':-4,'stability':-3,'happiness':2},'수익성 높은 도시에 투자가 집중되어 경제가 성장했지만 외곽 지역은 뒤처졌습니다.','market'),('정부가 주요 산업을 선정하고 건설 목표와 자원 투입량을 일괄 계획한다.',{'growth':6,'freedom':-5,'equality':4,'stability':4,'happiness':1},'국가 핵심 시설이 빠르게 확충되었지만 필요성이 낮은 일부 시설에도 자원이 투입되었습니다.','plan')]),
 dict(title='소득 격차가 벌어졌다',story='일부 사람의 소득은 크게 늘었지만 어려운 가정은 필수적인 의료 서비스도 이용하기 힘들어졌습니다.',options=[('정부가 필수 의료와 생계 지원을 확대하고 재원을 마련한다.',{'growth':-2,'freedom':-1,'equality':7,'stability':4,'happiness':5},'취약 계층의 생활 여건이 개선되었습니다. 정부의 재정 부담과 정책 운영 효율성은 앞으로 살펴봐야 합니다.','regulate'),('기업 투자와 고용 확대를 우선하여 소득 증가를 유도한다.',{'growth':6,'freedom':5,'equality':-6,'stability':-3,'happiness':-1},'고용 기회가 늘었지만 당장 도움이 필요한 가정의 의료 문제는 충분히 해결되지 않았습니다.','market')]),
 dict(title='수요를 놓친 신발 공장',story='국민은 운동화를 원하지만, 기존의 구두 생산 계획이 유지되어 창고에 구두가 쌓이고 운동화는 부족해졌습니다.',options=[('국가가 공장별 생산 계획을 다시 계산하고 다음 분기부터 바꾼다.',{'growth':-3,'freedom':-3,'equality':2,'stability':-3,'happiness':-3},'새로운 계획을 수립했지만 현장의 변화 속도를 따라가지 못해 일부 물자가 계속 부족했습니다.','plan'),('판매량과 가격의 변화를 보고 공장이 직접 생산을 전환하도록 한다.',{'growth':6,'freedom':6,'equality':-2,'stability':1,'happiness':4},'판매가 부진한 제품의 생산이 줄고 운동화가 늘었습니다. 일부 공장은 전환 비용 때문에 어려움을 겪었습니다.','market')]),
 dict(title='경제가 갑자기 흔들린다',story='기업들의 과잉 투자와 소비 감소가 겹쳐 실업자가 늘고 있습니다. 국민들은 불안을 호소합니다.',options=[('시장 참여자들의 조정과 신규 투자를 우선하며 정부는 개입을 최소화한다.',{'growth':-4,'freedom':4,'equality':-4,'stability':-7,'happiness':-5},'일부 기업은 회복했지만 경제 전체의 수요 부족이 길어져 실업 문제가 심해졌습니다.','market'),('정부가 일자리 사업과 긴급 재정 지원을 실시한다.',{'growth':3,'freedom':-2,'equality':4,'stability':6,'happiness':5},'긴급 지출로 고용과 소비가 다소 회복됐지만 재정 부담과 사업의 비효율 가능성도 남았습니다.','regulate')]),
 dict(title='대홍수, 생필품을 공급하라',story='홍수로 도로와 공장이 피해를 입었습니다. 식수와 의료 물품을 신속하게 확보해야 합니다.',options=[('기업이 물류와 생산을 신속하게 조정하고 정부는 긴급 구호를 보완한다.',{'growth':3,'freedom':5,'equality':1,'stability':2,'happiness':3},'여러 공급망이 살아났습니다. 다만 교통망이 끊긴 지역에는 공공 구호가 꼭 필요했습니다.','mixed'),('국가가 보유 물자를 모아 지역별 우선 배분량을 직접 지정한다.',{'growth':-2,'freedom':-4,'equality':6,'stability':6,'happiness':4},'긴급 물자가 필요한 지역에 집중 배분되었습니다. 일부 지역의 세부 수요를 파악하는 데는 시간이 걸렸습니다.','plan')]),
 dict(title='발명가의 새로운 기술',story='한 청년이 획기적인 배터리 기술을 개발했습니다. 기술을 전국으로 확산하려면 어떻게 해야 할까요?',options=[('정부가 연구개발을 국가 사업으로 편성하고 지정 공장에서 생산한다.',{'growth':5,'freedom':-4,'equality':4,'stability':3,'happiness':2},'대규모 연구 자원을 모을 수 있었지만 민간의 다양한 시도는 줄어들었습니다.','plan'),('발명가와 기업들이 투자자를 모으고 서로 경쟁하며 제품을 개발한다.',{'growth':7,'freedom':8,'equality':-4,'stability':-4,'happiness':3},'다양한 신제품이 등장했습니다. 하지만 실패한 기업들의 투자 손실도 커졌습니다.','market')]),
 dict(title='국가의 마지막 선택',story='10년이 흘렀습니다. 이제 국가가 앞으로 우선해야 할 발전 방향을 정해야 합니다.',options=[('가격과 민간의 선택을 경제 운영의 중심에 두고, 필요한 분야는 규제와 복지로 보완한다.',{'growth':4,'freedom':5,'equality':2,'stability':3,'happiness':3},'시장의 유연성과 정부의 보완 기능을 함께 활용했습니다. 제도의 균형을 계속 점검해야 합니다.','mixed'),('국가가 생산 목표와 자원 배분을 더 폭넓게 정해 장기 발전 계획을 추진한다.',{'growth':4,'freedom':-5,'equality':6,'stability':4,'happiness':2},'장기 목표를 일관되게 추진했지만 현장의 다양한 선택과 변화에 대응하는 과제가 남았습니다.','plan')]),
]

def sanitize(s,n=20):
    return ''.join(c for c in str(s)[:n] if c.isalnum() or c in '가나다라마바사아자차카타파하 -_').strip() or '학생'

def public_state(room, role, pid=None):
    ridx=room['round']; finished=ridx>=len(ROUNDS); current=None if finished else ROUNDS[ridx]
    votes=room['votes']; counts=Counter(votes.values()); revealed=room['phase']=='revealed'
    result=room.get('last_result') if revealed else None
    return {'type':'state','room':room['code'],'role':role,'round':ridx,'total_rounds':len(ROUNDS),'phase':room['phase'],'stats':room['stats'],'labels':LABELS,'players':len(room['players']), 'voted':len(votes), 'votes':counts if role=='host' or revealed else None, 'my_vote':votes.get(pid) if pid else None,'current':({'title':current['title'],'story':current['story'],'options':[o[0] for o in current['options']]} if current else None), 'result':result,'history':room['history'] if finished or role=='host' else None,'ending':ending(room) if finished else None}

def ending(room):
    s=room['stats']; n=Counter(h['kind'] for h in room['history']);
    if min(s.values())<=0: title='국가 운영 위기'; msg='어떤 지표가 바닥나 국가 운영에 큰 위기가 찾아왔습니다.'
    elif s['growth']>=68 and s['freedom']>=68 and s['equality']<45: title='혁신은 눈부시지만 격차가 큰 나라'; msg='기업과 시민의 창의성이 성장을 이끌었지만 불평등 문제를 해결해야 합니다.'
    elif s['equality']>=68 and s['freedom']<43: title='평등을 추구하지만 선택이 제한된 나라'; msg='기본 생활을 고르게 보장하려 했지만 시민의 선택과 새로운 시도도 중요해졌습니다.'
    elif min(s.values())>=48: title='균형을 찾아가는 나라'; msg='시장과 정부의 역할을 활용해 여러 목표 사이의 균형을 추구했습니다.'
    elif s['stability']<37: title='위기에 흔들리는 나라'; msg='경제적 충격과 물자 공급 문제에 대응할 제도가 필요합니다.'
    else: title='새로운 선택을 고민하는 나라'; msg='경제 성장과 자율성, 평등과 안정을 함께 달성하기 위한 선택이 남아 있습니다.'
    return {'title':title,'message':msg,'counts':dict(n),'reflection':'누가 경제 문제를 결정했는가? 자유로운 선택과 계획적 배분은 각각 언제 효과적이었는가?'}

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
            room['players'][pid]=sanitize(init.get('name') or '학생')
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
        effect['stability']-=2; bonus.append('이전의 시장 중심 정책이 누적된 상태에서 경기 충격이 더 크게 나타났습니다.')
    if room['round']==7 and ('regulate' in tags):
        effect['happiness']+=2; bonus.append('앞서 마련한 공공 대응 체계가 긴급 구호에 도움이 되었습니다.')
    if room['round']==8 and tags.count('market')>=4 and option[3]=='market':
        effect['growth']+=2; bonus.append('민간 혁신 경험이 쌓여 신기술 상용화가 빨라졌습니다.')
    for k,v in effect.items(): room['stats'][k]=max(0,min(100,room['stats'][k]+v))
    result={'pick':pick,'counts':counts,'text':option[2], 'effect':effect,'bonus':bonus,'old':old,'new':dict(room['stats']),'choice':option[0]}
    room['last_result']=result;room['history'].append({'round':room['round']+1,'title':r['title'],'choice':option[0],'kind':option[3],'pick':pick,'effect':effect});room['phase']='revealed'

if __name__=='__main__':
    uvicorn.run(app,host='0.0.0.0',port=int(os.getenv('PORT','8000')))
