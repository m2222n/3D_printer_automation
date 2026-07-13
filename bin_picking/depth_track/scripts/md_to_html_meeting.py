#!/usr/bin/env python3
"""미팅공유_0703.md → 자체완결 HTML (PDF 인쇄용). 표준 라이브러리만 사용.

지원 문법(이 문서에 쓰인 것만): # 제목, ## , ### / 표(| |) / > 인용구 / - 리스트 /
1. 번호리스트 / **볼드** / `코드` / --- 구분선 / 📷 그림줄(PNG data URI 임베드).
6000엔 pip/sudo 없음 → markdown 모듈 대신 직접 파싱.
"""
import base64, html, os, re, sys

MD = "/home/jtm/kaist_project/docs/미팅공유_0703.md"
OUT = "/home/jtm/kaist_project/docs/미팅공유_0703.html"
IMG_DIR = "/home/jtm/kaist_project/docs/sim2real_probe_0701"

# 컬러 이모지가 Mac 브라우저/폰트에서 □(tofu)로 깨짐 → 폰트에 확실히 있는 텍스트 기호로 치환.
# (한글·화살표·원문자·−≈ 등은 정상 렌더되므로 건드리지 않음)
EMOJI_MAP = {
    "⭐": "★",        # ⭐ → 검은 별
    "✅": "✔",        # ✅ → 체크 (U+2714, 폰트 지원 넓음)
    "⚠": "⚑",        # ⚠  → 깃발형 경고 (△!는 폰트 편차 커서 깃발 사용)
    "\U0001F534": "●",    # 🔴 → 검은 원 (CSS로 빨강)
    "\U0001F4CC": "▣",    # 📌 → 사각 강조
    "\U0001F4F7": "▣",    # 📷 → (그림줄은 FIG_RE로 별도 처리되어 실제 표시 안 됨)
    "\U0001F947": "1위",  # 🥇
    "\U0001F948": "2위",  # 🥈
    "\U0001F949": "3위",  # 🥉
    "⏸": "▹",        # ⏸ → 대기
    "️": "",         # variation selector 제거
}


def strip_emoji(text):
    for k, v in EMOJI_MAP.items():
        text = text.replace(k, v)
    return text

# 📷 그림 N — `파일.png`: 캡션  →  파일명과 캡션 추출
FIG_RE = re.compile(r"📷\s*\*\*(그림\s*\d+)\*\*\s*—\s*`([^`]+\.png)`\s*:?\s*(.*)")


def data_uri(png_name):
    path = os.path.join(IMG_DIR, os.path.basename(png_name))
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def inline(text):
    """인라인: **볼드**, `코드`. 이모지 치환 + HTML 이스케이프 후 강조 치환."""
    text = strip_emoji(text)
    text = html.escape(text)
    # 빨강 원(🔴 치환된 ●)은 색 입히기
    text = text.replace("●", '<span style="color:#dc2626">●</span>')
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    return text


def render(md_lines):
    out = []
    i = 0
    n = len(md_lines)
    while i < n:
        line = md_lines[i].rstrip("\n")
        stripped = line.strip()

        # 그림줄 (인용구 안/밖 무관하게 먼저 잡음)
        m = FIG_RE.search(line)
        if m:
            title, png, cap = m.group(1), m.group(2), m.group(3)
            uri = data_uri(png)
            out.append('<figure>')
            if uri:
                out.append(f'<img src="{uri}" alt="{html.escape(title)}">')
            else:
                out.append(f'<div class="missing">[{html.escape(png)} 없음]</div>')
            out.append(f'<figcaption><strong>{inline(title)}</strong> — {inline(cap)}</figcaption>')
            out.append('</figure>')
            i += 1
            continue

        # 구분선
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue

        # 제목
        if stripped.startswith("### "):
            out.append(f"<h3>{inline(stripped[4:])}</h3>")
            i += 1; continue
        if stripped.startswith("## "):
            out.append(f"<h2>{inline(stripped[3:])}</h2>")
            i += 1; continue
        if stripped.startswith("# "):
            out.append(f"<h1>{inline(stripped[2:])}</h1>")
            i += 1; continue

        # 표: 연속된 | 로 시작하는 줄 묶음
        if stripped.startswith("|"):
            tbl = []
            while i < n and md_lines[i].strip().startswith("|"):
                tbl.append(md_lines[i].strip())
                i += 1
            out.append(render_table(tbl))
            continue

        # 인용구: 연속 > 줄 묶음 (그림줄은 위에서 이미 처리됨)
        if stripped.startswith(">"):
            quote = []
            while i < n and md_lines[i].strip().startswith(">"):
                q = md_lines[i].strip()[1:].lstrip()
                # 인용구 안의 그림줄
                fm = FIG_RE.search(q)
                if fm:
                    i += 1
                    # 별도 figure로 뽑기 위해 큐 밖에서 처리하도록 flush
                    quote.append(("FIG", fm))
                    continue
                quote.append(("TXT", q))
                i += 1
            out.append(render_quote(quote))
            continue

        # 리스트 (- 또는 1.)
        if re.match(r"^(\-|\d+\.)\s+", stripped):
            is_ol = bool(re.match(r"^\d+\.\s+", stripped))
            items = []
            while i < n:
                s = md_lines[i].strip()
                mm = re.match(r"^(?:\-|\d+\.)\s+(.*)", s)
                if not mm:
                    break
                items.append(inline(mm.group(1)))
                i += 1
            tag = "ol" if is_ol else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) + f"</{tag}>")
            continue

        # 빈 줄
        if stripped == "":
            i += 1
            continue

        # 일반 문단
        out.append(f"<p>{inline(stripped)}</p>")
        i += 1

    return "\n".join(out)


def render_table(rows):
    # rows[1]은 구분선(---) → 스킵
    def cells(r):
        parts = [c.strip() for c in r.strip().strip("|").split("|")]
        return parts
    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]] if len(rows) > 2 else []
    h = "<tr>" + "".join(f"<th>{inline(c)}</th>" for c in header) + "</tr>"
    b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<table><thead>{h}</thead><tbody>{b}</tbody></table>'


def render_quote(items):
    parts = ['<blockquote>']
    for kind, val in items:
        if kind == "TXT":
            v = val
            if v.startswith("### "):
                parts.append(f"<h3>{inline(v[4:])}</h3>")
            elif v.startswith("- "):
                parts.append(f"<ul><li>{inline(v[2:])}</li></ul>")
            elif v == "":
                continue
            else:
                parts.append(f"<p>{inline(v)}</p>")
        else:  # FIG
            m = val
            uri = data_uri(m.group(2))
            parts.append('<figure>')
            if uri:
                parts.append(f'<img src="{uri}">')
            parts.append(f'<figcaption>{inline(m.group(1))} — {inline(m.group(3))}</figcaption></figure>')
    parts.append('</blockquote>')
    return "\n".join(parts)


CSS = """
* { box-sizing: border-box; }
body { font-family: 'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic','Apple Color Emoji','Segoe UI Emoji',sans-serif;
  line-height: 1.6; color: #1a1a1a; max-width: 900px; margin: 0 auto; padding: 32px 40px;
  font-size: 14px; }
h1 { font-size: 24px; border-bottom: 3px solid #2563eb; padding-bottom: 10px; margin-top: 8px; }
h2 { font-size: 19px; margin-top: 28px; border-bottom: 1px solid #ddd; padding-bottom: 6px; color:#1e3a8a; }
h3 { font-size: 15.5px; margin-top: 20px; color:#374151; }
p { margin: 8px 0; }
ul,ol { margin: 8px 0; padding-left: 24px; }
li { margin: 3px 0; }
code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-family:'D2Coding',Consolas,monospace;
  font-size:12.5px; color:#be185d; }
strong { color:#111; }
hr { border:none; border-top:1px solid #e5e7eb; margin:22px 0; }
blockquote { background:#f8fafc; border-left:4px solid #2563eb; margin:14px 0; padding:10px 18px;
  border-radius:0 6px 6px 0; }
blockquote h3 { margin-top:4px; color:#1e3a8a; }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:13px; }
th,td { border:1px solid #d1d5db; padding:7px 10px; text-align:left; vertical-align:top; }
th { background:#eff6ff; font-weight:600; }
tbody tr:nth-child(even){ background:#fafafa; }
figure { margin:16px 0; text-align:center; }
figure img { max-width:100%; border:1px solid #e5e7eb; border-radius:6px; }
figcaption { font-size:12px; color:#6b7280; margin-top:6px; }
.missing { color:#b91c1c; font-size:12px; padding:12px; background:#fef2f2; border-radius:6px; }
@media print { body { padding:0 12px; font-size:12px; } h2 { page-break-after:avoid; }
  figure,table { page-break-inside:avoid; } }
"""


def main():
    with open(MD, encoding="utf-8") as f:
        lines = f.readlines()
    body = render(lines)
    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KAIST 미팅 공유 (7/3)</title>
<style>{CSS}</style></head>
<body>{body}</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"OK -> {OUT}  ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()
