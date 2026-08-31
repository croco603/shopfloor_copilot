"""
app.py
------
현장 작업자가 보는 채팅 화면입니다. (Streamlit)
실행 방법: streamlit run app.py
"""

import streamlit as st
import functions as f
import agent

st.set_page_config(page_title="ShopFloor Copilot", page_icon="🏭")
st.title("🏭 ShopFloor Copilot")
st.caption("현장에서 쓰는 말로 물어보세요. 공정 데이터를 근거로 답합니다.")

# 데이터는 앱이 켜질 때 한 번만 불러와서 캐싱 (매번 다시 읽지 않도록)
@st.cache_data
def get_data():
    return f.load_data()

df = get_data()

if "messages" not in st.session_state:
    st.session_state.messages = []

# 예시 질문 버튼 (데모 시나리오 STEP1~3 그대로)
st.write("**예시 질문:**")
col1, col2, col3 = st.columns(3)
example_clicked = None
if col1.button("이번 주 불량 많았던 날?"):
    example_clicked = "이번 주에 불량 유독 많았던 날 있었어요?"
if col2.button("가스 불량 원인은?"):
    example_clicked = "가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?"
if col3.button("뭘 조정해야 해?"):
    example_clicked = "그럼 뭘 조정해야 해요?"

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("질문을 입력하세요") or example_clicked

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("데이터 확인 중..."):
            answer = agent.ask(user_input, df)
        st.write(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
