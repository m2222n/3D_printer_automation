#!/usr/bin/env python3
"""
제어 화면 조각 생성 -> docs/juhee/06_와이어프레임_HTML/control_pages.html

제어는 페이지가 하나다. 서브 메뉴도 화면 종류도 런타임에 데이터에서 나오므로
빌드 시점에 페이지를 여러 장 찍을 수 없다 (노드를 늘리면 탭이 늘어야 한다).
본문 = docs/juhee/06_와이어프레임_HTML/control_body.html
"""
import pathlib

BODY = pathlib.Path('docs/juhee/06_와이어프레임_HTML/control_body.html').read_text(encoding='utf-8')

out = ('<!-- 제어 화면 조각 - 직접 작성한다 (클로드 디자인 번들에서 오지 않는다).\n'
       '     페이지는 #control 하나. 서브 메뉴는 v_control_menu 로, 화면은 ui_kind 로 갈린다.\n'
       '     split_wireframe.py 가 <!--TOPNAV--> 자리에 상단 메뉴를 끼워 넣는다. -->\n\n'
       '<template data-page="control">\n'
       '<div class="wf"><!--TOPNAV-->' + BODY + '</div>\n'
       '</template>\n')

pathlib.Path('docs/juhee/06_와이어프레임_HTML/control_pages.html').write_text(out, encoding='utf-8')
print('control_pages.html  %d bytes - 페이지 1 (동적 메뉴)' % len(out))
