import asyncio
import json
import time
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="G2G 법률검토", page_icon="⚖️")

AUTH = Path("/tmp/nlm")
AUTH.mkdir(exist_ok=True)
STORAGE = AUTH / "storage_state.json"
MASTER = AUTH / "master_token.json"

if not STORAGE.exists():
    STORAGE.write_text(st.secrets["storage_state"], encoding="utf-8")
    MASTER.write_text(st.secrets["master_token"], encoding="utf-8")

from notebooklm import NotebookLMClient

NOTEBOOKS = {
    "국내법": "862b41b3-0740-4a27-9b48-069c9fd8acb0",
    "국제법": "45f5b51d-fe25-45d5-884a-f1fca9e726d4",
}


def 문지기():
    if st.session_state.get("통과"):
        return True
    st.title("G2G 법률검토")
    pw = st.text_input("비밀번호", type="password")
    if pw:
        if pw == st.secrets["password"]:
            st.session_state["통과"] = True
            st.rerun()
        else:
            st.error("비밀번호가 다릅니다")
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


def 결과표시(결과):
    for 레인, r in 결과.items():
        제목 = f"{레인} — {r['초']}초, 출처 {r['출처수']}건"
        with st.expander(제목, expanded=True):
            if r["오류"]:
                st.error(r["오류"])
            else:
                st.markdown(r["답변"])


if 문지기():
    st.title("G2G 법률검토")

    탭1, 탭2 = st.tabs(["질의", "계약서 검토"])

    with 탭1:
        질의 = st.text_area("질문", "법령 목록만 알려주세요", height=120)
        레인 = st.radio("대상", ["둘 다", "국내법", "국제법"], horizontal=True)
        if st.button("물어보기", type="primary"):
            대상 = NOTEBOOKS if 레인 == "둘 다" else {레인: NOTEBOOKS[레인]}
            with st.spinner("노트북LM에 묻는 중…"):
                결과 = asyncio.run(_물어보기(질의, 대상))
            st.session_state["마지막"] = {"질의": 질의, "결과": 결과}
            결과표시(결과)

    with 탭2:
        st.caption("마스킹된 계약서만 올리세요. 전처리는 사내에서 끝내고 오셔야 합니다.")
        올린파일 = st.file_uploader("계약서", type=["pdf", "txt", "docx"])
        검토질의 = st.text_area(
            "검토 질의",
            "방금 추가된 계약서를 검토하세요.",
            height=160,
        )

        if 올린파일 and st.button("검토 시작", type="primary"):
            임시 = Path("/tmp") / 올린파일.name
            임시.write_bytes(올린파일.getbuffer())

            with st.spinner("두 노트북에 올리는 중…"):
                ids = asyncio.run(_계약서올리기(임시, 올린파일.name))
            st.session_state["소스ID"] = ids
            st.success("업로드 완료")

            with st.spinner("검토 중… 1분쯤 걸립니다"):
                결과 = asyncio.run(_물어보기(검토질의, NOTEBOOKS))
            st.session_state["마지막"] = {"질의": 검토질의, "결과": 결과,
                                        "계약서": 올린파일.name}
            결과표시(결과)

        if st.session_state.get("소스ID"):
            st.divider()
            st.caption("결과를 확인한 뒤 눌러주세요. 지우면 되물을 수 없습니다.")
            if st.button("계약서 소스 삭제"):
                asyncio.run(_계약서지우기(st.session_state["소스ID"]))
                del st.session_state["소스ID"]
                st.success("삭제 완료")

    if st.session_state.get("마지막"):
        st.divider()
        기록 = dict(st.session_state["마지막"])
        기록["시각"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st.download_button(
            "결과 JSON 내려받기",
            json.dumps(기록, ensure_ascii=False, indent=2),
            file_name=f"검토결과_{time.strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )
