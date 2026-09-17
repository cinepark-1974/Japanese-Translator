"""
BLUE JEANS PICTURES — Japanese-Translator
한국어 시나리오 → 일본어 번역 (5-Stage Market Adaptation Pipeline)
Powered by Anthropic Claude API

Pipeline:
  Stage 1: Raw Translation (Sonnet) — 충실한 직역 + 캐릭터/통화/문화 매핑
  Stage 2: Format Conversion (Rule-based) — 한국 포맷 → 일본 〇柱 포맷
  Stage 3: Voice Rewrite (Opus) — 번역체 제거, 일본 시나리오 문체
  Stage 4: Dialogue Polish (Opus) — 경어 설계, 대사 현지화
  Stage 5: QA Check (Sonnet) — 포맷/경어/문화코드/스토리 검증 리포트

─────────────────────────────────────────────
CHANGELOG (최신이 위)
─────────────────────────────────────────────
v1.1.1 (2026-09-17)
  - 버그 수정: 폐기된 모델 ID로 인한 Stage 실행 404 오류 해결
    (prompt.py MODEL_POLICY 갱신 — claude-sonnet-5 / claude-opus-5)
  - 사이드바·파이프라인 안내에 실제 사용 모델 ID 표기

v1.1 (2026-09-17)
  - 로컬라이징 대조표(XLSX) 업로드 지원
    · 다중 시트 자동 인식 (주요 인물 / 조·단역 / 지명·기관 / 법조문)
    · 일본어 열 자동 매칭 (일본명·일본판·요미가나·대사 헤드(일))
    · 일본어 열이 없는 시트(영문 전용)는 자동으로 건너뜀
    · 다른 시트의 '약칭'을 교차 참조해 극중 축약 호칭도 매핑
  - loc_map(extras/places/legal/corrections)을 Stage 1·3·4 프롬프트에 강제 주입
  - Stage 5 QA에 매핑 원본 동봉 → 미적용 항목 지적
  - 신설: apply_korean_residue_fix() — 남은 한글 고유명사 강제 치환
  - 신설: apply_glossary_enforcement() — 구판 오표기 일본어 강제 치환
  - 신설: check_glossary_residue() — 한국 고유 요소 잔존 검수 리포트
  - 신설 UI: 🔎 LOCALIZATION AUDIT 섹션
  - VERSION 표기를 prompt.ENGINE_VERSION 단일 출처로 통일

v1.0
  - 5-Stage Market Adaptation Pipeline 최초 구성
"""

import streamlit as st
import anthropic
import re
import io
import csv
import json
import time
from datetime import datetime

from prompt import (
    ENGINE_VERSION,
    ENGINE_BUILD_DATE,
    STYLE_PRESETS,
    KEIGO_TONE_TAGS,
    MODEL_POLICY,
    STAGE_2_FORMAT_RULES,
    CURRENCY_RULE,
    CULTURAL_CODE_MAP,
    build_stage1_prompt,
    build_stage3_prompt,
    build_stage4_prompt,
    build_stage5_prompt,
)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title=f"Japanese-Translator v{ENGINE_VERSION} | BLUE JEANS PICTURES",
    page_icon="🎌",
    layout="wide",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&display=swap');

.stApp { background-color: #F7F7F5 !important; }

.main-header {
    text-align: center;
    padding: 2.5rem 0 1rem 0;
}
.main-header .brand-name {
    font-size: 0.85rem; color: #191970;
    letter-spacing: 0.35em; font-weight: 600; margin-bottom: 0.3rem;
}
.main-header h1 {
    font-family: 'Playfair Display', serif;
    font-size: 2.8rem; font-weight: 900; color: #191970;
    margin: 0.2rem 0 0; letter-spacing: 0.02em;
    display: inline-block; border-bottom: 4px solid #f5c842;
    padding-bottom: 0.3rem;
}
.main-header .tagline {
    font-size: 0.78rem; color: #999;
    letter-spacing: 0.3em; margin-top: 0.7rem; font-weight: 400;
}
.main-header .version-badge {
    display: inline-block; background: #191970; color: #f5c842;
    font-size: 0.7rem; padding: 0.15rem 0.6rem; border-radius: 10px;
    margin-top: 0.5rem; letter-spacing: 0.1em; font-weight: 600;
}

.section-header {
    background: #f5c842; color: #191970;
    padding: 0.5rem 1.1rem; border-radius: 6px;
    font-weight: 700; font-size: 0.95rem;
    margin: 1.5rem 0 0.8rem 0; letter-spacing: 0.03em;
}

.stage-badge {
    display: inline-block; padding: 0.3rem 0.8rem;
    border-radius: 15px; font-size: 0.8rem;
    font-weight: 700; margin: 0.3rem 0.2rem; letter-spacing: 0.02em;
}
.stage-active { background: #191970; color: #f5c842; }
.stage-done { background: #2ecc71; color: #fff; }
.stage-pending { background: #ddd; color: #999; }

.result-box {
    background: #fff; border: 1px solid #ddd; border-radius: 8px;
    padding: 1.2rem; font-family: 'Yu Gothic', 'Hiragino Sans', sans-serif;
    font-size: 0.88rem; line-height: 1.7;
    white-space: pre-wrap; max-height: 600px; overflow-y: auto;
}

.qa-box {
    background: #FFFEF5; border: 2px solid #f5c842; border-radius: 8px;
    padding: 1.2rem; font-family: 'Courier New', monospace;
    font-size: 0.85rem; line-height: 1.6;
    white-space: pre-wrap; max-height: 500px; overflow-y: auto;
}

.page-chip {
    display: inline-block; background: #191970; color: #f5c842;
    padding: 0.2rem 0.7rem; border-radius: 12px;
    font-size: 0.8rem; font-weight: 600; margin-bottom: 0.5rem;
}

.char-table {
    width: 100%; border-collapse: collapse; margin: 0.5rem 0; font-size: 0.85rem;
}
.char-table th {
    background: #191970; color: #f5c842;
    padding: 0.45rem 0.8rem; text-align: left; font-weight: 600;
}
.char-table td {
    padding: 0.4rem 0.8rem; border-bottom: 1px solid #e8e8e0;
}
.char-table tr:nth-child(even) td { background: #EEEEF6; }

.pipeline-info {
    background: #EEEEF6; border-left: 4px solid #191970;
    padding: 0.8rem 1rem; border-radius: 0 6px 6px 0;
    font-size: 0.85rem; margin: 0.5rem 0; color: #333;
}

.progress-text {
    text-align: center; color: #666; font-size: 0.85rem; padding: 0.5rem 0;
}

.footer {
    text-align: center; color: #bbb; font-size: 0.72rem;
    margin-top: 2.5rem; padding: 1rem 0;
    border-top: 1px solid #ddd; letter-spacing: 0.08em;
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div { background-color: #fff !important; border-color: #ddd !important; }
div[data-testid="stFileUploader"] { background-color: #fff !important; border-radius: 8px; }
.stExpander { background-color: #fff !important; border-color: #ddd !important; border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
MAX_CHARS_PER_PAGE = 8000
VERSION = ENGINE_VERSION  # prompt.py 단일 출처 — 버전 표기 일원화


# ═══════════════════════════════════════════════════
# ★ v1.2 — 프로젝트 세션 백업 (JSON 저장/불러오기)
# 단계 중단 시 그 시점까지의 원고·결과 전체를 JSON으로 저장하고,
# 불러오면 멈춘 지점부터 그대로 이어서 진행할 수 있게 한다.
# ═══════════════════════════════════════════════════

# 백업 대상 키 — 원고 입력 + 5단계 결과 + 로컬라이징 매핑
# (타겟 장르/지시사항은 실행 시 위젯에서 다시 읽는 구조라 제외.
#  파일 업로드 원고도 텍스트 변환 후 세션에 남지 않아 제외 — 결과는 복원됨.)
_BACKUP_KEYS = [
    # 원고 입력
    "project_title", "paste_pages",
    # 5단계 번역 결과
    "stage_1_result", "stage_2_result", "stage_3_result",
    "stage_4_result", "stage_5_result",
    # 로컬라이징 매핑 (대조표 재업로드 없이 복구)
    "saved_char_map", "saved_char_tones", "saved_loc_map", "saved_char_yomi",
]

_STAGE_KEYS = [
    "stage_1_result", "stage_2_result", "stage_3_result",
    "stage_4_result", "stage_5_result",
]


def export_session_backup() -> bytes:
    """현재 세션 상태(원고 + 단계 결과 + 매핑)를 JSON bytes로 직렬화한다."""
    session = {k: st.session_state.get(k) for k in _BACKUP_KEYS}

    # 붙여넣기 페이지(paste_page_0, paste_page_1 ...)는 동적 키라 따로 수집
    pages = {}
    page_count = st.session_state.get("paste_pages", 1) or 1
    for i in range(page_count):
        key = f"paste_page_{i}"
        if key in st.session_state:
            pages[key] = st.session_state.get(key, "")
    session["_paste_pages_data"] = pages

    done = sum(1 for k in _STAGE_KEYS if st.session_state.get(k))

    payload = {
        "_meta": {
            "engine": "Japanese-Translator",
            "engine_version": ENGINE_VERSION,
            "build_date": ENGINE_BUILD_DATE,
            "saved_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "title": st.session_state.get("project_title", "") or "Untitled",
            "stage_progress": f"{done}/5",
        },
        "session": session,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def import_session_backup(raw_bytes: bytes) -> dict:
    """백업 JSON bytes를 받아 세션에 복원한다. 복원된 메타 정보 dict를 반환한다."""
    raw = raw_bytes.decode("utf-8")
    data = json.loads(raw)

    session_data = data.get("session", {})
    meta = data.get("_meta", {})

    for k in _BACKUP_KEYS:
        if k in session_data:
            st.session_state[k] = session_data[k]

    pages = session_data.get("_paste_pages_data", {})
    if isinstance(pages, dict):
        for key, val in pages.items():
            st.session_state[key] = val

    return meta


def make_backup_filename(title: str, done_count: int) -> str:
    """백업 파일명 생성 — 제목/진행도/시각 포함."""
    base = (title or "Untitled").strip()[:30]
    for ch in '<>:"/\\|?*':
        base = base.replace(ch, "_")
    base = base.replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"JPTranslator_{base}_{done_count}of5_{ts}.json"


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

# ═══════════════════════════════════════════════════
# ★ v1.1 — LOCALIZATION WORKBOOK (XLSX 대조표)
# 한·영·일 대조표에서 '일본어 열'만 골라 매핑을 만든다.
# ═══════════════════════════════════════════════════

# ── 시트 분류 키워드 (시트명에 포함되면 해당 분류) ──
_SHEET_EXTRAS_KEYS = ["단역", "조역", "조연", "端役", "extra", "minor", "bit"]
_SHEET_LEGAL_KEYS = ["법조문", "법령", "법률", "조문", "직급", "법전", "legal"]
_SHEET_PLACES_KEYS = ["지명", "기관", "장소", "용어", "명칭", "고유명사",
                      "place", "location", "term"]

# ── 헤더 컬럼 인식 키워드 ──
_COL_KO_KEYS = ["한국명", "한국이름", "한국판", "한국어", "원문", "국문", "korean"]
_COL_JP_KEYS = ["일본명", "일본판", "일본어", "일문", "japanese", "日本"]
# 일본어 열로 오인하면 안 되는 헤더 (역할·비고·요미가나 등)
_COL_JP_EXCLUDE = ["영문", "english", "요미가나", "로마자", "비고", "대응", "정확도",
                   "역할", "role", "맥락", "의도", "성별", "출처", "헤드", "연령"]
_COL_YOMI_KEYS = ["요미가나", "よみ", "読み", "yomi", "가나"]
_COL_CUE_KEYS = ["대사 헤드", "대사헤드", "cue"]      # 대사 헤드(일) — 극중 호칭 표기
_COL_SHORT_KEYS = ["약칭", "short"]                   # 극중 축약 호칭 (석훈, 도현 …)
_COL_TONE_KEYS = ["경어", "톤", "tone", "keigo"]
_COL_WRONG_KEYS = ["v1", "수정 전", "수정전", "오표기", "before", "직역 상태"]


def _norm_header(v) -> str:
    return str(v or "").strip().lower().replace(" ", "")


def _pick_column(headers: list, keys: list, exclude_keys: list = None) -> int:
    """헤더 리스트에서 키워드에 맞는 컬럼 인덱스를 찾는다. 없으면 -1."""
    exclude_keys = exclude_keys or []
    best = -1
    best_score = -1
    for idx, h in enumerate(headers):
        hn = _norm_header(h)
        if not hn:
            continue
        if any(_norm_header(x) in hn for x in exclude_keys):
            continue
        for k in keys:
            if _norm_header(k) in hn:
                # '확정' / 'v3' 가 붙은 열을 우선한다
                score = 1
                if "확정" in hn:
                    score += 2
                if "v3" in hn:
                    score += 1
                if score > best_score:
                    best_score = score
                    best = idx
    return best


def _clean_term(v, strip_kr_note: bool = False) -> str:
    """셀 값을 문자열로 정리한다.

    strip_kr_note=True 이면 일본어 값 뒤에 붙은 '한글만 들어있는 괄호 주석'을 제거한다.
    예) "国税調査官（국세전문관 채용）" → "国税調査官"
        "国税調査官（国税専門官採用）" → 그대로 유지 (일본어 주석은 남긴다)
    """
    if v is None:
        return ""
    t = str(v).strip()
    if t in {"—", "-", "–", "N/A", "n/a", "없음", "변경 없음", "None"}:
        return ""
    if strip_kr_note:
        # 괄호 안이 한글을 포함하고 일본어(히라가나·가타카나·한자)를 포함하지 않을 때만 제거
        t = re.sub(
            r"\s*[（(](?=[^）)]*[가-힣])(?![^）)]*[ぁ-んァ-ヶ一-龥])[^）)]*[）)]",
            "",
            t,
        ).strip()
        # 설명용 대시 뒤 한글 주석 제거: "相続税法第41条（物納）— 물납재산 순위에 …"
        t = re.sub(r"\s*[—–]\s*[^—–]*[가-힣][^—–]*$", "", t).strip()
    return t


def _has_hangul(s: str) -> bool:
    return bool(re.search(r"[가-힣]", str(s or "")))


def _split_variants(text: str) -> list:
    """'A / B' 같은 셀을 개별 표기로 분해한다."""
    if not text:
        return []
    out = []
    for chunk in re.split(r"\s*[/／]\s*", str(text)):
        chunk = chunk.strip(" .·\t")
        if chunk and chunk not in out:
            out.append(chunk)
    return out


def _flexible_pattern(term: str) -> "re.Pattern":
    """표기 차이를 흡수하는 검색 패턴을 만든다. (v1.1)

    번역 결과물은 괄호( () vs （） ), 중점( · vs ・ ), 대시, 줄바꿈 공백이
    대조표와 다르게 나오는 경우가 많다. 그 차이로 치환이 누락되지 않도록
    해당 문자들을 유연하게 매칭한다.
    """
    esc = re.escape(str(term))
    esc = re.sub(r"\\?[（(]", "[（(]", esc)
    esc = re.sub(r"\\?[）)]", "[）)]", esc)
    esc = re.sub(r"\\?[・·]", "[・·]", esc)
    esc = re.sub(r"\\?[-–—−]", "[-–—−]", esc)
    esc = re.sub(r"(?:\\\s|\s)+", r"\\s*", esc)
    return re.compile(esc)


def _is_safe_correction(bad: str, good: str) -> bool:
    """기계 치환해도 안전한 교정쌍인지 판정한다."""
    if not bad or not good:
        return False
    b, g = str(bad).strip(), str(good).strip()
    if b == g:
        return False
    if b in g:            # 재귀 치환 방지
        return False
    if len(b) < 2:
        return False
    return True


def parse_translation_workbook(uploaded_file):
    """XLSX 로컬라이징 대조표를 파싱한다. (v1.1)

    반환: (char_map, char_tones, loc_map, char_yomi)
      char_map  : {한국명: 일본명}            — 주요 등장인물 (+약칭 → 대사 헤드)
      char_tones: {일본명: keigo tag}          — 경어 태그 열이 있을 때
      loc_map   : {
            "extras":      {한국명: 일본명},
            "places":      {한국어 원문: 확정 일본어},
            "legal":       {한국 법조문: 일본 법조문},
            "corrections": {구판 오표기 일본어: 확정 일본어},
        }
      char_yomi : {일본명: 요미가나}           — UI 표시용

    시트명·헤더명을 키워드로 자동 인식한다.
    일본어 열이 없는 시트(영문 전용)는 건너뛴다.
    """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl이 설치되어 있지 않습니다. requirements.txt를 확인하세요.")

    data = uploaded_file.read()
    uploaded_file.seek(0)
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)

    char_map, char_tones, char_yomi = {}, {}, {}
    loc_map = {"extras": {}, "places": {}, "legal": {}, "corrections": {}}

    # ── 사전 스캔: 어느 시트에 있든 '한국명 → 약칭'을 모아둔다 ──
    # (한·영·일 시트에는 약칭 열이 없고, 영문 시트에만 있는 경우가 많다)
    short_index = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for row in rows[:6]:
            cand = list(row)
            ko_i = _pick_column(cand, _COL_KO_KEYS)
            sh_i = _pick_column(cand, _COL_SHORT_KEYS)
            if ko_i >= 0 and sh_i >= 0:
                start = rows.index(row) + 1
                for r in rows[start:]:
                    if not r or len(r) <= max(ko_i, sh_i):
                        continue
                    ko = _clean_term(r[ko_i])
                    sh = _clean_term(r[sh_i])
                    if ko and sh and ko != sh:
                        short_index.setdefault(ko, sh)
                break

    # ── 본 스캔 ──
    for ws in wb.worksheets:
        sheet_name = str(ws.title).lower()

        if any(k in sheet_name for k in _SHEET_EXTRAS_KEYS):
            bucket = "extras"
        elif any(k in sheet_name for k in _SHEET_LEGAL_KEYS):
            bucket = "legal"
        elif any(k in sheet_name for k in _SHEET_PLACES_KEYS):
            bucket = "places"
        else:
            bucket = "characters"

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        # 헤더 행 탐색 (앞 6행 안에서 한국어 열과 일본어 열이 모두 잡히는 행)
        header_idx, headers = -1, []
        for i, row in enumerate(rows[:6]):
            cand = list(row)
            ko_i = _pick_column(cand, _COL_KO_KEYS)
            jp_i = _pick_column(cand, _COL_JP_KEYS, exclude_keys=_COL_JP_EXCLUDE)
            if ko_i >= 0 and jp_i >= 0:
                header_idx, headers = i, cand
                break
        if header_idx < 0:
            # 일본어 열이 없는 시트(영문 전용 등)는 건너뛴다
            continue

        ko_i = _pick_column(headers, _COL_KO_KEYS)
        jp_i = _pick_column(headers, _COL_JP_KEYS, exclude_keys=_COL_JP_EXCLUDE)
        tone_i = _pick_column(headers, _COL_TONE_KEYS)
        yomi_i = _pick_column(headers, _COL_YOMI_KEYS)
        cue_i = _pick_column(headers, _COL_CUE_KEYS)
        short_i = _pick_column(headers, _COL_SHORT_KEYS)

        # 구판 오표기 열: '일본판 (수정 전)' 처럼 '일본'과 함께 있을 때만 인정
        wrong_i = -1
        for idx, h in enumerate(headers):
            hn = _norm_header(h)
            if not hn or idx == jp_i:
                continue
            if any(_norm_header(k) in hn for k in _COL_WRONG_KEYS) and \
               ("일본" in hn or "japanese" in hn):
                wrong_i = idx
                break

        for row in rows[header_idx + 1:]:
            if not row or len(row) <= max(ko_i, jp_i):
                continue
            ko = _clean_term(row[ko_i])
            jp = _clean_term(row[jp_i], strip_kr_note=True)
            if not ko or not jp:
                continue

            if bucket == "characters":
                char_map[ko] = jp

                if yomi_i >= 0 and len(row) > yomi_i:
                    yomi = _clean_term(row[yomi_i])
                    if yomi:
                        char_yomi[jp] = yomi

                # 약칭(석훈) → 대사 헤드(神崎) 도 매핑에 포함한다.
                # 원고 본문·대사 헤드에는 약칭이 훨씬 자주 등장한다.
                cue = _clean_term(row[cue_i], strip_kr_note=True) if (cue_i >= 0 and len(row) > cue_i) else ""
                short = _clean_term(row[short_i]) if (short_i >= 0 and len(row) > short_i) else ""
                if not short:
                    short = short_index.get(ko, "")
                if short and short not in char_map:
                    char_map[short] = cue or jp

                if tone_i >= 0 and len(row) > tone_i:
                    tone = _clean_term(row[tone_i]).lower()
                    if tone in KEIGO_TONE_TAGS:
                        char_tones[jp] = tone
            else:
                loc_map[bucket][ko] = jp

            # 구판 오표기 → 확정 일본어 (교정 매핑)
            if wrong_i >= 0 and len(row) > wrong_i:
                wrong_raw = _clean_term(row[wrong_i])
                for variant in _split_variants(wrong_raw):
                    if _is_safe_correction(variant, jp):
                        loc_map["corrections"][variant] = jp

    return char_map, char_tones, loc_map, char_yomi


def count_loc_entries(loc_map: dict) -> int:
    """loc_map 총 항목 수."""
    if not loc_map:
        return 0
    return sum(len(v or {}) for v in loc_map.values())


def _build_ko_jp_pairs(char_map: dict, loc_map: dict) -> list:
    """한글 → 일본어 기계 치환에 쓸 안전한 쌍 목록을 만든다. (v1.1)

    - 키에 한글이 있어야 한다 (일본어 원고에 한글은 남으면 안 되므로 안전)
    - 값에 한글이 있으면 제외 (한글을 새로 심는 사고 방지)
    - 법조문(legal)은 값이 설명형 장문이라 기계 치환에서 제외한다
    - 'A / B' 형태는 좌우 개수가 맞을 때만 1:1로 분해한다
    """
    pairs = []
    seen = set()

    def add(ko, jp):
        ko, jp = str(ko).strip(), str(jp).strip()
        if len(ko) < 2 or not _has_hangul(ko) or _has_hangul(jp) or not jp:
            return
        if ko in seen:
            return
        seen.add(ko)
        pairs.append((ko, jp))

    sources = [char_map or {}]
    if loc_map:
        sources.append(loc_map.get("extras") or {})
        sources.append(loc_map.get("places") or {})

    for mapping in sources:
        for ko, jp in mapping.items():
            add(ko, jp)
            ko_parts = _split_variants(ko)
            jp_parts = _split_variants(jp)
            if len(ko_parts) > 1 and len(ko_parts) == len(jp_parts):
                for k, j in zip(ko_parts, jp_parts):
                    add(k, j)

    # 긴 표기부터 치환해야 부분 일치 사고가 없다 (서울지방국세청 > 서울)
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def apply_korean_residue_fix(text: str, char_map: dict, loc_map: dict) -> tuple:
    """번역 결과에 남은 한글 고유명사를 확정 일본어 표기로 강제 치환한다. (v1.1)

    일본어 원고에 한글이 남아 있으면 그 자체가 결함이므로,
    대조표에 있는 항목에 한해 기계적으로 치환해도 안전하다.

    반환: (치환된 텍스트, [(한국어, 일본어, 횟수), ...])
    """
    if not text:
        return text, []

    pairs = _build_ko_jp_pairs(char_map, loc_map)
    if not pairs:
        return text, []

    log = []
    placeholders = {}

    for i, (ko, jp) in enumerate(pairs):
        pattern = _flexible_pattern(ko)
        found = len(pattern.findall(text))
        if found:
            token = f"\x00BJP{i}\x00"
            text = pattern.sub(token, text)
            placeholders[token] = jp
            log.append((ko, jp, found))

    for token, jp in placeholders.items():
        text = text.replace(token, jp)

    return text, log


def apply_glossary_enforcement(text: str, loc_map: dict) -> tuple:
    """구판 오표기 일본어를 확정 표기로 강제 치환한다. (v1.1)

    반환: (치환된 텍스트, [(오표기, 확정, 횟수), ...])
    """
    if not text or not loc_map:
        return text, []

    corrections = loc_map.get("corrections") or {}
    if not corrections:
        return text, []

    log = []
    placeholders = {}

    for i, bad in enumerate(sorted(corrections.keys(), key=len, reverse=True)):
        good = corrections[bad]
        pattern = _flexible_pattern(bad)
        found = len(pattern.findall(text))
        if found:
            token = f"\x00BJC{i}\x00"
            text = pattern.sub(token, text)
            placeholders[token] = good
            log.append((bad, good, found))

    for token, good in placeholders.items():
        text = text.replace(token, good)

    return text, log


# 한국 고유 요소 잔존 탐지 패턴 (일본어 원고 기준)
_RESIDUE_PATTERNS = [
    (r"[가-힣]{2,}", "한글 원문 잔존"),
    (r"(?:ソウル|セジョン|ノウォン|カンナム|チョンノ|イテウォン|ハンガン|"
     r"コエックス|プサン|インチョン|テグ|クァンジュ)", "카타카나 한국 지명"),
    (r"(?:キム|パク|チョン|チェ|カン|ハン|ユン|シン|クォン|ミョン|ソン|ペ)"
     r"[・･\s]?[ァ-ヶー]{2,}", "카타카나 한국식 인명 의심"),
    (r"(?:オッパ|ヒョン|ヌナ|オンニ|アジョシ|アジュンマ|ソンベ)", "한국식 호칭 미변환"),
    (r"(?:ウォン|₩)", "원화 표기"),
    (r"\b(?:Seoul|Sejong|Nowon|Gangnam|Jongno|Itaewon|Hangang)\b", "로마자 한국 지명"),
    (r"(?:相続税及び贈与税法|国税基本法|租税犯処罰法|特定経済犯罪加重処罰法|"
     r"公務員行動綱領)", "한국 법령명 직역"),
    (r"(?:고합|コハプ|コ・ハプ)", "한국식 사건번호"),
    (r"[89]\s*級(?!数)", "한국식 공무원 급수"),
    (r"(?:キムチ|ソジュ|マッコリ|サムギョプサル|チゲ|ラミョン)", "미현지화 문화어"),
]


def check_glossary_residue(text: str, char_map: dict, loc_map: dict) -> dict:
    """번역 결과에 한국 고유 요소·미적용 매핑이 남아있는지 검수한다. (v1.1)

    반환: {
        "unapplied": [(한국어, 목표 일본어, 분류)],   # 한국어 원문이 그대로 남은 항목
        "missing":   [(한국어, 목표 일본어, 분류)],   # 목표 일본어가 한 번도 안 나온 항목
        "residue":   [(라벨, 샘플[:8], 총 건수)],     # 패턴 기반 잔존
        "corrections_left": [(오표기, 확정, 건수)],
    }
    """
    result = {"unapplied": [], "missing": [], "residue": [], "corrections_left": []}
    if not text:
        return result

    buckets = [("주요 인물", char_map or {})]
    if loc_map:
        buckets.append(("조·단역", loc_map.get("extras") or {}))
        buckets.append(("지명·기관·용어", loc_map.get("places") or {}))
        buckets.append(("법조문·직급", loc_map.get("legal") or {}))

    for label, mapping in buckets:
        for ko, jp in mapping.items():
            if ko and ko in text:
                result["unapplied"].append((ko, jp, label))
            # 목표 일본어가 전혀 등장하지 않으면 미반영 의심
            head = re.split(r"\s*[/／]\s*", str(jp))[0].strip()
            head = re.split(r"[（(]", head)[0].strip()
            if label != "법조문·직급" and head and len(head) >= 2 and head not in text:
                result["missing"].append((ko, jp, label))

    for pattern, label in _RESIDUE_PATTERNS:
        hits = re.findall(pattern, text)
        if hits:
            uniq = []
            for h in hits:
                h = str(h).strip()
                if h and h not in uniq:
                    uniq.append(h)
            result["residue"].append((label, uniq[:8], len(hits)))

    corrections = (loc_map or {}).get("corrections") or {}
    for bad, good in corrections.items():
        n = len(_flexible_pattern(bad).findall(text))
        if n:
            result["corrections_left"].append((bad, good, n))

    return result

# ── END LOCALIZATION HELPERS ──


def parse_character_map(uploaded_file) -> tuple:
    """Parse character name mapping from CSV or TXT file.
    Supports optional keigo tag and note columns:
    한국이름,일본이름,경어태그,호칭메모
    """
    name = uploaded_file.name.lower()

    # ★ v1.1 — XLSX 로컬라이징 대조표는 전용 파서로 넘긴다
    if name.endswith((".xlsx", ".xlsm")):
        cm, ct, _lm, _yomi = parse_translation_workbook(uploaded_file)
        return cm, ct

    content = uploaded_file.read().decode("utf-8", errors="replace")
    uploaded_file.seek(0)

    char_map = {}
    char_tones = {}
    skip_headers = {"한국이름", "한국명", "korean", "name", "이름"}

    if name.endswith(".csv"):
        reader = csv.reader(io.StringIO(content))
        for row in reader:
            if len(row) >= 2:
                ko = row[0].strip()
                jp = row[1].strip()
                if ko and jp and ko.lower() not in skip_headers:
                    char_map[ko] = jp
                    if len(row) >= 3:
                        tone = row[2].strip().lower()
                        if tone in KEIGO_TONE_TAGS:
                            char_tones[jp] = tone
    else:
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in ["→", "->", "=>", "=", ",", ":", "\t"]:
                if sep in line:
                    parts = line.split(sep)
                    ko = parts[0].strip()
                    jp = parts[1].strip() if len(parts) > 1 else ""
                    if ko and jp and ko.lower() not in skip_headers:
                        char_map[ko] = jp
                        if len(parts) >= 3:
                            tone = parts[2].strip().lower()
                            if tone in KEIGO_TONE_TAGS:
                                char_tones[jp] = tone
                    break

    return char_map, char_tones


def read_uploaded_file(uploaded_file) -> str:
    """Read text from uploaded .txt, .pdf, or .docx file."""
    name = uploaded_file.name.lower()

    if name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="replace")

    elif name.endswith(".pdf"):
        try:
            import pymupdf
            pdf_bytes = uploaded_file.read()
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts)
        except ImportError:
            st.error("PDF 처리를 위해 pymupdf가 필요합니다.")
            return ""

    elif name.endswith(".docx"):
        try:
            from docx import Document
            docx_bytes = io.BytesIO(uploaded_file.read())
            doc = Document(docx_bytes)
            return "\n".join([p.text for p in doc.paragraphs])
        except ImportError:
            st.error("DOCX 처리를 위해 python-docx가 필요합니다.")
            return ""

    else:
        st.error("지원하지 않는 파일 형식입니다. (.txt / .pdf / .docx)")
        return ""


def split_into_pages(text: str, max_chars: int = MAX_CHARS_PER_PAGE) -> list:
    """Split text into pages, trying to break at scene boundaries."""
    if len(text) <= max_chars:
        return [text]

    pages = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            pages.append(remaining)
            break

        chunk = remaining[:max_chars]
        # 한국어 씬 패턴 + 일본어 〇 패턴
        scene_pattern = r'\n\s*(?:S\s*#?\s*\d+|씬\s*#?\s*\d+|SCENE\s*\d+|#\s*\d+[\.\)]|INT\.|EXT\.|〇)'
        matches = list(re.finditer(scene_pattern, chunk))

        if matches:
            cut_point = matches[-1].start()
            if cut_point > max_chars * 0.3:
                pages.append(remaining[:cut_point].rstrip())
                remaining = remaining[cut_point:].lstrip("\n")
                continue

        last_break = chunk.rfind("\n\n")
        if last_break > max_chars * 0.3:
            pages.append(remaining[:last_break].rstrip())
            remaining = remaining[last_break:].lstrip("\n")
        else:
            pages.append(chunk)
            remaining = remaining[max_chars:]

    return pages


# ─────────────────────────────────────────────
# STAGE 2: FORMAT CONVERSION (Rule-based)
# ─────────────────────────────────────────────

def apply_format_conversion(text: str) -> str:
    """Apply rule-based format conversion: Korean screenplay → Japanese 横書き format."""
    result = text

    # ── Scene heading: number prefix → 〇 ──
    # Patterns: "1. INT. ..." / "1. EXT. ..." / "S#1. INT. ..." / "씬1. ..."
    result = re.sub(
        r'^(?:\d+\.?\s*|S\s*#?\s*\d+\.?\s*|씬\s*\d+\.?\s*)'
        r'(?:INT\.\s*/??\s*EXT\.\s*|EXT\.\s*/??\s*INT\.\s*|INT\.\s*|EXT\.\s*)?',
        '〇',
        result,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # ── Scene heading: dash time → parenthetical time ──
    # "〇場所 — 時間" → "〇場所（時間）"
    result = re.sub(
        r'^(〇.+?)\s*[—–\-]\s*(.+)$',
        lambda m: f"{m.group(1).rstrip()}（{m.group(2).strip()}）",
        result,
        flags=re.MULTILINE
    )

    # ── Korean time words → Japanese ──
    time_map = {
        "새벽": "夜明け", "아침": "朝", "오전": "午前", "낮": "昼",
        "오후": "午後", "저녁": "夕方", "밤": "夜", "심야": "深夜",
        "늦은 오후": "夕方", "늦은 밤": "深夜",
    }
    for ko_time, jp_time in time_map.items():
        result = result.replace(f"（{ko_time}）", f"（{jp_time}）")

    # ── Korean direction markers → Japanese ──
    marker_map = {
        r'\(N\)': '（ナレーション）',
        r'\(나레이션\)': '（ナレーション）',
        r'\(V\.O\.?\)': '（声のみ）',
        r'\(O\.S\.?\)': '（OFF）',
        r'\(소리\)': '（OFF）',
        r'\(독백\)': '（ナレーション）',
        r'\(전화\)': '（電話）',
        r'\(계속\)': '（続き）',
        r'\(회상\)': '（回想）',
        r'\(몽타주\)': '（モンタージュ）',
        r'\(타이틀\)': 'タイトル。',
        r'\(자막\)': '字幕。',
    }
    for pattern, replacement in marker_map.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # ── Transitions ──
    result = re.sub(r'CUT\s+TO\.?', 'カットバック。', result, flags=re.IGNORECASE)
    result = re.sub(r'INSERT\s*>', 'インサート＞', result, flags=re.IGNORECASE)
    result = re.sub(r'FADE\s+IN\s*:', 'フェイドイン。', result, flags=re.IGNORECASE)
    result = re.sub(r'FADE\s+OUT\.?', 'フェイドアウト。', result, flags=re.IGNORECASE)
    result = re.sub(r'SMASH\s+CUT\s*:', 'スマッシュカット。', result, flags=re.IGNORECASE)

    # ── V.O. in character cues ──
    result = re.sub(r'\(V\.O\.?\)', '（声のみ）', result)
    result = re.sub(r'\(O\.S\.?\)', '（OFF）', result)

    return result


# ─────────────────────────────────────────────
# API CALL FUNCTION
# ─────────────────────────────────────────────

def call_api(client, text: str, system_prompt: str, model_id: str,
             max_tokens: int = 8000, page_info: str = "") -> str:
    """Call Claude API with streaming to prevent timeout."""
    full_system = system_prompt
    if page_info:
        full_system += f"\n\n[Internal context: {page_info}. Do NOT include this in output.]"

    collected = []
    with client.messages.stream(
        model=model_id,
        max_tokens=max_tokens,
        system=full_system,
        messages=[{"role": "user", "content": text}]
    ) as stream:
        for text_chunk in stream.text_stream:
            collected.append(text_chunk)

    return "".join(collected)


def run_stage_on_pages(client, pages: list, system_prompt: str,
                       model_id: str, stage_name: str,
                       progress_bar, status_area) -> list:
    """Run an API-based stage on multiple pages with progress tracking."""
    results = []
    total = len(pages)

    for idx, page in enumerate(pages):
        page_num = idx + 1
        status_area.markdown(
            f'<div class="progress-text">🔄 {stage_name} — 페이지 {page_num}/{total} 처리 중... (모델: {model_id})</div>',
            unsafe_allow_html=True
        )

        try:
            result = call_api(
                client, page, system_prompt, model_id,
                page_info=f"Page {page_num} of {total}. Maintain consistency."
            )
            results.append(result)
        except anthropic.APIError as e:
            error_msg = f"❌ API 오류 ({stage_name}, 페이지 {page_num}): {e}"
            st.error(error_msg)
            st.session_state["last_error"] = error_msg
            return None
        except Exception as e:
            error_msg = f"❌ 오류 ({stage_name}, 페이지 {page_num}): {type(e).__name__}: {e}"
            st.error(error_msg)
            st.session_state["last_error"] = error_msg
            return None

        progress_bar.progress(page_num / total)

    return results


# ─────────────────────────────────────────────
# DOCX GENERATION (横書き A4)
# ─────────────────────────────────────────────

def generate_docx(text: str) -> bytes:
    """Generate formatted Japanese screenplay DOCX (横書き A4)."""
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # ── Page Setup: A4 横書き ──
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    # ── Styles ──
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Yu Gothic'
    style_normal.font.size = Pt(10.5)
    style_normal.paragraph_format.space_after = Pt(0)
    style_normal.paragraph_format.space_before = Pt(0)
    style_normal.paragraph_format.line_spacing = 1.5

    # Scene heading (柱)
    style_scene = doc.styles.add_style('Hashira', 1)
    style_scene.font.name = 'Yu Gothic'
    style_scene.font.size = Pt(10.5)
    style_scene.font.bold = True
    style_scene.paragraph_format.space_before = Pt(24)
    style_scene.paragraph_format.space_after = Pt(6)
    style_scene.paragraph_format.line_spacing = 1.5

    # Action (ト書き) — 3字下げ
    style_action = doc.styles.add_style('Togaki', 1)
    style_action.font.name = 'Yu Gothic'
    style_action.font.size = Pt(10.5)
    style_action.paragraph_format.left_indent = Cm(1.0)  # ~3字下げ
    style_action.paragraph_format.space_before = Pt(3)
    style_action.paragraph_format.space_after = Pt(0)
    style_action.paragraph_format.line_spacing = 1.5

    # Character name (人物名)
    style_char = doc.styles.add_style('Jinmei', 1)
    style_char.font.name = 'Yu Gothic'
    style_char.font.size = Pt(10.5)
    style_char.font.bold = True
    style_char.paragraph_format.space_before = Pt(6)
    style_char.paragraph_format.space_after = Pt(0)
    style_char.paragraph_format.line_spacing = 1.5

    # Dialogue (セリフ)
    style_dialog = doc.styles.add_style('Serifu', 1)
    style_dialog.font.name = 'Yu Gothic'
    style_dialog.font.size = Pt(10.5)
    style_dialog.paragraph_format.space_before = Pt(0)
    style_dialog.paragraph_format.space_after = Pt(0)
    style_dialog.paragraph_format.line_spacing = 1.5

    # Transition
    style_trans = doc.styles.add_style('Tenkan', 1)
    style_trans.font.name = 'Yu Gothic'
    style_trans.font.size = Pt(10.5)
    style_trans.paragraph_format.space_before = Pt(6)
    style_trans.paragraph_format.space_after = Pt(6)
    style_trans.paragraph_format.line_spacing = 1.5

    # ── Parse and format ──
    HASHIRA_RE = re.compile(r'^〇')
    TRANSITION_RE = re.compile(
        r'^(カットバック|インサート|フェイドイン|フェイドアウト|スマッシュカット|タイトル|字幕|モンタージュ)',
    )
    # セリフ: name「...」 or name（声のみ）「...」
    SERIFU_RE = re.compile(r'^(.+?)(?:（[^）]*）)?\s*「')

    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 柱
        if HASHIRA_RE.match(stripped):
            doc.add_paragraph(stripped, style='Hashira')
            i += 1
            continue

        # 転換
        if TRANSITION_RE.match(stripped):
            doc.add_paragraph(stripped, style='Tenkan')
            i += 1
            continue

        # セリフ (「」を含む行)
        if '「' in stripped:
            # 人物名 + セリフ が同一行
            m = SERIFU_RE.match(stripped)
            if m:
                doc.add_paragraph(stripped, style='Serifu')
                i += 1
                continue

        # ト書き (default)
        doc.add_paragraph(stripped, style='Togaki')
        i += 1

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ═══════════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════════

# ── Header ──
st.markdown(f"""
<div class="main-header">
    <div class="brand-name">B L U E &nbsp; J E A N S &nbsp; P I C T U R E S</div>
    <h1>JAPANESE-TRANSLATOR</h1>
    <div class="tagline">Y O U N G &nbsp; · &nbsp; V I N T A G E &nbsp; · &nbsp; F R E E &nbsp; · &nbsp; I N N O V A T I V E</div>
    <div class="version-badge">v{VERSION} — 5-Stage Market Adaptation Pipeline</div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── API Key ──
api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
if api_key:
    st.success("🔑 API Key 연결됨 (Secrets)")
else:
    api_key = st.text_input(
        "🔑 Anthropic API Key",
        type="password",
        help="Claude API 키를 입력하세요. (sk-ant-...)"
    )

# ═══════════════════════════════════════════════════
# SETTINGS PANEL
# ═══════════════════════════════════════════════════

st.markdown('<div class="section-header">⚙️ SETTINGS — 번역 설정</div>', unsafe_allow_html=True)

# ── Style ──
st.markdown("**장르 스타일**")
style_choice = st.selectbox(
    "장르/스타일 프리셋:",
    list(STYLE_PRESETS.keys()),
    index=0,
    label_visibility="collapsed",
)
selected_style = STYLE_PRESETS[style_choice]
st.caption(f"📌 {selected_style['desc']}")

# ── Custom Instructions ──
custom_instructions = st.text_area(
    "✏️ 추가 번역 지시사항 (선택)",
    height=80,
    placeholder="예: 특정 용어는 이렇게 번역해줘 / 경어 레벨을 이렇게 조정해줘...",
)

# ── Pipeline Info ──
st.markdown(
    '<div class="pipeline-info"><strong>5-Stage Market Adaptation Pipeline:</strong><br>'
    f'Stage 1: Raw Translation → <code>{MODEL_POLICY["stage_1"]["model"]}</code> (직역 + 캐릭터/통화/문화 매핑)<br>'
    'Stage 2: Format Conversion → 규칙 기반 (무료, 〇柱 포맷 변환)<br>'
    f'Stage 3: Voice Rewrite → <code>{MODEL_POLICY["stage_3"]["model"]}</code> (번역체 제거, 일본 시나리오 문체)<br>'
    f'Stage 4: Dialogue Polish → <code>{MODEL_POLICY["stage_4"]["model"]}</code> (경어 설계, 대사 현지화)<br>'
    f'Stage 5: QA Check → <code>{MODEL_POLICY["stage_5"]["model"]}</code> (포맷/경어/문화코드/스토리 검증)<br>'
    '<br>💡 각 단계별로 독립 실행 · 결과 저장 · 이어서 진행 가능<br>'
    '🔎 대조표를 올리면 Stage 1·3·4에 매핑이 강제 주입되고, 하단 LOCALIZATION AUDIT에서 잔존 검수가 가능합니다.</div>',
    unsafe_allow_html=True
)


# ═══════════════════════════════════════════════════
# CHARACTER MAP
# ═══════════════════════════════════════════════════

st.markdown('<div class="section-header">👤 LOCALIZATION MAP — 로컬라이징 대조표</div>', unsafe_allow_html=True)

st.info(
    "💡 **XLSX 대조표**를 올리면 주요 인물 · 조단역 · 지명/기관/고유명사 · 법조문까지 한 번에 반영됩니다. "
    "한·영·일 대조표를 그대로 올리면 일본어 열만 자동으로 읽습니다. "
    "기존 CSV/TXT 인물표도 그대로 사용할 수 있습니다."
)

char_map_file = st.file_uploader(
    "대조표 파일 업로드",
    type=["xlsx", "xlsm", "csv", "txt"],
    help="XLSX: 다중 시트 대조표 (권장) | CSV: 한국이름,일본이름,경어태그 | TXT: 한국이름 → 일본이름",
    key="char_map_upload"
)

char_map = {}
char_tones = {}
char_yomi = {}
loc_map = {"extras": {}, "places": {}, "legal": {}, "corrections": {}}

if char_map_file:
    fname = char_map_file.name.lower()
    try:
        if fname.endswith((".xlsx", ".xlsm")):
            char_map, char_tones, loc_map, char_yomi = parse_translation_workbook(char_map_file)
        else:
            char_map, char_tones = parse_character_map(char_map_file)
    except Exception as e:
        st.error(f"❌ 대조표를 읽는 중 오류가 발생했습니다: {e}")
        char_map, char_tones = {}, {}

    if char_map or count_loc_entries(loc_map):
        # 세션에 저장 (재업로드 없이 유지)
        st.session_state["saved_char_map"] = char_map
        st.session_state["saved_char_tones"] = char_tones
        st.session_state["saved_loc_map"] = loc_map
        st.session_state["saved_char_yomi"] = char_yomi

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("주요 인물", f"{len(char_map)}")
        c2.metric("조·단역", f"{len(loc_map.get('extras') or {})}")
        c3.metric("지명·기관·용어", f"{len(loc_map.get('places') or {})}")
        c4.metric("법조문·직급", f"{len(loc_map.get('legal') or {})}")

        st.success(
            f"✅ 총 {len(char_map) + count_loc_entries(loc_map)}건 로드 "
            f"· 경어 태그 {len(char_tones)}건"
        )

        with st.expander("📑 로드된 매핑 확인", expanded=False):
            tab1, tab2, tab3, tab4 = st.tabs(
                ["주요 인물", "조·단역", "지명·기관·용어", "법조문·직급"]
            )
            with tab1:
                if char_map:
                    rows = []
                    for ko, jp in char_map.items():
                        tone = char_tones.get(jp, "—")
                        tone_label = KEIGO_TONE_TAGS[tone]["label"] if tone in KEIGO_TONE_TAGS else "—"
                        yomi = char_yomi.get(jp, "")
                        rows.append(
                            f"<tr><td>{ko}</td><td>→</td><td><strong>{jp}</strong></td>"
                            f"<td>{yomi}</td><td>{tone_label}</td></tr>"
                        )
                    st.markdown(f"""
                    <table class="char-table">
                        <tr><th>한국이름</th><th></th><th>日本語名</th><th>よみ</th><th>敬語レベル</th></tr>
                        {"".join(rows)}
                    </table>
                    """, unsafe_allow_html=True)
                else:
                    st.caption("없음")
            with tab2:
                extras = loc_map.get("extras") or {}
                if extras:
                    st.table([{"한국어": k, "日本語": v} for k, v in extras.items()])
                else:
                    st.caption("없음")
            with tab3:
                places = loc_map.get("places") or {}
                if places:
                    st.table([{"한국어 원문": k, "확정 일본어": v} for k, v in places.items()])
                else:
                    st.caption("없음")
            with tab4:
                legal = loc_map.get("legal") or {}
                if legal:
                    st.caption("법조문은 프롬프트 참조용으로만 전달되며, 기계 치환 대상이 아닙니다.")
                    st.table([{"한국판 근거": k, "일본판 조문": v} for k, v in legal.items()])
                else:
                    st.caption("없음")

        if loc_map.get("corrections"):
            with st.expander(f"🛠 구판 오표기 교정 매핑 ({len(loc_map['corrections'])}건)", expanded=False):
                st.table([{"오표기": k, "확정 표기": v} for k, v in loc_map["corrections"].items()])
    else:
        st.warning(
            "⚠️ 매핑을 읽을 수 없습니다. 시트 헤더에 '한국명'(또는 '한국판 원문')과 "
            "'일본명'(또는 '일본판') 열이 있는지 확인해 주세요."
        )

# 대조표를 다시 올리지 않아도 세션 보관본을 사용한다
if not char_map and st.session_state.get("saved_char_map"):
    char_map = st.session_state.get("saved_char_map") or {}
    char_tones = st.session_state.get("saved_char_tones") or {}
    loc_map = st.session_state.get("saved_loc_map") or loc_map
    char_yomi = st.session_state.get("saved_char_yomi") or {}
    st.caption(
        f"↩️ 이전 매핑 사용 중 — 인물 {len(char_map)}건 · 기타 {count_loc_entries(loc_map)}건"
    )

# Manual keigo assignment
if char_map and not char_tones:
    with st.expander("🎭 캐릭터별 경어 태그 수동 설정 (선택)"):
        st.caption("CSV 3번째 열 없이 여기서 직접 설정할 수 있어요.")
        for ko, jp in char_map.items():
            tone = st.selectbox(
                f"{jp}",
                ["—", "keigo", "teinei", "tameguchi", "kenson", "ibar"],
                index=0,
                key=f"tone_{jp}",
            )
            if tone != "—":
                char_tones[jp] = tone

with st.expander("📋 XLSX 대조표 양식 안내", expanded=False):
    st.markdown("""
**시트 구성** — 시트명에 아래 단어가 들어가면 자동 분류됩니다.

| 시트명 예시 | 분류 | 인식 키워드 |
|---|---|---|
| 한·영·일 이름 대조 | 주요 인물 | (그 외 전부) |
| 조·단역 한영일 | 조·단역 | 단역 · 조역 · 조연 |
| 일본판 지명·기관·고유명사 | 지명·기관·용어 | 지명 · 기관 · 장소 · 용어 · 명칭 · 고유명사 |
| 일본판 법조문 | 법조문·직급 | 법조문 · 법령 · 법률 · 조문 · 직급 |

**열 구성** — 헤더 이름으로 자동 인식합니다. 순서는 상관없습니다.

| 열 | 인식 키워드 | 용도 |
|---|---|---|
| 한국명 / 한국판 원문 / 한국판 근거 | 한국명 · 한국이름 · 한국판 · 원문 | 치환 대상 |
| 일본명 (한자) / 일본판 (확정안) | 일본명 · 일본판 · 일본어 | 확정 표기 |
| 요미가나 | 요미가나 · 読み | 표시용 (프롬프트 미주입) |
| 대사 헤드(일) | 대사 헤드 · cue | 약칭과 짝지어 극중 호칭으로 매핑 |
| 약칭 | 약칭 | 다른 시트에 있어도 한국명으로 교차 참조 |
| 경어태그 | 경어 · 톤 · keigo | keigo / teinei / tameguchi / kenson / ibar |

- **영문 열만 있는 시트는 자동으로 건너뜁니다.** 한·영·일 통합 대조표를 그대로 올리면 됩니다.
- `역할 (일본판)` `비고` `대응 정확도` 처럼 표기가 아닌 열은 매핑에 쓰이지 않습니다.
- 일본어 값 뒤의 **한글 전용 괄호 주석**은 자동 제거됩니다. (일본어 괄호 주석은 유지)
""")

with st.expander("📋 CSV / TXT 인물표 예시 보기"):
    st.code("""# CSV 형식 — 4열: 한국이름, 일본이름, 경어태그, 호칭메모(선택)
한국이름,일본이름,경어태그,호칭메모
김지훈,中村智弘,teinei,松田には敬語
이수현,林美咲,teinei,智弘とは距離がある
박성태,杉山正道,ibar,タメ口+命令形
박 경위,松田警部補,tameguchi,職務的タメ口

# TXT 형식
김지훈 → 中村智弘 → teinei
박성태 → 杉山正道 → ibar""", language="text")


# ═══════════════════════════════════════════════════
# INPUT
# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
# ★ v1.2 — 프로젝트 세션 백업 (중단 시 복구용)
# ═══════════════════════════════════════════════════
with st.expander("💾 프로젝트 세션 백업 (중단 시 복구용)", expanded=False):
    st.caption(
        "현재까지의 원고와 단계별 번역 결과, 로컬라이징 대조표 매핑을 JSON으로 저장하거나 불러옵니다. "
        "번역 도중 멈추거나 다음 날 이어서 작업할 때 사용합니다. "
        "불러오면 멈춘 단계부터 그대로 이어서 진행할 수 있습니다."
    )

    col_b1, col_b2 = st.columns(2)

    # ── 저장 ──
    with col_b1:
        st.markdown("**📥 백업 저장**")
        _done = sum(1 for _k in _STAGE_KEYS if st.session_state.get(_k))
        _backup_title = st.session_state.get("project_title", "") or "Untitled"
        _backup_bytes = export_session_backup()
        _backup_fname = make_backup_filename(_backup_title, _done)
        st.download_button(
            label=f"💾 JSON 다운로드 ({_done}/5 단계)",
            data=_backup_bytes,
            file_name=_backup_fname,
            mime="application/json",
            use_container_width=True,
            key="backup_download_btn",
        )
        st.caption(f"파일명: `{_backup_fname}`")

    # ── 불러오기 ──
    with col_b2:
        st.markdown("**📤 백업 불러오기**")
        backup_file = st.file_uploader(
            "백업 JSON 파일",
            type=["json"],
            key="backup_uploader",
            label_visibility="collapsed",
        )
        load_backup_btn = st.button(
            "📂 백업 적용 (현재 작업 덮어쓰기)",
            use_container_width=True,
            disabled=(backup_file is None),
            key="backup_load_btn",
        )

        if load_backup_btn and backup_file is not None:
            try:
                meta = import_session_backup(backup_file.read())

                saved_ver = meta.get("engine_version", "?")
                saved_at = meta.get("saved_at", "?")
                progress = meta.get("stage_progress", "?")
                title = meta.get("title", "(무제)")

                if saved_ver != ENGINE_VERSION:
                    st.warning(
                        f"⚠️ 백업 버전({saved_ver})이 현재 엔진({ENGINE_VERSION})과 다릅니다. "
                        "복원은 시도되었으나 일부 신규 기능은 반영되지 않을 수 있습니다."
                    )

                st.success(
                    f"✅ 백업 복원 완료\n\n"
                    f"**프로젝트**: {title}\n\n"
                    f"**저장 시각**: {saved_at}\n\n"
                    f"**엔진 버전**: {saved_ver}\n\n"
                    f"**진행도**: {progress} 단계"
                )
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"JSON 파싱 실패: {e}")
            except Exception as e:
                st.error(f"복원 중 오류: {e}")


st.markdown('<div class="section-header">📥 INPUT — 시나리오 입력 (한국어)</div>', unsafe_allow_html=True)

project_title = st.text_input(
    "🎬 프로젝트 제목 (파일명에 사용됩니다)",
    value=st.session_state.get("project_title", ""),
    placeholder="예: 水姫, 물귀신, TAKEOFF...",
    help="다운로드 파일명이 Screenplay_제목_JP 형태로 생성됩니다.",
)
if project_title:
    st.session_state["project_title"] = project_title

input_method = st.radio(
    "입력 방식:",
    ["📎 파일 업로드", "📝 텍스트 붙여넣기"],
    horizontal=True,
)

source_text = ""

if input_method == "📎 파일 업로드":
    uploaded = st.file_uploader(
        "시나리오 파일을 업로드하세요",
        type=["txt", "pdf", "docx"],
        help=".txt / .pdf / .docx 파일 지원",
        key="screenplay_upload"
    )
    if uploaded:
        with st.spinner("파일 읽는 중..."):
            source_text = read_uploaded_file(uploaded)
        if source_text:
            import os
            raw_name = os.path.splitext(uploaded.name)[0]
            clean_title = re.sub(r'[\s_-]+', '_', raw_name).strip('_')
            st.session_state["project_title"] = clean_title
            st.success(f"✅ 파일 로드 완료 — {len(source_text):,}자")
            with st.expander("📄 원문 미리보기", expanded=False):
                st.text(source_text[:3000] + ("..." if len(source_text) > 3000 else ""))
else:
    if "paste_pages" not in st.session_state:
        st.session_state.paste_pages = 1

    col_add, col_remove = st.columns([1, 1])
    with col_add:
        if st.button("➕ 페이지 추가", use_container_width=True):
            st.session_state.paste_pages += 1
            st.rerun()
    with col_remove:
        if st.session_state.paste_pages > 1:
            if st.button("➖ 페이지 제거", use_container_width=True):
                st.session_state.paste_pages -= 1
                st.rerun()

    page_texts = []
    for i in range(st.session_state.paste_pages):
        st.markdown(f'<span class="page-chip">Page {i+1}</span>', unsafe_allow_html=True)
        txt = st.text_area(
            f"시나리오 텍스트 (페이지 {i+1})",
            height=250,
            key=f"paste_page_{i}",
            placeholder=f"페이지 {i+1}의 시나리오 텍스트를 붙여넣으세요...",
            label_visibility="collapsed"
        )
        page_texts.append(txt)

    source_text = "\n\n".join([t for t in page_texts if t.strip()])
    if source_text:
        st.caption(f"총 {len(source_text):,}자 입력됨")


# ═══════════════════════════════════════════════════
# STEP-BY-STEP PIPELINE
# ═══════════════════════════════════════════════════

st.markdown('<div class="section-header">🔄 PIPELINE — 단계별 실행</div>', unsafe_allow_html=True)

can_run = bool(api_key and source_text.strip())

if not api_key:
    st.warning("⬆️ API Key를 먼저 입력하세요.")
elif not source_text.strip():
    st.warning("⬆️ 시나리오 텍스트를 입력하세요.")

for key in ["stage_1_result", "stage_2_result", "stage_3_result", "stage_4_result", "stage_5_result"]:
    if key not in st.session_state:
        st.session_state[key] = None


def show_stage_result(stage_num: int, stage_name: str, result_key: str):
    result = st.session_state.get(result_key)
    if result:
        with st.expander(f"📄 Stage {stage_num} 결과 — {stage_name}", expanded=False):
            st.text(result[:5000] + ("..." if len(result) > 5000 else ""))
        st.download_button(
            f"💾 Stage {stage_num} 결과 저장 (TXT)",
            data=result.encode("utf-8"),
            file_name=f"stage_{stage_num}_{stage_name.lower().replace(' ', '_')}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"dl_stage_{stage_num}",
        )


def upload_previous_result(stage_num: int, prev_stage_name: str, result_key: str):
    prev_result = st.session_state.get(result_key)
    if prev_result:
        st.success(f"✅ 이전 단계 결과 있음 ({len(prev_result):,}자) — 자동 연결됩니다.")
        return prev_result
    else:
        st.info(f"💡 이전 단계({prev_stage_name}) 결과가 없으면 파일을 업로드하세요.")
        prev_file = st.file_uploader(
            f"Stage {stage_num - 1} 결과 파일 업로드",
            type=["txt"],
            key=f"prev_upload_{stage_num}",
        )
        if prev_file:
            text = prev_file.read().decode("utf-8", errors="replace")
            st.success(f"✅ 파일 로드 완료 — {len(text):,}자")
            return text
    return None


# ═══════════════════════════════════════════════════
# STAGE 1: Raw Translation
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown("### ① Raw Translation (Sonnet)")
st.caption("한국어 → 일본어 직역. 캐릭터명/통화/문화코드 매핑 적용.")

if can_run:
    if st.button("▶️ Stage 1 실행", key="btn_stage1", use_container_width=True):
        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = build_stage1_prompt(
            char_map=char_map,
            style_prompt=selected_style["prompt"],
            custom_instructions=custom_instructions,
            loc_map=loc_map,
        )
        model_id = MODEL_POLICY["stage_1"]["model"]
        pages = split_into_pages(source_text)

        progress_bar = st.progress(0)
        status_area = st.empty()

        results = run_stage_on_pages(
            client, pages, system_prompt, model_id,
            "Stage 1: Raw Translation", progress_bar, status_area
        )

        if results is not None:
            st.session_state["stage_1_result"] = "\n\n".join(results)
            status_area.markdown('<div class="progress-text">✅ Stage 1 완료!</div>', unsafe_allow_html=True)
            st.rerun()

show_stage_result(1, "Raw Translation", "stage_1_result")


# ═══════════════════════════════════════════════════
# STAGE 2: Format Conversion
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown("### ② Format Conversion (규칙 기반)")
st.caption("한국 씬 헤더 → 일본 〇柱 포맷. API 호출 없음 (무료).")

stage_2_input = st.session_state.get("stage_1_result")
if stage_2_input:
    if st.button("▶️ Stage 2 실행", key="btn_stage2", use_container_width=True):
        st.session_state["stage_2_result"] = apply_format_conversion(stage_2_input)
        st.rerun()
elif st.session_state.get("stage_2_result") is None:
    st.caption("⏳ Stage 1을 먼저 완료하세요.")

show_stage_result(2, "Format", "stage_2_result")


# ═══════════════════════════════════════════════════
# STAGE 3: Voice Rewrite
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown("### ③ Voice Rewrite (Opus)")
st.caption("번역체 제거, 일본 시나리오 문체로 리라이트. JP-1~JP-9 안티패턴 교정.")

stage_3_input = upload_previous_result(3, "Stage 2 Format", "stage_2_result")
if stage_3_input and api_key:
    if st.button("▶️ Stage 3 실행", key="btn_stage3", use_container_width=True):
        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = build_stage3_prompt(
            char_map=char_map,
            char_tones=char_tones,
            style_prompt=selected_style["prompt"],
            custom_instructions=custom_instructions,
            loc_map=loc_map,
        )
        model_id = MODEL_POLICY["stage_3"]["model"]
        pages = split_into_pages(stage_3_input)

        progress_bar = st.progress(0)
        status_area = st.empty()

        results = run_stage_on_pages(
            client, pages, system_prompt, model_id,
            "Stage 3: Voice Rewrite", progress_bar, status_area
        )

        if results is not None:
            st.session_state["stage_3_result"] = "\n\n".join(results)
            status_area.markdown('<div class="progress-text">✅ Stage 3 완료!</div>', unsafe_allow_html=True)
            st.rerun()
elif st.session_state.get("stage_3_result") is None:
    st.caption("⏳ Stage 2를 먼저 완료하세요.")

show_stage_result(3, "Voice Rewrite", "stage_3_result")


# ═══════════════════════════════════════════════════
# STAGE 4: Dialogue Polish
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown("### ④ Dialogue Polish (Opus)")
st.caption("경어 설계 적용, 대사 전문 폴리시. DP-1~DP-6 원칙.")

stage_4_input = upload_previous_result(4, "Stage 3 Voice Rewrite", "stage_3_result")
if stage_4_input and api_key:
    if st.button("▶️ Stage 4 실행", key="btn_stage4", use_container_width=True):
        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = build_stage4_prompt(
            char_map=char_map,
            char_tones=char_tones,
            style_prompt=selected_style["prompt"],
            custom_instructions=custom_instructions,
            loc_map=loc_map,
        )
        model_id = MODEL_POLICY["stage_4"]["model"]
        pages = split_into_pages(stage_4_input)

        progress_bar = st.progress(0)
        status_area = st.empty()

        results = run_stage_on_pages(
            client, pages, system_prompt, model_id,
            "Stage 4: Dialogue Polish", progress_bar, status_area
        )

        if results is not None:
            st.session_state["stage_4_result"] = "\n\n".join(results)
            status_area.markdown('<div class="progress-text">✅ Stage 4 완료!</div>', unsafe_allow_html=True)
            st.rerun()
elif st.session_state.get("stage_4_result") is None:
    st.caption("⏳ Stage 3를 먼저 완료하세요.")

show_stage_result(4, "Dialogue Polish", "stage_4_result")


# ═══════════════════════════════════════════════════
# STAGE 5: QA Check
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown("### ⑤ QA Check (Sonnet)")
st.caption("최종 품질 검증. 포맷/경어/문화코드/스토리 체크리스트.")

stage_5_input = upload_previous_result(5, "Stage 4 Dialogue Polish", "stage_4_result")
if stage_5_input and api_key:
    if st.button("▶️ Stage 5 실행", key="btn_stage5", use_container_width=True):
        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = build_stage5_prompt(
            char_map=char_map,
            loc_map=loc_map,
        )
        model_id = MODEL_POLICY["stage_5"]["model"]

        status_area = st.empty()
        status_area.markdown(
            '<div class="progress-text">🔍 QA 검증 중...</div>',
            unsafe_allow_html=True
        )

        try:
            qa_input = stage_5_input
            if len(qa_input) > 30000:
                qa_input = stage_5_input[:15000] + "\n\n[...中略...]\n\n" + stage_5_input[-15000:]

            qa_report = call_api(
                client, qa_input, system_prompt,
                model_id, max_tokens=4000
            )
            st.session_state["stage_5_result"] = qa_report
            status_area.markdown('<div class="progress-text">✅ Stage 5 완료!</div>', unsafe_allow_html=True)
            st.rerun()
        except Exception as e:
            st.error(f"❌ QA 오류: {e}")
elif st.session_state.get("stage_5_result") is None:
    st.caption("⏳ Stage 4를 먼저 완료하세요.")

if st.session_state.get("stage_5_result"):
    st.markdown("**🔍 QA Report**")
    st.markdown(f'<div class="qa-box">{st.session_state["stage_5_result"]}</div>', unsafe_allow_html=True)
    st.download_button(
        "💾 QA Report 저장 (TXT)",
        data=st.session_state["stage_5_result"].encode("utf-8"),
        file_name="qa_report_jp.txt",
        mime="text/plain",
        use_container_width=True,
        key="dl_qa",
    )


# ═══════════════════════════════════════════════════
# ★ v1.1 — LOCALIZATION AUDIT (대조표 잔존 검수)
# ═══════════════════════════════════════════════════
st.markdown("---")
st.markdown("### 🔎 LOCALIZATION AUDIT — 로컬라이징 검수")
st.caption("대조표가 실제로 반영됐는지 기계적으로 대조합니다. 한글·카타카나 한국명·원화 잔존을 잡아냅니다.")

_audit_source = (
    st.session_state.get("stage_4_result")
    or st.session_state.get("stage_3_result")
    or st.session_state.get("stage_2_result")
    or st.session_state.get("stage_1_result")
)

if not (char_map or count_loc_entries(loc_map)):
    st.caption("⏳ 대조표를 먼저 업로드하세요.")
elif not _audit_source:
    st.caption("⏳ 번역 결과가 있어야 검수할 수 있습니다.")
else:
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🔎 검수 실행", key="btn_audit", use_container_width=True):
            st.session_state["audit_report"] = check_glossary_residue(
                _audit_source, char_map, loc_map
            )

    with col_b:
        if st.button("🈶 한글 잔존 강제 치환", key="btn_ko_fix", use_container_width=True):
            fixed, log = apply_korean_residue_fix(_audit_source, char_map, loc_map)
            st.session_state["enforced_result"] = fixed
            st.session_state["enforce_log"] = log

    with col_c:
        if st.button("🛠 구판 오표기 치환", key="btn_enforce", use_container_width=True):
            fixed, log = apply_glossary_enforcement(_audit_source, loc_map)
            st.session_state["enforced_result"] = fixed
            st.session_state["enforce_log"] = log

    # ── 검수 리포트 ──
    report = st.session_state.get("audit_report")
    if report:
        n_unapplied = len(report["unapplied"])
        n_residue = sum(cnt for _, _, cnt in report["residue"])
        n_corr = len(report["corrections_left"])

        m1, m2, m3 = st.columns(3)
        m1.metric("한국어 원문 잔존", n_unapplied)
        m2.metric("패턴 잔존 건수", n_residue)
        m3.metric("오표기 잔존", n_corr)

        if report["unapplied"]:
            st.error("**대조표 항목이 한국어 그대로 남아 있습니다** — '한글 잔존 강제 치환'으로 정리할 수 있습니다")
            st.table([
                {"분류": g, "한국어": ko, "적용되어야 할 일본어": jp}
                for ko, jp, g in report["unapplied"][:60]
            ])

        if report["residue"]:
            st.warning("**한국 고유 요소 패턴이 검출되었습니다**")
            st.table([
                {"유형": label, "검출 예": ", ".join(samples), "건수": cnt}
                for label, samples, cnt in report["residue"]
            ])

        if report["corrections_left"]:
            st.warning("**구판 오표기가 남아 있습니다**")
            st.table([
                {"오표기": bad, "확정 표기": good, "건수": n}
                for bad, good, n in report["corrections_left"][:60]
            ])

        if report["missing"]:
            with st.expander(f"⚠️ 확정 일본어가 한 번도 등장하지 않은 항목 ({len(report['missing'])}건)", expanded=False):
                st.caption("원고에 해당 인물·장소가 아예 안 나오는 경우일 수도 있습니다. 참고용입니다.")
                st.table([
                    {"분류": g, "한국어": ko, "확정 일본어": jp}
                    for ko, jp, g in report["missing"][:80]
                ])

        if not (report["unapplied"] or report["residue"] or report["corrections_left"]):
            st.success("✅ 검출된 문제가 없습니다. 로컬라이징이 일관되게 적용되었습니다.")

    # ── 강제 치환 결과 ──
    if st.session_state.get("enforced_result"):
        log = st.session_state.get("enforce_log") or []
        if log:
            st.success(f"✅ {len(log)}종 · 총 {sum(n for _, _, n in log)}건 치환했습니다.")
            st.table([
                {"치환 전": bad, "치환 후": good, "건수": n}
                for bad, good, n in log
            ])
        else:
            st.info("치환할 항목이 없습니다.")

        st.download_button(
            "💾 치환본 저장 (TXT)",
            data=st.session_state["enforced_result"].encode("utf-8"),
            file_name="localized_enforced_jp.txt",
            mime="text/plain",
            use_container_width=True,
            key="dl_enforced",
        )
        if st.button("↪️ 치환본을 최신 결과로 반영", key="btn_apply_enforced", use_container_width=True):
            for _k in ["stage_4_result", "stage_3_result", "stage_2_result", "stage_1_result"]:
                if st.session_state.get(_k):
                    st.session_state[_k] = st.session_state["enforced_result"]
                    break
            st.session_state["enforced_result"] = None
            st.session_state["enforce_log"] = None
            st.session_state["audit_report"] = None
            st.rerun()


# ═══════════════════════════════════════════════════
# FINAL OUTPUT — DOCX
# ═══════════════════════════════════════════════════

final_result = (
    st.session_state.get("stage_4_result")
    or st.session_state.get("stage_3_result")
    or st.session_state.get("stage_2_result")
    or st.session_state.get("stage_1_result")
)

if final_result:
    st.markdown("---")
    st.markdown('<div class="section-header">📤 FINAL OUTPUT — 최종 다운로드</div>', unsafe_allow_html=True)

    title_slug = st.session_state.get("project_title", "").strip()
    if title_slug:
        title_slug = re.sub(r'[^\w\s\-]', '', title_slug).strip()
        title_slug = re.sub(r'[\s]+', '_', title_slug)
        base_filename = f"Screenplay_{title_slug}_JP"
    else:
        base_filename = "Screenplay_JP"

    if st.session_state.get("stage_4_result"):
        st.caption("✅ Stage 4 (Dialogue Polish) 결과 기준")
    elif st.session_state.get("stage_3_result"):
        st.caption("⚠️ Stage 3 (Voice Rewrite) 결과 기준 — Stage 4 미완료")
    elif st.session_state.get("stage_2_result"):
        st.caption("⚠️ Stage 2 (Format) 결과 기준 — Stage 3~4 미완료")
    else:
        st.caption("⚠️ Stage 1 (Raw Translation) 결과 기준 — 추가 폴리시 권장")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "📥 TXT 다운로드",
            data=final_result.encode("utf-8"),
            file_name=f"{base_filename}.txt",
            mime="text/plain",
            use_container_width=True,
            key="dl_final_txt",
        )

    with col2:
        try:
            docx_bytes = generate_docx(final_result)
            st.download_button(
                "📥 DOCX 다운로드 (横書き A4)",
                data=docx_bytes,
                file_name=f"{base_filename}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="dl_final_docx",
            )
        except Exception as e:
            st.error(f"DOCX 생성 오류: {e}")

    st.markdown("")
    if st.button("🗑️ 전체 초기화 (새 프로젝트)", use_container_width=True):
        for key in ["stage_1_result", "stage_2_result", "stage_3_result",
                     "stage_4_result", "stage_5_result", "last_error",
                     "audit_report", "enforced_result", "enforce_log"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

if "last_error" in st.session_state:
    st.error(st.session_state["last_error"])


# ── Footer ──
st.markdown(f"""
<div class="footer">
    BLUE JEANS PICTURES — Japanese-Translator v{VERSION} ({ENGINE_BUILD_DATE})<br>
    5-Stage Market Adaptation Pipeline · Powered by Anthropic Claude API
</div>
""", unsafe_allow_html=True)
