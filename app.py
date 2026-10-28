import asyncio
import base64
import json
import time
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(
    page_title="계약 법률검토 지원 시스템",
    page_icon="◆",
    layout="centered",
)

CSS = """
<style>
#MainMenu, footer, header {visibility: hidden;}

html, body, [class*="css"] {
  font-family: -apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic',
               'Noto Sans KR', sans-serif;
}

.block-container {padding-top: 2.2rem; max-width: 50rem;}

.hdr {
  border-bottom: 2px solid rgba(128,128,128,0.45);
  padding-bottom: 1rem;
  margin-bottom: 1.8rem;
}
.hdr h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-color);
  margin: 0;
  letter-spacing: -0.02em;
  line-height: 1.3;
}
.hdr .sub {
  font-size: 0.95rem;
  color: var(--text-color);
  opacity: 0.7;
  margin-top: 0.5rem;
}

.meta {
  font-size: 0.85rem;
  color: var(--text-color);
  opacity: 0.75;
  font-variant-numeric: tabular-nums;
  padding: 0.15rem 0 0.7rem 0;
  border-bottom: 1px solid rgba(128,128,128,0.3);
  margin-bottom: 0.9rem;
}
.lane {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-color);
  margin-bottom: 0.15rem;
}
.note {
  font-size: 0.88rem;
  color: var(--text-color);
  opacity: 0.75;
  line-height: 1.7;
}
.rule {
  border-top: 1px solid rgba(128,128,128,0.3);
  margin: 1.8rem 0 1rem 0;
}

.stButton > button {
  border-radius: 2px;
  font-weight: 600;
}
.stTabs [data-baseweb="tab"] {
  font-weight: 600;
  font-size: 0.95rem;
}
div[data-testid="stExpander"] details {
  border: 1px solid rgba(128,128,128,0.3);
  border-radius: 2px;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

AUTH = Path("/tmp/nlm")
AUTH.mkdir(exist_ok=True)
STORAGE = AUTH / "storage_state.json"
MASTER = AUTH / "master_token.json"

if not STORAGE.exists():
    STORAGE.write_bytes(base64.b64decode(st.secrets["storage_state_b64"]))
    MASTER.write_bytes(base64.b64decode(st.secrets["master_token_b64"]))

from notebooklm import NotebookLMClient

NOTEBOOKS = {
    "국내법·수출통제": "862b41b3-0740-4a27-9b48-069c9fd8acb0",
    "국제법·준거법": "45f5b51d-fe25-45d5-884a-f1fca9e726d4",
}


def 머리():
    st.markdown(
        '<div class="hdr">'
        '<h1>계약 법률검토 지원 시스템</h1>'
        '<div class="sub">G2G 계약 1차 검토 · 국내법 / 국제법 병행 분석</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def 문지기():
    if st.session_state.get("통과"):
        return True
    머리()
    st.markdown(
        '<div class="note">접근 권한이 있는 담당자만 이용할 수 있습니다.</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    pw = st.text_input("접근 코드", type="password", label_visibility="collapsed",
                       placeholder="접근 코드")
    if pw:
        if pw == st.secrets["password"]:
            st.session_state["통과"] = True
            st.rerun()
        else:
            st.error("접근 코드가 일치하지 않습니다.")
    return False


async def _물어보기(질의, 대상):
    async def one(c, name, nid):
        t = time.time()
        try:
            r = await c.chat.ask(nid, 질의)
            return name, {"답변": r.answer, "출처수": len(r.references),
                          "초": round(time.time() - t, 1), "오류": None}
        except Exception as e:
            return name, {"답변": None, "출처수": 0,
                          "초": round(time.time() - t, 1),
                          "오류": f"{type(e).__name__}: {e}"}

    async with NotebookLMClient.from_storage(str(STORAGE)) as c:
        쌍 = await asyncio.gather(*[one(c, n, i) for n, i in 대상.items()])
    return dict(쌍)


async def _계약서올리기(경로, 이름):
    async def add(c, name, nid):
        s = await c.sources.add_file(nid, str(경로), wait=True,
                                     wait_timeout=300, title=이름)
        return name, s.id

    async with NotebookLMClient.from_storage(str(STORAGE)) as c:
        쌍 = await asyncio.gather(*[add(c, n, i) for n, i in NOTEBOOKS.items()])
    return dict(쌍)


async def _계약서지우기(소스ID):
    async with NotebookLMClient.from_storage(str(STORAGE)) as c:
        for name, sid in 소스ID.items():
            await c.sources.delete(NOTEBOOKS[name], sid)


def 기록저장(기록):
    url = st.secrets.get("drive_webhook")
    if not url:
        return None
    try:
        r = requests.post(
            url,
            json={"token": st.secrets["drive_token"], "record": 기록},
            timeout=60,
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def 마무리(질의, 결과, 계약서=None):
    기록 = {
        "시각": time.strftime("%Y-%m-%d %H:%M:%S"),
        "질의": 질의,
        "결과": 결과,
    }
    if 계약서:
        기록["계약서"] = 계약서

    st.session_state["마지막"] = 기록

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    총초 = max(r["초"] for r in 결과.values())
    대상목록 = " · ".join(결과.keys())
    st.markdown(
        f'<div class="meta">검토 일시 {기록["시각"]} &nbsp;|&nbsp; '
        f'대상 {대상목록} &nbsp;|&nbsp; 소요 {총초}초</div>',
        unsafe_allow_html=True,
    )

    for 레인, r in 결과.items():
        with st.container(border=True):
            st.markdown(f'<div class="lane">{레인}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="note">인용 출처 {r["출처수"]}건 · 소요 {r["초"]}초</div>',
                unsafe_allow_html=True,
            )
            st.write("")
            if r["오류"]:
                st.error(r["오류"])
            else:
                st.markdown(r["답변"])

    응답 = 기록저장(기록)
    if 응답 and 응답.get("ok"):
        st.caption(f"검토 이력 저장됨 — 누적 {응답['count']}건")
    elif 응답:
        st.caption(f"검토 이력 저장 실패 — {응답.get('error')}")


if 문지기():
    머리()

    탭1, 탭2 = st.tabs(["계약 검토", "개별 질의"])

    with 탭2:
        st.markdown(
            '<div class="note">지식베이스에 수록된 법령·규정에 관해 '
            '직접 질의합니다.</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        질의 = st.text_area("질의 내용", "법령 목록만 알려주세요", height=110)
        레인 = st.radio("검토 대상", ["전체", *NOTEBOOKS.keys()], horizontal=True)
        if st.button("질의 실행", type="primary", key="q"):
            대상 = NOTEBOOKS if 레인 == "전체" else {레인: NOTEBOOKS[레인]}
            with st.spinner("검토 중"):
                결과 = asyncio.run(_물어보기(질의, 대상))
            마무리(질의, 결과)

    with 탭1:
        st.markdown(
            '<div class="note">'
            '마스킹 처리된 계약서만 등록할 수 있습니다. '
            '조항 식별자 부여, 마스킹, 대응표 작성은 사내에서 완료한 뒤 '
            '등록하십시오.</div>',
            unsafe_allow_html=True,
        )
        st.write("")

        if st.session_state.get("소스ID"):
            st.info("검토가 진행 중인 계약서가 있습니다. "
                    "아래에서 등록 해제한 뒤 새 계약서를 등록하십시오.")
        else:
            올린파일 = st.file_uploader("계약서 파일", type=["pdf", "txt", "docx"])
            검토질의 = st.text_area(
                "검토 지시문",
                "방금 등록된 계약서를 검토하세요.",
                height=150,
            )
            if 올린파일 and st.button("검토 실행", type="primary", key="c"):
                임시 = Path("/tmp") / 올린파일.name
                임시.write_bytes(올린파일.getbuffer())

                with st.spinner("자료 등록 중"):
                    ids = asyncio.run(_계약서올리기(임시, 올린파일.name))
                st.session_state["소스ID"] = ids

                with st.spinner("검토 중 — 1분가량 소요됩니다"):
                    결과 = asyncio.run(_물어보기(검토질의, NOTEBOOKS))
                마무리(검토질의, 결과, 계약서=올린파일.name)

        if st.session_state.get("소스ID"):
            st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="note">검토 결과를 확인한 뒤 등록을 해제하십시오. '
                '해제 후에는 추가 질의를 할 수 없습니다.</div>',
                unsafe_allow_html=True,
            )
            st.write("")
            if st.button("계약서 등록 해제"):
                asyncio.run(_계약서지우기(st.session_state["소스ID"]))
                del st.session_state["소스ID"]
                st.success("등록이 해제되었습니다.")
                st.rerun()

    if st.session_state.get("마지막"):
        st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
        st.download_button(
            "검토 결과 내려받기 (JSON)",
            json.dumps(st.session_state["마지막"], ensure_ascii=False, indent=2),
            file_name=f"검토결과_{time.strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="note">'
        '본 시스템의 검토 결과는 1차 자동 분석 자료이며, 법무 검수를 대체하지 '
        '않습니다. 최종 판단은 반드시 담당 법무의 확인을 거쳐야 합니다.<br>'
        '검토 결과는 지식베이스에 수록된 법령을 기준으로 하며, '
        '법령 개정 사항이 반영되지 않았을 수 있습니다.'
        '</div>',
        unsafe_allow_html=True,
    )
