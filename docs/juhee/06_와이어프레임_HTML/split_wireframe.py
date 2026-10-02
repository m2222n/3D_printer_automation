#!/usr/bin/env python3
"""
클로드 디자인 번들(standalone .html) → 상단 메뉴별 페이지로 쪼갠 단일 HTML.

번들은 gzip+base64 페이로드 안에 디자인을 담고 있고, 아트보드(4a·4b·4c…)가
세로로 나열된 "디자인 문서" 형태다. 이 스크립트는 그것을 앱처럼 만든다.
  - 아트보드마다 이미 들어 있는 topnav 를 그대로 쓰고 on 위치만 옮긴다
  - 메뉴 클릭 → 해당 페이지. 안 그려진 메뉴는 자리표시자
  - 10MB 한글 TTF 등 @font-face 는 걷어낸다 (폴백 스택으로 충분)

사용:
  python3 docs/juhee/06_와이어프레임_HTML/split_wireframe.py "docs/juhee/06_와이어프레임_HTML/Factory Line Wireframes (standalone).html" \
                                       docs/juhee/06_와이어프레임_HTML/wireframe_pages.html

디자인을 다시 내보내면 아래 BOARDS 매핑만 확인하면 된다.
"""
import base64, gzip, json, re, sys, pathlib

# 상단 메뉴 → (페이지 id, 아트보드 id). 아트보드가 없으면 자리표시자.
MENU = [
    ('monitor',   '모니터링',    '4a'),
    ('control',   '제어',        None),   # ← AUTHORED 로 대체
    ('workorder', '작업 지시',   None),
    ('history',   '이력 · 품질', None),
    ('assets',    '설비 관리',   None),
]
# 메뉴에 없는 하위 상세 페이지: (페이지 id, 소속 메뉴, 아트보드, 되돌아갈 페이지, 부제)
SUBPAGES = []   # 제어 상세는 AUTHORED 로 옮겼다

# 한 아트보드를 서브탭으로 쪼갠다. 경계는 인덱스가 아니라 "그 조각 안에 있는 글자"로
# 잡는다 — 디자인을 다시 내보내 순서가 바뀌어도 조용히 어긋나지 않는다.
#   보드 id: [(페이지 id, 서브탭 이름, 시작 마커 or None=앞부분 전부), ...]
# .wf 의 topnav 와 앞쪽 wf-bar(라인 상태)는 모든 서브탭에 공통으로 붙는다.
# 직접 작성한 화면 조각. 클로드 디자인 번들이 아니라 이 파일에서 온다.
#   <template data-page="..."> 안의 마크업이 그대로 페이지가 되고,
#   <!--TOPNAV--> 자리에 상단 메뉴가 끼워진다.
AUTHORED = 'docs/juhee/06_와이어프레임_HTML/control_pages.html'

SUBTABS = {
    '4a': [
        ('monitor',          '설비 · 반송',        None),
        ('monitor-pipeline', '플레이트 파이프라인', '플레이트 파이프라인'),
    ],
}

# 아직 안 그린 메뉴의 자리표시자에 넣을 한 줄 정의 (2026-09-08 태민님)
DESC = {
    '작업 지시': '무엇을 만들지 정하는 <b>계획 단위</b>. 어떤 부품(PN)을 몇 개, 어느 플레이트로 묶어, '
                 '어떤 레시피·우선순위로 흘릴지. 플레이트 배치 생성 · 대기 랙 투입 예약 · 우선순위 변경 · 취소. '
                 '결과는 “일감이 큐에 쌓인다”이고 설비는 즉시 움직이지 않는다. '
                 '<br>↔ <b>제어</b>는 지금 이 설비를 어떻게 움직일지(즉시 물리 동작·인터록). '
                 '작업 지시 = 계획·큐(되돌릴 수 있음) / 제어 = 실행·장비(되돌릴 수 없음).',
}

# 번들을 다시 내보내기 전까지 유지할 손수정. 번들 안(7MB base64)이 아니라 여기서 고친다.
# 못 찾으면 멈춘다 — 조용히 빠지면 다음 빌드에서 수정이 사라진 걸 모른다.
PATCHES = [
    # 치수검사 → 빔피킹 대기 랙 = 작업자 반송 (2026-09-10)
    ('서포트제거 · 경화 구간', '서포트제거 · 경화 · 치수검사 구간'),
    ('<path d="M924 386 L924 290" stroke="#9FA7B2" stroke-width="1.5" fill="none"></path>'
     '<polygon points="924,290 919,299 929,299" fill="#9FA7B2"></polygon>',
     '<path d="M924 386 L924 290" stroke="#EC694A" stroke-width="1.5" stroke-dasharray="5 4" fill="none"></path>'
     '<polygon points="924,290 919,299 929,299" fill="#EC694A"></polygon>'),
    ('<div class="zz-lbl" style="left:924px"><span>ARM-B</span>',
     '<div class="zz-lbl man" style="left:924px"><span>\u270b 작업자</span>'),
]

VOID = {'br','img','input','hr','meta','link','source','col','area','base','embed','track','wbr'}


def slice_element(s, start):
    tag = re.match(r'<([a-zA-Z0-9-]+)', s[start:]).group(1)
    if tag.lower() in VOID:
        return s.index('>', start) + 1
    depth = 0
    for m in re.finditer(r'<(/?)' + tag + r'\b[^>]*?(/?)>', s[start:], re.I):
        if m.group(2) == '/':
            if m.start() == 0:
                return start + m.end()
            continue
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return start + m.end()
    raise ValueError('닫는 태그 없음: ' + tag)


def inner(s, start):
    end = slice_element(s, start)
    open_end = s.index('>', start) + 1
    close = re.search(r'</[a-zA-Z0-9-]+\s*>$', s[:end]).group(0)
    return s[open_end:end - len(close)]


def unpack(bundle_path):
    """번들에서 디자인 템플릿(HTML 문자열)을 꺼낸다."""
    lines = pathlib.Path(bundle_path).read_text(encoding='utf-8').splitlines()
    tpl = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('<script type="__bundler/template">'):
            tpl = json.loads(lines[i + 1])
            break
    if tpl is None:                       # 템플릿이 리소스로 들어간 구형 번들
        for ln in lines:
            if ln.startswith('{"') and '"compressed"' in ln:
                for v in json.loads(ln).values():
                    data = base64.b64decode(v['data'])
                    if v.get('compressed'):
                        data = gzip.decompress(data)
                    if b'<x-dc>' in data:
                        tpl = data.decode('utf-8')
                        break
    if tpl is None:
        sys.exit('디자인 템플릿을 못 찾았습니다 — 번들 형식이 바뀌었을 수 있습니다.')
    return tpl


def parse_boards(tpl):
    xdc = tpl.split('<x-dc>', 1)[1].rsplit('</x-dc>', 1)[0]
    sty = re.search(r'<style>(.*?)</style>', xdc, re.S)
    css, markup = sty.group(1), xdc[sty.end():]

    boards = {}
    for m in re.finditer(r'<div class="dv-opt" id="(\w+)">', markup):
        block = inner(markup, m.start())
        card = re.search(r'<div class="dv-card"([^>]*)>', block)
        width = re.search(r'width:\s*(\d+)px', card.group(1) or '')
        lab = re.search(r'<div class="dv-olabel">(.*?)</div>', block, re.S)
        boards[m.group(1)] = {
            'html': inner(block, card.start()).strip(),
            'width': int(width.group(1)) if width else 1200,
            'label': re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', lab.group(1))).strip() if lab else '',
        }
    return css, boards


def load_authored(path):
    """<template data-page=...> 조각과 전용 CSS 를 읽는다."""
    f = pathlib.Path(path)
    if not f.exists():
        return {}, ''
    src = f.read_text(encoding='utf-8')
    css = ''.join(re.findall(r'<style data-control-css>(.*?)</style>', src, re.S))
    frags = dict(re.findall(r'<template data-page="([\w-]+)">(.*?)</template>', src, re.S))
    return {k: v.strip() for k, v in frags.items()}, css


def wf_children(board_html):
    """.wf 의 최상위 자식들을 순서대로 돌려준다."""
    open_end = board_html.index('>', board_html.index('<div class="wf"')) + 1
    end = board_html.rindex('</div>')
    out, pos = [], open_end
    while pos < end:
        m = re.compile(r'<[a-zA-Z]').search(board_html, pos)
        if not m or m.start() >= end:
            break
        e = slice_element(board_html, m.start())
        out.append(board_html[m.start():e])
        pos = e
    return out


def split_board(board_html, tabs):
    """(공통 머리, [(페이지 id, 탭 이름, 본문 html), ...]) 로 쪼갠다."""
    kids = wf_children(board_html)
    # 공통 = topnav + 뒤이어 붙은 wf-bar 들 (라인 상태 KPI)
    n = 1
    while n < len(kids) and 'class="wf-bar"' in kids[n][:80]:
        n += 1
    head, rest = kids[:n], kids[n:]

    def text(x):
        return re.sub(r'<[^>]+>', ' ', x)

    bounds = [0]
    for _pid, _name, marker in tabs[1:]:
        hit = next((i for i, k in enumerate(rest) if marker in text(k)), None)
        if hit is None:
            sys.exit('서브탭 경계를 못 찾았습니다: %r — SUBTABS 마커를 확인하세요.' % marker)
        bounds.append(hit)
    bounds.append(len(rest))

    parts = []
    for i, (pid, name, _m) in enumerate(tabs):
        body = ''.join(rest[bounds[i]:bounds[i + 1]])
        if not body.strip():
            sys.exit('서브탭 %r 이 비었습니다 — 마커 순서를 확인하세요.' % name)
        parts.append((pid, name, body))
    return ''.join(head), parts


def subtab_bar(tabs, active_pid):
    items = ''.join(
        '<span class="ptab%s" data-goto="%s">%s</span>' % (' on' if pid == active_pid else '', pid, name)
        for pid, name, _ in tabs)
    return '<div class="ptabs">' + items + '</div>'


SHELL_CSS = """
/* ── 페이지 셸 (원본 디자인에 없던 부분) ───────────────── */
body{margin:0;background:var(--n100);display:flex;justify-content:center;padding:24px 16px 64px}
.page[hidden]{display:none!important}
.board{max-width:100%}
.topnav .navi,.ptab[data-goto]{cursor:pointer}
.subbar{display:flex;align-items:center;gap:10px;padding:8px 0 10px;
  font:400 11.5px/1.4 var(--sans);color:var(--n500)}
.backlink{font:500 11.5px var(--sans);color:var(--teal6);background:none;
  border:1px solid var(--n300);border-radius:6px;padding:4px 10px;cursor:pointer}
.backlink:hover{background:#fff}
.xlink{color:var(--teal6);text-decoration:underline;cursor:pointer}
.wf-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:8px;min-height:420px;background:var(--n25);color:var(--n500);
  font:400 12px/1.6 var(--sans);text-align:center}
.wf-empty b{font:600 14px var(--sans);color:var(--ink)}
.wf-empty span{max-width:640px}
"""

JS = """
(function () {
  var pages = [].slice.call(document.querySelectorAll('.page'));
  var byLabel = {};
  pages.forEach(function (p) {
    if (!byLabel[p.dataset.menu]) byLabel[p.dataset.menu] = p.id.replace('page-', '');
  });

  function show(id, push) {
    id = String(id || '').split('/')[0];   // '#control/서브탭' 의 뒷부분은 페이지가 아니다
    if (!document.getElementById('page-' + id)) id = pages[0].id.replace('page-', '');
    pages.forEach(function (p) { p.hidden = p.id !== 'page-' + id; });
    if (push !== false && location.hash.slice(1) !== id) location.hash = id;
    window.scrollTo(0, 0);
  }

  document.addEventListener('click', function (e) {
    var t = e.target;

    var nav = t.closest('.navi');
    if (nav) { var id = byLabel[nav.textContent.trim()]; if (id) show(id); return; }

    var go = t.closest('[data-goto]');
    if (go) { show(go.dataset.goto); return; }
  });

  window.addEventListener('hashchange', function () { show(location.hash.slice(1), false); });
  show(location.hash.slice(1) || pages[0].id.replace('page-', ''), false);
})();
"""


def build(css, boards, frags, acss):
    css = re.sub(r'@font-face\{[^}]*\}\s*', '', css)                       # 10MB 폰트 제거
    css = re.sub(r'/\* options board shell \*/.*?(?=/\* ── wireframe)', '', css, flags=re.S)
    css = re.sub(r'^\.dv-[^\n]*\n', '', css, flags=re.M) + acss
    # @font-face 를 걷어냈으므로 죽은 폰트 이름을 지우고, 윈도우·맥 양쪽에서
    # 한글이 제대로 나오도록 실제 존재하는 서체로 갈아끼운다.
    css = css.replace("'NFW','NotoKR','Apple SD Gothic Neo',system-ui,sans-serif",
                      "'Pretendard','Apple SD Gothic Neo','Malgun Gothic','Segoe UI',system-ui,sans-serif")
    css = css.replace("'JetBrains Mono','SF Mono',Menlo,monospace",
                      "'JetBrains Mono','SF Mono',Menlo,Consolas,'D2Coding',monospace")

    nav_src = re.search(r'<div class="topnav">.*?</div>\s*(?=<div|<section)',
                        boards[MENU[0][2]]['html'], re.S).group(0)

    def topnav(active):
        n = nav_src.replace('<span class="navi on">', '<span class="navi">')
        return n.replace('<span class="navi">%s</span>' % active,
                         '<span class="navi on">%s</span>' % active)

    def page(pid, menu, body, width, extra=''):
        return ('<section class="page" id="page-%s" data-menu="%s" hidden>\n'
                '  <div class="board" style="width:%dpx">%s%s</div>\n</section>'
                % (pid, menu, width, extra, body))

    pages = []
    for pid, label, bid in MENU:
        if pid in frags:
            pages.append(page(pid, label, frags[pid].replace('<!--TOPNAV-->', topnav(label)), 1320))
            print('    · %-18s %-14s %6dB  (직접 작성)' % ('#' + pid, label, len(frags[pid])))
        elif bid and bid in SUBTABS:
            tabs = SUBTABS[bid]
            head, parts = split_board(boards[bid]['html'], tabs)
            for spid, sname, body in parts:
                wf = '<div class="wf">' + head + subtab_bar(tabs, spid) + body + '</div>'
                pages.append(page(spid, label, wf, boards[bid]['width']))
                print('    └ %-18s %-14s %6dB' % ('#' + spid, sname, len(body)))
        elif bid:
            pages.append(page(pid, label, boards[bid]['html'], boards[bid]['width']))
        else:
            note = DESC.get(label, '아직 설계 전 화면입니다. 디자인이 정해지면 이 자리에 들어갑니다.')
            body = ('<div class="wf">' + topnav(label) +
                    '<div class="wf-empty"><b>' + label + '</b><span>' + note + '</span></div></div>')
            pages.append(page(pid, label, body, 1120))

    for pid, frag in frags.items():
        if any(pid == m[0] for m in MENU):
            continue
        # 조각이 자체 서브메뉴를 갖고 있으므로 '돌아가기' 바를 붙이지 않는다
        menu = next((m[1] for m in MENU if pid.startswith(m[0] + '-')), MENU[0][1])
        pages.append(page(pid, menu, frag.replace('<!--TOPNAV-->', topnav(menu)), 1320))
        print('    · %-18s %-14s %6dB  (직접 작성)' % ('#' + pid, menu, len(frag)))

    for pid, menu, bid, back, sub in SUBPAGES:
        bar = ('<div class="subbar"><button class="backlink" data-goto="%s">← 돌아가기</button>'
               '<span>%s</span></div>\n    ' % (back, sub))
        pages.append(page(pid, menu, boards[bid]['html'], boards[bid]['width'], bar))

    html = '\n'.join(pages)
    for old, new in PATCHES:
        if html.count(old) != 1:
            sys.exit('PATCHES 대상을 못 찾았습니다 (%d건): %r' % (html.count(old), old[:60]))
        html = html.replace(old, new)
    # 디자인 문서용 상호참조(#4a 등)를 페이지 이동으로 바꾼다
    for pid, _label, bid in MENU:
        if bid:
            target = SUBTABS[bid][0][0] if bid in SUBTABS else pid
            html = html.replace('<a class="dv-oid" href="#%s">%s</a>' % (bid, bid),
                                '<span class="xlink" data-goto="%s">%s</span>' % (target, _label))
    for pid, _menu, bid, _back, _sub in SUBPAGES:
        html = html.replace('<a class="dv-oid" href="#%s">%s</a>' % (bid, bid),
                            '<span class="xlink" data-goto="%s">%s</span>' % (pid, _sub))
    # '상세 제어' 버튼 → 하위 상세 페이지
    return ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>Factory Line Wireframes</title>\n<style>\n' + css.strip() + '\n'
            + SHELL_CSS + '</style>\n</head>\n<body>\n' + html
            + '\n<script>' + JS + '</script>\n</body>\n</html>\n')


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'docs/juhee/06_와이어프레임_HTML/Factory Line Wireframes (standalone).html'
    dst = sys.argv[2] if len(sys.argv) > 2 else 'docs/juhee/06_와이어프레임_HTML/wireframe_pages.html'
    css, boards = parse_boards(unpack(src))
    frags, acss = load_authored(AUTHORED)
    if frags:
        print('  직접 작성 조각: %s (%s)' % (', '.join(sorted(frags)), AUTHORED))
    used = {b for _, _, b in MENU if b} | {b for _, _, b, _, _ in SUBPAGES}
    for bid, b in boards.items():
        mark = '→ 페이지' if bid in used else '   미사용'
        print('  %-3s %6dB  %s  %s' % (bid, len(b['html']), mark, b['label'][:56]))
    out = build(css, boards, frags, acss)
    pathlib.Path(dst).write_text(out, encoding='utf-8')
    print('\n%s  %d bytes' % (dst, len(out)))
