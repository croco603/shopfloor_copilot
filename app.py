"""
app.py
------
현장 작업자가 보는 채팅 화면입니다. (Streamlit)
실행 방법: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import functions as f
import agent

st.set_page_config(page_title="ShopFloor Copilot", page_icon="🏭")
st.title("🏭 ShopFloor Copilot")
st.caption("현장에서 쓰는 말로 물어보세요. 공정 데이터를 근거로 답합니다.")

@st.cache_data
def get_data(source=None):
    return f.load_data(source)

uploaded_file = st.sidebar.file_uploader("공정 데이터 업로드 (CSV)", type="csv")

if uploaded_file is not None:
    df_up = pd.read_csv(uploaded_file)
    missing = f.validate_columns(df_up)
    if missing:
        st.error(f"필요한 컬럼이 없습니다: {', '.join(missing[:5])}")
        st.stop()
    df = get_data(uploaded_file)
else:
    df = get_data()

@st.cache_data
def get_daily_defect_rate(data):
    temp = data.copy()
    temp["date"] = pd.to_datetime(temp["TimeStamp"]).dt.floor("D")
    daily = temp.groupby("date").agg(
        생산=("PassOrFail", "count"),
        불량=("PassOrFail", lambda x: (x == "N").sum()),
    )
    daily["불량률(%)"] = (daily["불량"] / daily["생산"] * 100).round(2)
    return daily.reset_index()

daily_rate = get_daily_defect_rate(df)

def make_defect_chart(daily):
    worst_idx = daily["불량률(%)"].idxmax()
    worst_row = daily.loc[worst_idx]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["불량률(%)"],
        mode="lines+markers",
        line=dict(color="#4A9EFF", width=2),
        marker=dict(size=6),
        name="불량률",
        hovertemplate="%{x|%m/%d}<br>불량률: %{y}%<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=[worst_row["date"]], y=[worst_row["불량률(%)"]],
        mode="markers+text",
        marker=dict(size=14, color="#FF4B4B", symbol="star"),
        text=[f"최고 {worst_row['불량률(%)']}%"],
        textposition="top center",
        name="최고 불량률",
        hovertemplate="%{x|%m/%d}<br>불량률: %{y}%<extra></extra>",
    ))

    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        xaxis_title=None,
        yaxis_title="불량률(%)",
        xaxis=dict(tickformat="%m/%d"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig

if "messages" not in st.session_state:
    st.session_state.messages = []

# 예시 질문 버튼 (데모 시나리오 STEP1~4)
st.write("**예시 질문:**")
col1, col2, col3, col4 = st.columns(4)
example_clicked = None
STEP1_QUESTION = "이번 주에 불량 유독 많았던 날 있었어요?"
if col1.button("이번 주 불량 많았던 날?"):
    example_clicked = STEP1_QUESTION
if col2.button("가스 불량 원인은?"):
    example_clicked = "가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?"
if col3.button("뭘 조정해야 해?"):
    example_clicked = "그럼 뭘 조정해야 해요?"
if col4.button("야간에 불량이 왜 많아요?"):
    # STEP4 신뢰성 시연용 질문 — 데이터로 답할 수 없는 질문임을
    # 솔직하게 인정하는 모습을 보여주기 위한 버튼입니다.
    example_clicked = "야간에 불량이 왜 더 많아요?"

# 둘째 줄 — 미성형/RG3는 검증된 조치안이 없는 조합이라, '모른다'를 정직하게
# 인정하는 모습을 STEP4(야간 질문)와는 다른 맥락(조치 제안)에서 한 번 더
# 보여줄 수 있는 버튼입니다. part_code를 문장에 직접 넣어 RG3로 확실히 유도합니다.
col5, = st.columns(1)
if col5.button("미성형은 RG3에서 어떻게 막아요?"):
    example_clicked = "미성형은 RG3에서 어떻게 막아야 해요?"

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant" and msg.get("show_chart"):
            st.plotly_chart(make_defect_chart(daily_rate), use_container_width=True)

user_input = st.chat_input("질문을 입력하세요") or example_clicked

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("데이터 확인 중..."):
            history = st.session_state.messages[:-1][-6:]
            answer = agent.ask(user_input, df, history=history)
        st.write(answer)

        is_step1 = user_input == STEP1_QUESTION
        if is_step1:
            st.plotly_chart(make_defect_chart(daily_rate), use_container_width=True)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "show_chart": is_step1}
    )