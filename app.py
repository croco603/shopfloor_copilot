"""
app.py
------
현장 작업자가 보는 채팅 화면입니다. (Streamlit)
실행 방법: streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import functions as f
import agent

st.set_page_config(page_title="ShopFloor Copilot", page_icon="🏭", layout="wide")
st.title("🏭 ShopFloor Copilot")
st.caption("현장에서 쓰는 말로 물어보세요. 공정 데이터를 근거로 답합니다.")

# ---------------------------------------------------------------------
# 색상 팔레트 (다크 테마 기준 검증된 데이터 시각화 팔레트에서 가져온 값)
# 파란색 = 기본 계열, 빨간색 = 강조(최고/최악), 회색 = 비강조(맥락)
# ---------------------------------------------------------------------
COLOR_BLUE = "#3987e5"
COLOR_RED = "#e66767"
COLOR_MUTED = "#898781"
COLOR_GRID = "#2c2c2a"

CHART_BASE_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=40, b=10),
)


@st.cache_data
def get_data(source=None):
    return f.load_data(source)


uploaded_file = st.sidebar.file_uploader("공정 데이터 업로드 (CSV)", type="csv", key="csv_uploader")

# ▼ 화면 전체 드래그 앤 드롭 업로드 기능 ▼
# Streamlit은 file_uploader 박스 안에만 드롭이 되므로, 화면 전체를 드롭존으로
# 넓히기 위해 JS를 주입해서 숨겨진 파일 입력창에 강제로 파일을 전달합니다.
components.html("""
<script>
const streamlitDoc = window.parent.document;
if (!streamlitDoc.body.dataset.dropZoneInstalled) {
    streamlitDoc.body.dataset.dropZoneInstalled = 'true';
    function showOverlay() {
        let overlay = streamlitDoc.getElementById('dropOverlay');
        if (!overlay) {
            overlay = streamlitDoc.createElement('div');
            overlay.id = 'dropOverlay';
            overlay.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0, 100, 255, 0.15);
                border: 4px dashed #0064ff;
                z-index: 9999; display: flex; align-items: center; justify-content: center;
                font-size: 28px; color: #0064ff; font-weight: bold; pointer-events: none;
            `;
            overlay.innerText = '📂 여기에 CSV 파일을 놓으세요';
            streamlitDoc.body.appendChild(overlay);
        }
        overlay.style.display = 'flex';
    }
    function hideOverlay() {
        const overlay = streamlitDoc.getElementById('dropOverlay');
        if (overlay) overlay.style.display = 'none';
    }
    streamlitDoc.addEventListener('dragover', (e) => {
        e.preventDefault();
        showOverlay();
    });
    streamlitDoc.addEventListener('dragleave', (e) => {
        if (e.clientX <= 0 || e.clientY <= 0) hideOverlay();
    });
    streamlitDoc.addEventListener('drop', (e) => {
        e.preventDefault();
        hideOverlay();
        const files = e.dataTransfer.files;
        if (files.length === 0) return;
        if (!files[0].name.toLowerCase().endsWith('.csv')) {
            alert('CSV 파일만 업로드할 수 있습니다.');
            return;
        }
        const fileInput = streamlitDoc.querySelector('input[type="file"]');
        if (!fileInput) {
            console.error('file_uploader 입력창을 찾을 수 없습니다.');
            return;
        }
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(files[0]);
        fileInput.files = dataTransfer.files;
        const event = new Event('change', { bubbles: true });
        fileInput.dispatchEvent(event);
    });
}
</script>
""", height=0)
# ▲ 화면 전체 드래그 앤 드롭 업로드 기능 끝 ▲

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


# ---------------------------------------------------------------------
# 대시보드 — 핵심 지표 (KPI)
# ---------------------------------------------------------------------
def render_kpi_row(data):
    total = len(data)
    n_fail = int((data["PassOrFail"] == "N").sum())
    fail_rate = round(n_fail / total * 100, 2) if total else 0.0

    reason_info = f.count_defects_by_reason(data)
    top_reason = reason_info["by_reason"][0] if reason_info["by_reason"] else None

    part_info = f.list_part_codes(data)
    top_part = part_info["parts"][0] if part_info["parts"] else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 생산량", f"{total:,}개")
    c2.metric("전체 불량률", f"{fail_rate}%", f"불량 {n_fail}건", delta_color="off")
    c3.metric("최다 불량 원인", top_reason["reason"] if top_reason else "-",
              f"{top_reason['count']}건" if top_reason else None, delta_color="off")
    c4.metric("불량률 최고 품번", top_part["part_code"] if top_part else "-",
              f"{top_part['defect_rate_pct']}%" if top_part else None, delta_color="off")


# ---------------------------------------------------------------------
# 차트 1. 일별 생산량 + 불량률 추이
# (두 지표의 단위가 달라서 한 그래프에 축 두 개로 억지로 합치지 않고,
#  같은 x축을 공유하는 그래프 두 개를 위아래로 나눠서 보여줍니다)
# ---------------------------------------------------------------------
def make_trend_fig(daily):
    worst_idx = daily["불량률(%)"].idxmax()
    worst_row = daily.loc[worst_idx]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.35, 0.65], vertical_spacing=0.08,
        subplot_titles=("일별 생산량", "일별 불량률(%)"),
    )

    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["생산"],
        marker_color=COLOR_BLUE,
        name="생산량",
        hovertemplate="%{x|%m/%d}<br>생산량: %{y}개<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["불량률(%)"],
        mode="lines+markers",
        line=dict(color=COLOR_BLUE, width=2),
        marker=dict(size=6),
        name="불량률",
        hovertemplate="%{x|%m/%d}<br>불량률: %{y}%<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=[worst_row["date"]], y=[worst_row["불량률(%)"]],
        mode="markers+text",
        marker=dict(size=14, color=COLOR_RED, symbol="star"),
        text=[f"최고 {worst_row['불량률(%)']}%"],
        textposition="top center",
        name="최고 불량률",
        hovertemplate="%{x|%m/%d}<br>불량률: %{y}%<extra></extra>",
    ), row=2, col=1)

    fig.update_layout(
        height=420,
        showlegend=False,
        hovermode="x unified",
        **CHART_BASE_LAYOUT,
    )
    fig.update_xaxes(showgrid=True, gridcolor=COLOR_GRID, tickformat="%m/%d")
    fig.update_yaxes(showgrid=True, gridcolor=COLOR_GRID, zeroline=False)
    return fig


# 기존 이름 유지 — 채팅 답변 아래에서 계속 이 이름으로 호출합니다.
def make_defect_chart(daily):
    return make_trend_fig(daily)


# ---------------------------------------------------------------------
# 차트 2. 불량 원인별 건수 (가로 막대, 최다 원인만 강조)
# ---------------------------------------------------------------------
def make_reason_fig(data):
    info = f.count_defects_by_reason(data)
    rows = info["by_reason"]
    if not rows:
        return None

    reasons = [r["reason"] for r in rows][::-1]
    counts = [r["count"] for r in rows][::-1]
    max_count = max(counts)
    colors = [COLOR_RED if c == max_count else COLOR_MUTED for c in counts]

    fig = go.Figure(go.Bar(
        x=counts, y=reasons, orientation="h",
        marker_color=colors,
        text=[f"{c}건" for c in counts],
        textposition="outside",
        hovertemplate="%{y}: %{x}건<extra></extra>",
    ))
    fig.update_layout(
        title="불량 원인별 건수",
        height=280,
        xaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False),
        yaxis=dict(showgrid=False),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 3. 품번별 불량률 비교 (세로 막대, 최고 불량률만 강조)
# ---------------------------------------------------------------------
def make_part_fig(data):
    info = f.list_part_codes(data)
    rows = info["parts"]
    if not rows:
        return None

    parts = [r["part_code"] for r in rows]
    rates = [r["defect_rate_pct"] for r in rows]
    max_rate = max(rates)
    colors = [COLOR_RED if r == max_rate else COLOR_MUTED for r in rates]

    fig = go.Figure(go.Bar(
        x=parts, y=rates,
        marker_color=colors,
        text=[f"{r}%" for r in rates],
        textposition="outside",
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title="품번별 불량률",
        height=280,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 4. 좌우(LH/RH) 불량률 비교
# ---------------------------------------------------------------------
def make_side_fig(data):
    info = f.list_part_codes(data)
    rows = info.get("by_side") or []
    if not rows:
        return None

    sides = [r["side"] for r in rows]
    rates = [r["defect_rate_pct"] for r in rows]
    max_rate = max(rates)
    colors = [COLOR_RED if r == max_rate else COLOR_MUTED for r in rates]

    fig = go.Figure(go.Bar(
        x=sides, y=rates,
        marker_color=colors,
        text=[f"{r}%" for r in rates],
        textposition="outside",
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title="좌우(LH/RH) 불량률",
        height=280,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 5. (STEP2 질문 전용) 정상 vs 불량 — 주요 변수 비교
# ---------------------------------------------------------------------
def make_variable_compare_fig(compare_result, top_n=4):
    diffs = (compare_result or {}).get("top_differences") or []
    if not diffs:
        return None
    diffs = diffs[:top_n]
    variables = [d["variable"] for d in diffs]
    normal_vals = [d["normal_mean"] for d in diffs]
    defect_vals = [d["defect_mean"] for d in diffs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=variables, y=normal_vals, name="정상",
        marker_color=COLOR_BLUE,
        text=[str(v) for v in normal_vals], textposition="outside",
        hovertemplate="%{x} 정상: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=variables, y=defect_vals, name="불량",
        marker_color=COLOR_RED,
        text=[str(v) for v in defect_vals], textposition="outside",
        hovertemplate="%{x} 불량: %{y}<extra></extra>",
    ))
    fig.update_layout(
        title="정상 vs 불량 — 주요 변수 비교",
        barmode="group",
        height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 6. (STEP2 질문 전용) 운전조건별 불량률 비교
# ---------------------------------------------------------------------
def make_mode_compare_fig(mode_info):
    modes = (mode_info or {}).get("modes") or []
    if not modes:
        return None
    names = [m["mode"] for m in modes]
    rates = [m["defect_rate_pct"] for m in modes]
    max_rate = max(rates)
    colors = [COLOR_RED if r == max_rate else COLOR_MUTED for r in rates]

    fig = go.Figure(go.Bar(
        x=names, y=rates,
        marker_color=colors,
        text=[f"{r}%" for r in rates],
        textposition="outside",
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title=f"운전조건별 불량률 ({mode_info.get('split_variable', '')} 기준)",
        height=320,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# 대시보드(공정 현황 요약)는 페이지를 열자마자 항상 보이는 게 아니라,
# 아래 "지금 공정 상황이 어때요?" 같은 질문을 했을 때만 답변으로 보여줍니다.
# — 이 앱의 핵심은 "물어보면 AI가 찾아서 보여준다"는 대화형 경험이라,
#   질문하기도 전에 결론을 다 까놓으면 그 경험이 죽습니다.

if "messages" not in st.session_state:
    st.session_state.messages = []

# 예시 질문 버튼 (데모 시나리오 STEP1~4)
st.write("**예시 질문:**")
col1, col2, col3, col4 = st.columns(4)
example_clicked = None
STEP1_QUESTION = "이번 주에 불량 유독 많았던 날 있었어요?"
STEP2_QUESTION = "가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?"
OVERVIEW_QUESTION = "지금 공정 상황이 어때요?"
if col1.button("이번 주 불량 많았던 날?"):
    example_clicked = STEP1_QUESTION
if col2.button("가스 불량 원인은?"):
    example_clicked = STEP2_QUESTION
if col3.button("뭘 조정해야 해?"):
    example_clicked = "그럼 뭘 조정해야 해요?"
if col4.button("야간에 불량이 왜 많아요?"):
    # STEP4 신뢰성 시연용 질문 — 데이터로 답할 수 없는 질문임을
    # 솔직하게 인정하는 모습을 보여주기 위한 버튼입니다.
    example_clicked = "야간에 불량이 왜 더 많아요?"

# 둘째 줄 — 미성형/RG3는 검증된 조치안이 없는 조합이라, '모른다'를 정직하게
# 인정하는 모습을 STEP4(야간 질문)와는 다른 맥락(조치 제안)에서 한 번 더
# 보여줄 수 있는 버튼입니다. part_code를 문장에 직접 넣어 RG3로 확실히 유도합니다.
# "지금 공정 상황이 어때요?"는 전체 현황(총생산량/불량률/원인별/품번별/좌우)을
# 대시보드 형태로 보여주는 질문입니다 — 페이지를 열자마자가 아니라, 이렇게
# 물어봤을 때만 뜨도록 일부러 챗봇 답변 쪽에 붙여뒀습니다.
col5, col6 = st.columns(2)
if col5.button("미성형은 RG3에서 어떻게 막아요?"):
    example_clicked = "미성형은 RG3에서 어떻게 막아야 해요?"
if col6.button("지금 공정 상황 요약해줘"):
    example_clicked = OVERVIEW_QUESTION


def render_answer_charts(question, data):
    """예시 질문에 맞춰, 답변 아래에 보여줄 차트를 그립니다.

    지금은 버튼 문구를 그대로 매칭해서 어떤 차트를 보여줄지 정하고 있습니다.
    나중에 agent.ask가 실제로 사용한 도구 이름을 돌려주게 되면, 문구 매칭 대신
    그 도구 이름 기준으로 바꾸는 게 더 정확합니다 (질문을 조금 다르게 표현해도
    같은 차트가 뜨도록).
    """
    if question == OVERVIEW_QUESTION:
        render_kpi_row(data)
        st.plotly_chart(make_trend_fig(daily_rate), use_container_width=True)

        dash_figs = [fig for fig in (
            make_reason_fig(data), make_part_fig(data), make_side_fig(data),
        ) if fig is not None]
        if dash_figs:
            for col, fig in zip(st.columns(len(dash_figs)), dash_figs):
                col.plotly_chart(fig, use_container_width=True)
        return

    if question == STEP1_QUESTION:
        st.plotly_chart(make_defect_chart(daily_rate), use_container_width=True)
        return

    if question == STEP2_QUESTION:
        compare = f.compare_normal_vs_defect(data, "가스", part_code="CN7", mode="고속")
        var_fig = make_variable_compare_fig(compare)
        mode_info = f.detect_operating_modes(data, "CN7")
        mode_fig = make_mode_compare_fig(mode_info)

        figs = [fig for fig in (var_fig, mode_fig) if fig is not None]
        if not figs:
            st.info("이 데이터에서는 비교할 만한 표본이 부족해서 그래프를 생략했습니다.")
            return
        for col, fig in zip(st.columns(len(figs)), figs):
            col.plotly_chart(fig, use_container_width=True)


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant" and msg.get("show_chart"):
            render_answer_charts(msg.get("question"), df)

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

        show_chart = user_input in (STEP1_QUESTION, STEP2_QUESTION, OVERVIEW_QUESTION)
        if show_chart:
            render_answer_charts(user_input, df)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "show_chart": show_chart,
         "question": user_input}
    )