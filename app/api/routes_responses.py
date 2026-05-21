# -*- coding: utf-8 -*-
import json, uuid, asyncio, logging
from typing import Any
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.pipeline.chat import ChatPipeline

router = APIRouter()
logger = logging.getLogger('kokoromemo.responses')
GPT_URL = 'http://127.0.0.1:10531/v1/responses'


def _is_gpt(m): return m.startswith('gpt-') if m else False

def _extract_text(c):
    if isinstance(c, str): return c
    if isinstance(c, list):
        return '\n'.join(i.get('text','') for i in c if isinstance(i,dict) and i.get('type') in {'input_text','output_text','text'})
    return ''

def _role(i):
    r = i.get('role','user')
    return r if r in {'system','user','assistant','developer'} else 'user'

def _msglist(inp):
    if isinstance(inp, str): return [{'role':'user','content':inp}]
    if not isinstance(inp, list): return []
    return [{'role':_role(i),'content':_extract_text(i.get('content'))} for i in inp if isinstance(i,dict) and _extract_text(i.get('content'))]


async def _gpt_handle(raw_body, request):
    messages = _msglist(raw_body.get('input'))
    if not messages:
        return JSONResponse(status_code=400, content={'error':{'message':'No input','type':'invalid_request'}})

    # Extract system prompt from instructions field for consistent character_id across models
    instructions = raw_body.get('instructions', '')
    if instructions:
        messages.insert(0, {'role': 'system', 'content': instructions[:2000]})

    meta = raw_body.get('metadata',{})
    if not isinstance(meta, dict): meta = {}
    openai_body = {
        'model': 'gpt-5.4', 'messages': messages, 'stream': False,
        'user': raw_body.get('user') or 'default',
        'metadata': {**meta, 'previous_response_id': raw_body.get('previous_response_id','')},
    }

    pipeline = ChatPipeline()
    try:
        prepared = await pipeline.prepare(request, raw_body=openai_body)
    except Exception as e:
        logger.warning('GPT prepare failed: %s', e)
        return JSONResponse(status_code=500, content={'error':{'message':f'Prepare: {e}'}})

    ctx, cfg = prepared.ctx, prepared.cfg
    # Reuse ChatPipeline.inject_memory for unified memory pipeline
    memory_text = None
    try:
        await pipeline.inject_memory(prepared)
        for msg in prepared.injected_messages:
            if msg.get('role') == 'system' and '【KokoroMemo' in msg.get('content',''):
                memory_text = msg['content']
                break
    except Exception as e:
        logger.warning('GPT memory failed: %s', e)

    # Build body for openai-oauth: strip internal fields, add memory as instructions
    forward_body = {k: v for k, v in raw_body.items() if k not in ('user','metadata','previous_response_id')}
    if memory_text:
        instructions = raw_body.get('instructions','') or ''
        forward_body['instructions'] = f'{instructions}\n\n{memory_text}'.strip()

    stream = bool(raw_body.get('stream', False))

    if stream:
        return _gpt_stream(forward_body, prepared, pipeline, messages)

    # Non-stream
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(GPT_URL, json=forward_body)
            if r.status_code != 200:
                return JSONResponse(status_code=502, content={'error':{'message':f'GPT upstream: {r.status_code}'}})
            data = r.json()
            # Record token usage (with cache tracking)
            try:
                u = data.get('usage', {})
                itok = u.get('input_tokens', 0)
                otok = u.get('output_tokens', 0)
                ctok = u.get('input_tokens_details', {}).get('cached_tokens', 0)
                if itok or otok:
                    import aiosqlite, asyncio as _asyncio, time as _t
                    async def _rec():
                        async with aiosqlite.connect(cfg.storage.sqlite.app_db) as _db:
                            await _db.execute('CREATE TABLE IF NOT EXISTS token_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, input_tokens INTEGER NOT NULL, cached_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL, created_at REAL NOT NULL)')
                            await _db.execute('INSERT INTO token_usage (input_tokens, cached_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?)', (itok, ctok, otok, _t.time()))
                            await _db.commit()
                    _asyncio.create_task(_rec())
            except: pass
            # Persist in background
            assistant = ''
            for o in data.get('output', []):
                for c in o.get('content', []):
                    if c.get('type') == 'output_text': assistant += c.get('text','')
            if assistant:
                asyncio.create_task(_gpt_persist(prepared, pipeline.services, messages, assistant))
            return JSONResponse(status_code=200, content=data)
    except Exception as e:
        logger.error('GPT upstream: %s', e)
        return JSONResponse(status_code=502, content={'error':{'message':f'GPT upstream: {e}'}})

    # Safety: should never reach here, but ensure a response is always returned
    return JSONResponse(status_code=500, content={'error':{'message':'GPT: unexpected code path'}})


def _gpt_stream(body, prepared, pipeline, messages):
    collected = []
    async def gen():
        nonlocal collected
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream('POST', GPT_URL, json=body) as r:
                if r.status_code != 200:
                    t = await r.aread()
                    yield f'data: {{"type":"error","error":{{"message":"{t.decode()[:200]}"}}}}\n\n'
                    yield 'data: [DONE]\n\n'; return
                async for line in r.aiter_lines():
                    if line:
                        yield f'{line}\n\n'
                        if line.startswith('data: ') and 'output_text.delta' in line:
                            try:
                                evt = json.loads(line[6:])
                                collected.append(evt.get('delta',''))
                            except: pass

    async def wrapped():
        async for c in gen(): yield c
        txt = ''.join(collected)
        if txt:
            await _gpt_persist(prepared, pipeline.services, messages, txt)

    return StreamingResponse(wrapped(), media_type='text/event-stream')


async def _gpt_persist(prepared, services, messages, assistant_text):
    try:
        from app.pipeline.chat import _persist_response_turn, _schedule_post_process_turn
        ctx = prepared.ctx
        tid, ti = await _persist_response_turn(ctx, list(messages), assistant_text,
                                                json.dumps({'content': assistant_text}), None)
        await _schedule_post_process_turn(ctx, prepared.cfg, services, list(messages),
                                           assistant_text, tid, ti, name=f'post_gpt:{ctx.request_id}')
    except Exception as e:
        logger.warning('GPT persist failed: %s', e)


# Non-GPT path (OpenAI chat via LiteLLM)
def request_to_openai(body):
    p = {'model': body.get('model'), 'messages': _msglist(body.get('input')),
         'stream': bool(body.get('stream'))}
    if body.get('temperature') is not None: p['temperature'] = body['temperature']
    if body.get('max_output_tokens') is not None: p['max_tokens'] = body['max_output_tokens']
    return p

def _oai_to_resp(data, body):
    ch = data.get('choices',[]); m = ch[0].get('message',{}) if ch else {}
    c = m.get('content') or ''; u = data.get('usage') or {}
    oc = [{'type':'output_text','text':c,'annotations':[]}]
    for tc in m.get('tool_calls') or []:
        fn = tc.get('function') or {}
        try: a = json.loads(fn.get('arguments','{}'))
        except: a = {}
        oc.append({'type':'function_call','id':tc.get('id',''),'call_id':tc.get('id',''),
                   'name':fn.get('name',''),'arguments':json.dumps(a, ensure_ascii=False)})
    return {'id':f'resp_{uuid.uuid4().hex[:24]}','object':'response',
            'created_at':data.get('created'),'model':data.get('model') or body.get('model'),
            'output':[{'id':f'msg_{uuid.uuid4().hex[:24]}','type':'message','role':'assistant',
                       'status':'completed','content':oc}],
            'usage':{'input_tokens':u.get('prompt_tokens',0),'output_tokens':u.get('completion_tokens',0),
                     'total_tokens':u.get('total_tokens',0)}}

@router.post('/v1/responses')
@router.post('/responses')
async def handler(request: Request):
    import logging, json
    body_bytes = await request.body()
    logging.getLogger('kokoromemo.raw').info(
        'REQ %s headers=%s body=%s',
        'handler',
        dict(request.headers),
        body_bytes.decode()[:800] if body_bytes else ''
    )
    import logging as _log, json as _json
    _log.getLogger('kokoromemo.raw').info('REQ headers=%s body=%s',
        {k:v for k,v in request.headers.items() if k.startswith('x-') or k in ('authorization','content-type','anthropic-version')},
        await request.body() and (await request.body()).decode()[:500])
    raw_body = await request.json()
    model = raw_body.get('model','')
    if _is_gpt(model):
        return await _gpt_handle(raw_body, request)
    openai_body = request_to_openai(raw_body)
    pr = await ChatPipeline().handle(request, raw_body=openai_body)
    if isinstance(pr, StreamingResponse):
        return StreamingResponse(_stream_legacy(pr, raw_body), media_type='text/event-stream')
    if isinstance(pr, JSONResponse):
        pl = json.loads(pr.body.decode('utf-8'))
        if pl.get('error'): return JSONResponse(status_code=pr.status_code, content=pl)
        return JSONResponse(status_code=pr.status_code, content=_oai_to_resp(pl, raw_body))
    return JSONResponse(status_code=500, content={'error':{'message':'Unexpected','type':'proxy_error'}})

async def _stream_legacy(oai_resp, body):
    rid, mid = f'resp_{uuid.uuid4().hex[:24]}', f'msg_{uuid.uuid4().hex[:24]}'
    m = body.get('model','')
    yield f'data: {json.dumps({"type":"response.created","response":{"id":rid,"object":"response","model":m,"output":[],"usage":None}})}\n\n'
    async for chunk in oai_resp.body_iterator:
        t = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
        for line in t.splitlines():
            line = line.strip()
            if not line.startswith('data: ') or line == 'data: [DONE]': continue
            try: pl = json.loads(line[6:])
            except: continue
            if pl.get('error'):
                yield f'data: {json.dumps({"type":"error","error":pl["error"]})}\n\n'
                yield 'data: [DONE]\n\n'; return
            d = (pl.get('choices') or [{}])[0].get('delta') or {}
            c = d.get('content')
            if c: yield f'data: {json.dumps({"type":"response.output_text.delta","item_id":mid,"output_index":0,"content_index":0,"delta":c})}\n\n'
    yield f'data: {json.dumps({"type":"response.completed","response":{"id":rid,"object":"response","model":m,"output":[{"id":mid,"type":"message","role":"assistant","status":"completed","content":[{"type":"output_text","text":"","annotations":[]}]}],"usage":{}}})}\n\n'
    yield 'data: [DONE]\n\n'
