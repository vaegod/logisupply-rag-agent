"""Real local acceptance: gateway -> self-hosted Dify -> local tools and SQLite.

Reads only gitignored local configuration. Creates and closes one synthetic
ticket, tests isolation and idempotency, and never calls a cloud Dify app.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    private = json.loads((root / 'dify/local/selfhost/local-admin.json').read_text(encoding='utf-8'))
    origin = 'http://127.0.0.1:8020'
    password = private['operator_password']
    report = {'scope': 'actual local gateway, self-hosted Dify 1.17.1, Milvus and local SQLite',
              'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'origin': origin,
              'passed': False, 'steps': [], 'turns': []}
    output = Path(__file__).parent / 'results/local_acceptance.json'
    try:
        with httpx.Client(base_url=origin, timeout=180, headers={'Origin': origin}) as client:
            boot = client.get('/web/bootstrap')
            boot.raise_for_status()
            assert boot.json()['chat_available']
            assert boot.json()['deployment_mode'] == 'local'
            assert boot.json()['dify_console_url'] == 'http://127.0.0.1:8088'
            assert 'HttpOnly' in boot.headers['set-cookie'] and 'SameSite=strict' in boot.headers['set-cookie']
            assert client.get('/').status_code == 200
            assert client.get('/tickets').status_code == 200
            assert client.get('/operator').status_code == 200
            report['steps'].append('Local frontend routes, explicit local Dify mode and HttpOnly anonymous session')
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

            state = chat('本机API模拟验收：查询 JD2026003 的温度异常，检索 SOP 并准备工单草稿，暂时不要建单。')
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
            report['steps'].append('User isolation and independent operator authorization')
            statuses = []
            for previous, status in [('open', 'processing'), ('processing', 'resolved'), ('resolved', 'closed')]:
                result = client.patch('/web/operator/tickets/' + tid,
                                      json={'expected_status': previous, 'status': status,
                                            'note': '本机API验收模拟处理：' + status})
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
            # This request uses the real local application and persisted Milvus.
            rag = client.post('/tools/search_sop', headers={'X-API-Key': private['tool_key']},
                              json={'query': '冷链温度报警应该如何处理'}).json()
            assert rag['retrieval_method'] == 'hybrid_bm25_milvus_rrf' and not rag['degraded']
            report['retrieval'] = {k: rag[k] for k in ('retrieval_method', 'degraded', 'query')}
            report['sources'] = [x['citation'] for x in rag['results']]
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
