# -*- coding: utf-8 -*-
"""topology.yaml 의 transporters 를 화면이 쓸 JSON 으로. 손으로 옮겨 적지 않는다.
   (신규 API 가 생기면 v_transporter_load 가 같은 것을 준다)"""
import json, sys, yaml, pathlib

root = pathlib.Path(__file__).resolve().parents[4]
doc = yaml.safe_load((root / 'topology.yaml').read_text(encoding='utf-8'))
groups = doc.get('groups', {})
labels = {n['id']: n['label'] for n in doc['nodes']}

def resolve(ref):
    return groups[ref[1:]] if isinstance(ref, str) and ref.startswith('@') else [ref]

out = []
for t in doc['transporters']:
    ids = [i for ref in t.get('nodes', []) for i in resolve(ref)]
    out.append({
        'id': t['id'], 'kind': t['kind'], 'label': t['label'],
        'endpoint': t.get('endpoint'),            # 없으면 수동 — 명령을 보낼 수 없다
        'node_ids': ids,
        'node_labels': [labels.get(i, i) for i in ids],
        # 명령 카탈로그도 여기서 온다. 화면·빌드가 지어내지 않는다.
        'commands': (t.get('attrs') or {}).get('commands') or [],
    })
json.dump({'transporters': out}, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('반송 자원', len(out), '건 추출:',
      ' '.join(f"{t['id']}({len(t['commands'])})" for t in out))
