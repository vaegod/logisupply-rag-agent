"""Real V3 HTTPS acceptance: browser gateway -> Dify -> same live ticket DB.

Set LOGISUPPLY_WEB_ORIGIN and LOGISUPPLY_WEB_OPERATOR_PASSWORD. No keys are
accepted from the browser or written into reports. Creates synthetic tickets.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main():
    origin = os.environ['LOGISUPPLY_WEB_ORIGIN'].rstrip('/')
    assert urlsplit(origin).scheme == 'https', 'Use actual deployed HTTPS origin'
    password = os.environ['LOGISUPPLY_WEB_OPERATOR_PASSWORD']
    report = {'scope': 'V3 actual HTTPS gateway, published Dify and existing cloud SQLite',
              'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'origin': origin,
              'passed': False, 'steps': [], 'turns': []}
    output = Path(__file__).parent / 'results/web_cloud_acceptance.json'
    try:
        with httpx.Client(base_url=origin, timeout=180, headers={'Origin': origin}) as client:
            boot = client.get('/web/bootstrap')
            boot.raise_for_status()
            assert boot.json()['chat_available']
            assert 'Secure' in boot.headers['set-cookie'] and 'HttpOnly' in boot.headers['set-cookie']
            assert client.get('/').status_code == 200
            assert client.get('/tickets').status_code == 200
            assert client.get('/operator').status_code == 200
            report['steps'].append('HTTPS frontend routes and secure anonymous session')
            cid = None

            def chat(query):
                nonlocal cid
                start = time.perf_counter()
                answer = ''
                finished = False
                with client.stream('POST', '/web/chat', json={'query': query, 'conversation_id': cid}) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line.startswith('data: '):
                            continue
                        event = json.loads(line[6:])
                        if event['type'] == 'conversation':
                            cid = event['conversation_id']
                        elif event['type'] == 'delta':
                            answer += event['text']
                        elif event['type'] == 'replace':
                            answer = event['text']
                        elif event['type'] == 'error':
                            raise AssertionError(event['message'])
                        elif event['type'] == 'done':
                            finished = True
                assert finished and answer, 'Stream not completed'
                report['turns'].append({'query': query, 'answer': answer, 'seconds': round(time.perf_counter()-start, 2)})
                return client.get('/web/conversations/' + cid).json()

            state = chat('前端联调模拟验收：查询 JD2026003 的温度异常，检索 SOP 并准备工单草稿，暂时不要建单。')
            assert state.get('proposal'), 'No authoritative database-backed proposal'
            assert not state['tickets'], 'Ticket created without confirmation'
            draft = state['proposal']
            report['proposal_id'] = draft['proposal_id']
            report['steps'].append('Dify tool-generated draft linked despite external/internal user-ID difference')
            state = chat(draft['confirmation_phrase'])
            assert state['tickets'], 'Confirmation did not create a real ticket'
            ticket = state['tickets'][0]
            tid = ticket['ticket_id']
            report['ticket_id'] = tid
            report['conversation_id'] = cid
            state = chat(draft['confirmation_phrase'])
            assert len(state['tickets']) == 1 and state['tickets'][0]['ticket_id'] == tid
            assert len(state['tickets'][0]['events']) == 1
            report['steps'].append('Exact user confirmation and duplicate-confirmation idempotency')
            # Independent browser identity cannot read or reuse this conversation.
            with httpx.Client(base_url=origin, timeout=30) as other:
                other.get('/web/bootstrap').raise_for_status()
                assert other.get('/web/conversations/' + cid).status_code == 404
                assert other.get('/web/tickets/' + tid).status_code == 404
            assert client.get('/web/operator/tickets').status_code == 401
            client.post('/web/operator/login', json={'password': password}).raise_for_status()
            assert client.get('/web/operator/tickets', params={'q': tid}).json()['total'] == 1
            legacy = client.get('/web/operator/tickets/T-ed8739a03b2eb83c').json()['ticket']
            # That V2 persistence probe was closed during the previous cleanup.
            # Its original two events and subsequent closure must all survive.
            assert legacy['status'] == 'closed' and len(legacy['events']) == 4
            assert [e['to_status'] for e in legacy['events']] == ['open', 'processing', 'resolved', 'closed']
            report['legacy_ticket_preserved'] = legacy['ticket_id']
            report['steps'].append('User isolation, independent operator login and V2 ticket preserved across deployment')
            statuses = []
            for previous, status in [('open', 'processing'), ('processing', 'resolved'), ('resolved', 'closed')]:
                result = client.patch('/web/operator/tickets/' + tid,
                                      json={'expected_status': previous, 'status': status,
                                            'note': '前端云端验收模拟处理：' + status})
                result.raise_for_status()
                fresh = client.get('/web/tickets/' + tid).json()['ticket']
                assert fresh['status'] == status
                statuses.append(status)
            assert len(fresh['events']) == 4
            state = client.get('/web/conversations/' + cid).json()
            assert state['proposal'] is None and state['tickets'][0]['status'] == 'closed'
            assert len(state['messages']) == 6 and all(m['state'] == 'complete' for m in state['messages'])
            stale = client.patch('/web/operator/tickets/' + tid,
                                 json={'expected_status': 'resolved', 'status': 'processing', 'note': '验证过期状态不会覆盖最新状态'})
            assert stale.status_code == 409
            report['statuses_observed'] = statuses
            report['event_count'] = len(fresh['events'])
            client.post('/web/operator/logout').raise_for_status()
            assert client.get('/web/operator/tickets').status_code == 401
            report['steps'].append('Operator lifecycle, fresh user progress, archived events, conflict rejection and logout')
            report['passed'] = True
    except Exception as exc:
        # Reports contain only public/synthetic business data, never headers/cookies.
        report['error_type'] = type(exc).__name__
        raise
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'report': str(output), 'ticket_id': report.get('ticket_id')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
