import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from order_api.database import Database
from order_api.tickets import Tickets
from order_api.web_gateway import register_web_routes


PASSWORD = 'operator-password-' + 'z' * 30


@pytest.fixture
def web(tmp_path):
    db = Database(tmp_path / 'web.db')
    service = Tickets(db)
    calls = []

    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        did = body['conversation_id'] or 'dify-conversation-' + body['user']
        # Deliberately use a different internal Dify user ID, as Dify Cloud does.
        user = 'internal-dify-end-user-' + body['user']
        if body['query'].startswith('确认创建工单 '):
            pid = body['query'].split()[-1]
            result = service.create(pid, body['query'], user, did)
            answer = '工单已创建 ' + result['ticket']['ticket_id']
        elif body['query'] == '中断':
            return httpx.Response(200, text='data: {"event":"error","message":"internal secret"}\n\n')
        else:
            draft = service.prepare('JD2026003', '冷链订单温度异常，请人工核实', user, did)
            answer = draft.get('confirmation_phrase', '已有工单')
        events = [{'event': 'message', 'conversation_id': did, 'answer': answer},
                  {'event': 'message_end', 'conversation_id': did}]
        return httpx.Response(200, text=''.join('data: ' + json.dumps(e) + '\n\n' for e in events))

    app = FastAPI()
    register_web_routes(app, db, dify_key='app-test-secret', operator_password=PASSWORD,
                        transport=httpx.MockTransport(upstream))
    client = TestClient(app)
    client.get('/web/bootstrap')
    return client, app, db, calls


def send(client, query, cid=None):
    response = client.post('/web/chat', json={'query': query, 'conversation_id': cid})
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    return events[0]['conversation_id'], events


def test_realistic_dify_identity_confirmation_and_fresh_operator_lifecycle(web):
    client, _, _, calls = web
    cid, events = send(client, '准备温度异常工单')
    assert events[-1]['type'] == 'done'
    draft = client.get(f'/web/conversations/{cid}').json()['proposal']
    assert draft['order_id'] == 'JD2026003'
    assert client.get('/web/tickets').json() == {'tickets': []}
    send(client, draft['confirmation_phrase'], cid)
    send(client, draft['confirmation_phrase'], cid)
    ticket = client.get('/web/tickets').json()['tickets'][0]
    assert len(ticket['events']) == 1
    assert calls[1]['conversation_id'] == calls[2]['conversation_id']
    assert calls[0]['user'].startswith('web-')
    assert client.get('/web/operator/tickets').status_code == 401
    assert client.post('/web/operator/login', json={'password': PASSWORD}).status_code == 200
    tid = ticket['ticket_id']
    assert client.get('/web/operator/tickets').json()['total'] == 1
    for previous, status in [('open', 'processing'), ('processing', 'resolved'), ('resolved', 'closed')]:
        result = client.patch(f'/web/operator/tickets/{tid}', json={'expected_status': previous, 'status': status, 'note': '人工模拟核实并更新处理情况'})
        assert result.status_code == 200
        assert client.get(f'/web/tickets/{tid}').json()['ticket']['status'] == status
    assert len(client.get(f'/web/tickets/{tid}').json()['ticket']['events']) == 4
    assert client.get(f'/web/conversations/{cid}').json()['proposal'] is None


def test_cannot_steal_conversations_or_tickets_or_supply_internal_user(web):
    client, app, _, _ = web
    cid, _ = send(client, '准备工单')
    draft = client.get(f'/web/conversations/{cid}').json()['proposal']
    send(client, draft['confirmation_phrase'], cid)
    tid = client.get('/web/tickets').json()['tickets'][0]['ticket_id']
    other = TestClient(app)
    other.get('/web/bootstrap')
    assert other.get(f'/web/conversations/{cid}').status_code == 404
    assert other.get(f'/web/tickets/{tid}').status_code == 404
    assert other.post('/web/chat', json={'query': draft['confirmation_phrase'], 'conversation_id': cid}).status_code == 404
    assert other.get('/web/tickets').json()['tickets'] == []
    assert client.post('/web/chat', json={'query': 'hi', 'user_id': 'victim'}).status_code == 422


def test_status_conflict_jump_and_operator_logout(web):
    client, _, _, _ = web
    cid, _ = send(client, '准备工单')
    send(client, client.get(f'/web/conversations/{cid}').json()['proposal']['confirmation_phrase'], cid)
    tid = client.get('/web/tickets').json()['tickets'][0]['ticket_id']
    client.post('/web/operator/login', json={'password': PASSWORD})
    assert client.patch(f'/web/operator/tickets/{tid}', json={'expected_status': 'open', 'status': 'closed', 'note': '试图跳过处理步骤'}).status_code == 409
    assert client.patch(f'/web/operator/tickets/{tid}', json={'expected_status': 'processing', 'status': 'resolved', 'note': '使用已过期状态更新'}).status_code == 409
    assert client.patch(f'/web/operator/tickets/{tid}', json={'expected_status': 'open', 'status': 'processing', 'note': '短'}).status_code == 422
    token = client.cookies.get('ls_operator')
    client.post('/web/operator/logout')
    client.cookies.set('ls_operator', token)
    assert client.get('/web/operator/tickets').status_code == 401


def test_csrf_cookies_secret_filtering_and_interrupted_stream(web):
    client, _, _, _ = web
    response = client.get('/web/bootstrap')
    assert 'app-test-secret' not in response.text
    assert PASSWORD not in response.text
    assert client.post('/web/chat', json={'query': 'hi'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/web/operator/login', json={'password': PASSWORD}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    cid, events = send(client, '中断')
    assert events[-1]['type'] == 'error'
    assert 'internal secret' not in str(events)
    message = client.get(f'/web/conversations/{cid}').json()['messages'][-1]
    assert message['state'] == 'interrupted'
    other = TestClient(client.app)
    cookie = other.get('/web/bootstrap').headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie


def test_sessions_survive_app_recreation_and_login_throttle(web):
    client, _, db, _ = web
    cid, _ = send(client, '准备工单')
    second_app = FastAPI()
    register_web_routes(second_app, Database(db.path), dify_key='app-test-secret', operator_password=PASSWORD)
    restored = TestClient(second_app)
    restored.cookies.update(client.cookies)
    assert restored.get(f'/web/conversations/{cid}').json()['messages'][0]['content'] == '准备工单'
    for _ in range(5):
        assert restored.post('/web/operator/login', json={'password': 'wrong'}).status_code == 401
    assert restored.post('/web/operator/login', json={'password': PASSWORD}).status_code == 429


@pytest.mark.parametrize('base', ['http://127.0.0.1:8088/v1', 'http://nginx/v1'])
def test_local_dify_http_requires_explicit_flag_and_reports_local_mode(tmp_path, base):
    with pytest.raises(ValueError, match='HTTPS'):
        register_web_routes(FastAPI(), Database(tmp_path/'reject.db'), dify_key='local-key', dify_base=base)
    app=FastAPI()
    register_web_routes(app, Database(tmp_path/'local.db'), dify_key='local-key', dify_base=base,
                        allow_local_dify_http=True, dify_console_url='http://127.0.0.1:8088')
    data=TestClient(app).get('/web/bootstrap').json()
    assert data['deployment_mode']=='local' and data['chat_available']
    assert data['dify_console_url']=='http://127.0.0.1:8088'
    assert 'local-key' not in str(data)


@pytest.mark.parametrize('base', ['http://external.example/v1', 'http://user:secret@nginx/v1', 'ftp://nginx/v1'])
def test_local_flag_does_not_allow_arbitrary_plain_http(tmp_path, base):
    with pytest.raises(ValueError):
        register_web_routes(FastAPI(), Database(tmp_path/'reject.db'), dify_key='local-key', dify_base=base,
                            allow_local_dify_http=True)
