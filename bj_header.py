"""BLUE JEANS PICTURES 엔진 공통 헤더 (Writer Engine 기준).

모든 엔진이 같은 파일을 씁니다. 헤더 모양을 바꾸려면 이 파일만 고친 뒤
다른 엔진 저장소의 bj_header.py 에도 똑같이 복사합니다.

    from bj_header import render_header
    render_header("WRITER ENGINE")                       # 세 줄만
    render_header("REVISE ENGINE", note="v3.3 · ...")    # 아래에 작은 회색 한 줄
"""

from __future__ import annotations

import html

import streamlit as st

_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&display=swap');
@import url('https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@latest/Paperlogy.css');
.bjh-wrap { text-align:center; padding:1rem 0 0 0; }
.bjh-co { font-size:0.85rem; font-weight:700; color:#191970; letter-spacing:0.15em;
  font-family:'Paperlogy', 'Pretendard', sans-serif; }
.bjh-title { font-size:2.6rem; font-weight:900; color:#191970; letter-spacing:-0.02em;
  font-family:'Playfair Display', 'Paperlogy', 'Georgia', serif; position:relative; display:inline-block; }
.bjh-title::after { content:''; position:absolute; bottom:2px; left:0; width:100%; height:4px;
  background:#FFCB05; border-radius:2px; }
.bjh-sub { font-size:0.7rem; color:#8E8E99 !important; letter-spacing:0.15em; margin-top:0.5rem; margin-bottom:1.5rem; }
.bjh-note { margin:-1.1rem 0 1.2rem; line-height:1.6; }
.bjh-note div { font-size:0.72rem !important; font-weight:400 !important; color:#8E8E99 !important; letter-spacing:0.03em; margin:0 !important; }
</style>"""

_CO = "B L U E &nbsp; J E A N S &nbsp; P I C T U R E S"
_SUB = "Y O U N G &nbsp; · &nbsp; V I N T A G E &nbsp; · &nbsp; F R E E &nbsp; · &nbsp; I N N O V A T I V E"


def render_header(title: str, note: str | list[str] = "") -> None:
    """title: 엔진 이름. note: 버전·부제처럼 엔진마다 다른 정보 (한 줄 또는 여러 줄)."""
    lines = [note] if isinstance(note, str) else list(note)
    note_html = "".join(f"<div>{html.escape(x)}</div>" for x in lines if x)
    st.markdown(
        _CSS
        + '<div class="bjh-wrap">'
        + f'<div class="bjh-co">{_CO}</div>'
        + f'<div class="bjh-title">{html.escape(title)}</div>'
        + f'<div class="bjh-sub">{_SUB}</div>'
        + (f'<div class="bjh-note">{note_html}</div>' if note_html else "")
        + "</div>",
        unsafe_allow_html=True,
    )
