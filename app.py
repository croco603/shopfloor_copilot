"""
app.py
------
현장 작업자가 보는 채팅 화면입니다. (Streamlit)
실행 방법: streamlit run app.py

구성
  - 사이드바: 언어 선택(영어 기본), 데이터 업로드, 대화 초기화
  - 본문: 예시 질문 버튼 + 채팅
  - 차트: '실제로 호출된 도구'를 보고 답변 아래에 자동으로 붙습니다.
          (질문 문장을 비교하면 사용자가 직접 타이핑할 때 빗나갑니다.)
  - 대시보드는 페이지를 열자마자가 아니라, "지금 공정 상황이 어때요?"처럼
    물어봤을 때만 보여줍니다. 이 앱의 핵심은 대화형 경험이라, 질문하기도 전에
    결론을 다 까놓으면 그 경험이 죽습니다.
"""

import json

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import functions as f
import agent

st.set_page_config(page_title="ShopFloor Copilot", page_icon="🏭", layout="wide")

# ---------------------------------------------------------------------
# 화면 문구 (영어 / 한국어)
# 심사위원이 영어권이므로 화면·답변·차트 제목을 모두 전환할 수 있게 합니다.
# ---------------------------------------------------------------------
LANG = {
    "en": {
        "caption": "Ask in plain language. Answers are backed by process data.",
        "ref_date": "Data as of {d} · {n:,} records",
        "settings": "Settings",
        "upload": "Upload process data (CSV)",
        "upload_ok": "Analyzing your uploaded data ({n:,} rows)",
        "missing": "Missing required columns: {cols}",
        "reset": "Clear conversation",
        "drop": "\U0001F4C2 Drop your CSV file here",
        "drop_alert": "Only CSV files can be uploaded.",
        "drop_no_input": "Could not find the file input.",
        "examples": "**Example questions**",
        "input": "Ask a question",
        "spinner": "Checking the data...",
        "kpi_total": "Total production",
        "kpi_rate": "Overall defect rate",
        "kpi_reason": "Top defect reason",
        "kpi_part": "Highest defect rate",
        "unit_ea": "{v:,}",
        "unit_case": "{v} cases",
        "t_prod": "Daily production",
        "t_rate": "Daily defect rate (%)",
        "t_reason": "Defects by reason",
        "t_part": "Defect rate by part",
        "t_side": "Defect rate by side (LH/RH)",
        "t_var": "Normal vs defective — key variables",
        "t_mode": "Defect rate by operating mode (by {v})",
        "l_prod": "Production",
        "l_rate": "Defect rate",
        "l_worst": "Peak {v}%",
        "l_worst_name": "Peak",
        "l_normal": "Normal",
        "l_defect": "Defective",
        "mode_labels": {"저속": "Low speed", "고속": "High speed"},
        "no_sample": "Not enough samples to compare, so the chart is omitted.",
        "b1": "Worst day this week?",
        "b2": "Why gas defects?",
        "b3": "What should we adjust?",
        "b4": "Why more defects at night?",
        "b5": "How to prevent short shots on RG3?",
        "b6": "Give me an overview",
        "q1": "Was there a day with an unusually high defect rate this week?",
        "q2": "What was different from normal products when gas defects happened?",
        "q3": "So what should we adjust?",
        "q4": "Why are there more defects at night?",
        "q5": "How can we prevent short shots on RG3?",
        "q6": "How does the process look right now?",
    },
    "ko": {
        "caption": "현장에서 쓰는 말로 물어보세요. 공정 데이터를 근거로 답합니다.",
        "ref_date": "데이터 기준일: {d} · 총 {n:,}건",
        "settings": "설정",
        "upload": "공정 데이터 업로드 (CSV)",
        "upload_ok": "업로드한 데이터로 분석합니다 ({n:,}행)",
        "missing": "필요한 컬럼이 없습니다: {cols}",
        "reset": "대화 초기화",
        "drop": "\U0001F4C2 여기에 CSV 파일을 놓으세요",
        "drop_alert": "CSV 파일만 업로드할 수 있습니다.",
        "drop_no_input": "파일 입력창을 찾을 수 없습니다.",
        "examples": "**예시 질문**",
        "input": "질문을 입력하세요",
        "spinner": "데이터 확인 중...",
        "kpi_total": "총 생산량",
        "kpi_rate": "전체 불량률",
        "kpi_reason": "최다 불량 원인",
        "kpi_part": "불량률 최고 품번",
        "unit_ea": "{v:,}개",
        "unit_case": "{v}건",
        "t_prod": "일별 생산량",
        "t_rate": "일별 불량률(%)",
        "t_reason": "불량 원인별 건수",
        "t_part": "품번별 불량률",
        "t_side": "좌우(LH/RH) 불량률",
        "t_var": "정상 vs 불량 — 주요 변수 비교",
        "t_mode": "운전조건별 불량률 ({v} 기준)",
        "l_prod": "생산량",
        "l_rate": "불량률",
        "l_worst": "최고 {v}%",
        "l_worst_name": "최고 불량률",
        "l_normal": "정상",
        "l_defect": "불량",
        "mode_labels": {"저속": "저속", "고속": "고속"},
        "no_sample": "이 데이터에서는 비교할 만한 표본이 부족해서 그래프를 생략했습니다.",
        "b1": "이번 주 불량 많았던 날?",
        "b2": "가스 불량 원인은?",
        "b3": "뭘 조정해야 해?",
        "b4": "야간에 불량이 왜 많아요?",
        "b5": "미성형은 RG3에서 어떻게 막아요?",
        "b6": "지금 공정 상황 요약해줘",
        "q1": "이번 주에 불량 유독 많았던 날 있었어요?",
        "q2": "가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?",
        "q3": "그럼 뭘 조정해야 해요?",
        "q4": "야간에 불량이 왜 더 많아요?",
        "q5": "미성형은 RG3에서 어떻게 막아야 해요?",
        "q6": "지금 공정 상황이 어때요?",
    },
}

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

# ---------------------------------------------------------------------
# 사이드바 — 언어 / 업로드 / 초기화
# ---------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Language / 언어")
    # 심사위원이 처음 열었을 때 영어가 보이도록 영어를 기본값으로 둡니다.
    _choice = st.radio("Language", ["English", "한국어"], index=0,
                       horizontal=True, label_visibility="collapsed")
    lang = "en" if _choice == "English" else "ko"
    T = LANG[lang]

    st.markdown("### " + T["settings"])
    uploaded_file = st.file_uploader(T["upload"], type="csv", key="csv_uploader")
    if st.button(T["reset"]):
        st.session_state.messages = []
        st.rerun()

st.title("🏭 ShopFloor Copilot")
st.caption(T["caption"])


@st.cache_data
def get_data(source=None):
    return f.load_data(source)


# ▼ 화면 전체 드래그 앤 드롭 업로드 기능 ▼
# Streamlit은 file_uploader 박스 안에서만 드롭을 받습니다. 화면 어디에 놓아도
# 업로드되게 하려고, 최상위 문서(window.parent.document)에 드롭 이벤트를 직접 답니다.
#
# 주의: st.markdown(unsafe_allow_html=True)로 <img onerror="..."> 를 넣는 방법은
#      Streamlit이 이벤트 속성(onerror 등)을 지워버려서 실행되지 않습니다.
#      그래서 components.html로 iframe을 하나 띄우고, 그 안에서 부모 문서를 조작합니다.
#      (iframe은 높이 0이라 화면에 보이지 않습니다.)
_DROP_ZONE_JS = """
<script>
(function() {
    const doc = window.parent.document;
    if (!doc || doc.body.dataset.dropZoneInstalled) { return; }
    doc.body.dataset.dropZoneInstalled = 'true';

    function showOverlay() {
        let overlay = doc.getElementById('dropOverlay');
        if (!overlay) {
            overlay = doc.createElement('div');
            overlay.id = 'dropOverlay';
            overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,100,255,0.15);border:4px dashed #0064ff;z-index:999999;display:flex;align-items:center;justify-content:center;font-size:28px;color:#0064ff;font-weight:bold;pointer-events:none;';
            overlay.innerText = __DROP_TEXT__;
            doc.body.appendChild(overlay);
        }
        overlay.innerText = __DROP_TEXT__;
        overlay.style.display = 'flex';
    }

    function hideOverlay() {
        const overlay = doc.getElementById('dropOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    doc.addEventListener('dragover', function(e) {
        e.preventDefault();
        showOverlay();
    });

    doc.addEventListener('dragleave', function(e) {
        if (e.clientX <= 0 || e.clientY <= 0) hideOverlay();
    });

    doc.addEventListener('drop', function(e) {
        e.preventDefault();
        hideOverlay();

        const files = e.dataTransfer.files;
        if (!files || files.length === 0) return;

        if (!files[0].name.toLowerCase().endsWith('.csv')) {
            alert(__DROP_ALERT__);
            return;
        }

        // 사이드바의 file_uploader 입력창을 찾아 파일을 강제로 넣어줍니다.
        const fileInput = doc.querySelector('section[data-testid="stSidebar"] input[type="file"]')
                       || doc.querySelector('input[type="file"]');
        if (!fileInput) {
            alert(__DROP_NO_INPUT__);
            return;
        }

        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(files[0]);
        fileInput.files = dataTransfer.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
})();
</script>
"""

components.html(
    _DROP_ZONE_JS
    .replace("__DROP_TEXT__", json.dumps(T["drop"]))
    .replace("__DROP_ALERT__", json.dumps(T["drop_alert"]))
    .replace("__DROP_NO_INPUT__", json.dumps(T["drop_no_input"])),
    height=0,
)
# ▲ 화면 전체 드래그 앤 드롭 업로드 기능 끝 ▲

if uploaded_file is not None:
    df_up = pd.read_csv(uploaded_file)
    missing = f.validate_columns(df_up)
    if missing:
        st.error(T["missing"].format(cols=", ".join(missing[:5])))
        st.stop()
    df = get_data(uploaded_file)
    st.sidebar.success(T["upload_ok"].format(n=len(df)))
else:
    df = get_data()

# 2020년 데이터를 쓰는 이유를 심사위원이 바로 알 수 있게 기준일을 밝힙니다.
st.caption(T["ref_date"].format(d=df["date"].max(), n=len(df)))


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
def render_kpi_row(data, T):
    total = len(data)
    n_fail = int((data["PassOrFail"] == "N").sum())
    fail_rate = round(n_fail / total * 100, 2) if total else 0.0

    reason_info = f.count_defects_by_reason(data)
    top_reason = reason_info["by_reason"][0] if reason_info["by_reason"] else None

    part_info = f.list_part_codes(data)
    top_part = part_info["parts"][0] if part_info["parts"] else None

    kpis = [
        (T["kpi_total"], T["unit_ea"].format(v=total), None),
        (T["kpi_rate"], f"{fail_rate}%", T["unit_case"].format(v=n_fail)),
        (T["kpi_reason"], top_reason["reason"] if top_reason else "-",
         T["unit_case"].format(v=top_reason["count"]) if top_reason else None),
        (T["kpi_part"], top_part["part_code"] if top_part else "-",
         f"{top_part['defect_rate_pct']}%" if top_part else None),
    ]
    # 카드마다 테두리를 둘러서 배경 위에 붕 떠 보이지 않고 하나의 패널처럼 보이게 합니다.
    for col, (label, value, delta) in zip(st.columns(4, gap="medium"), kpis):
        with col, st.container(border=True):
            st.metric(label, value, delta, delta_color="off")


def render_chart_card(fig):
    """차트 하나를 테두리 있는 카드 안에 넣어서 그립니다. (배경에 붕 떠 보이는 것 방지)"""
    with st.container(border=True):
        st.plotly_chart(fig, use_container_width=True)


def render_chart_row(figs):
    figs = [fig for fig in figs if fig is not None]
    if not figs:
        return
    for col, fig in zip(st.columns(len(figs), gap="medium"), figs):
        with col:
            render_chart_card(fig)


# ---------------------------------------------------------------------
# 차트 1-1. 일별 생산량
# 차트 1-2. 일별 불량률 (최고 불량률 날 강조)
# 두 지표는 단위(개 vs %)도 다르고 쓰이는 질문 맥락도 달라서, 억지로 한 차트에
# 묶지 않고 다른 차트들처럼 완전히 독립된 카드로 나눠서 보여줍니다.
# ---------------------------------------------------------------------
def make_production_fig(daily, T):
    fig = go.Figure(go.Bar(
        x=daily["date"], y=daily["생산"],
        marker_color=COLOR_BLUE,
        hovertemplate="%{x|%m/%d}<br>%{y}<extra></extra>",
    ))
    fig.update_layout(
        title=T["t_prod"],
        height=340,
        xaxis=dict(showgrid=False, tickformat="%m/%d"),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False),
        **CHART_BASE_LAYOUT,
    )
    return fig


def make_defect_rate_fig(daily, T):
    worst_idx = daily["불량률(%)"].idxmax()
    worst_row = daily.loc[worst_idx]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["불량률(%)"],
        mode="lines+markers",
        line=dict(color=COLOR_BLUE, width=2),
        marker=dict(size=6),
        name=T["l_rate"],
        hovertemplate="%{x|%m/%d}<br>%{y}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[worst_row["date"]], y=[worst_row["불량률(%)"]],
        mode="markers+text",
        marker=dict(size=14, color=COLOR_RED, symbol="star"),
        text=[T["l_worst"].format(v=worst_row["불량률(%)"])],
        textposition="top center",
        name=T["l_worst_name"],
        hovertemplate="%{x|%m/%d}<br>%{y}%<extra></extra>",
    ))
    fig.update_layout(
        title=T["t_rate"],
        height=340,
        showlegend=False,
        xaxis=dict(showgrid=False, tickformat="%m/%d"),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 2. 불량 원인별 건수 (가로 막대, 최다 원인만 강조)
# ---------------------------------------------------------------------
def make_reason_fig(data, T):
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
        text=[str(c) for c in counts],
        textposition="outside",
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title=T["t_reason"],
        height=340,
        xaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False),
        yaxis=dict(showgrid=False),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 3. 품번별 불량률 비교 (세로 막대, 최고 불량률만 강조)
# ---------------------------------------------------------------------
def make_part_fig(data, T):
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
        title=T["t_part"],
        height=340,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 4. 좌우(LH/RH) 불량률 비교
# ---------------------------------------------------------------------
def make_side_fig(data, T):
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
        title=T["t_side"],
        height=340,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 5. (STEP2 질문 전용) 정상 vs 불량 — 주요 변수 비교
# ---------------------------------------------------------------------
def make_variable_compare_fig(compare_result, T, top_n=4):
    diffs = (compare_result or {}).get("top_differences") or []
    if not diffs:
        return None
    diffs = diffs[:top_n]
    variables = [d["variable"].replace("_", " ") for d in diffs]
    normal_vals = [d["normal_mean"] for d in diffs]
    defect_vals = [d["defect_mean"] for d in diffs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=variables, y=normal_vals, name=T["l_normal"],
        marker_color=COLOR_BLUE,
        text=[str(v) for v in normal_vals], textposition="outside",
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=variables, y=defect_vals, name=T["l_defect"],
        marker_color=COLOR_RED,
        text=[str(v) for v in defect_vals], textposition="outside",
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    fig.update_layout(
        # 기존에는 위쪽 여백(margin.t=40)이 좁은 채로 제목이랑 범례를 둘 다
        # 그 안에 밀어넣어서 글씨가 겹쳐 보였습니다. 여백을 넉넉히 키우고,
        # 범례는 그 넓어진 여백의 아래쪽(그래프 바로 위)에, 제목은 위쪽에
        # 오도록 확실히 떨어뜨립니다.
        title=T["t_var"],
        barmode="group",
        height=360,
        margin=dict(l=10, r=10, t=80, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---------------------------------------------------------------------
# 차트 6. (STEP2 질문 전용) 운전조건별 불량률 비교
# ---------------------------------------------------------------------
def make_mode_compare_fig(mode_info, T):
    modes = (mode_info or {}).get("modes") or []
    if not modes:
        return None
    # functions.py는 운전조건 이름을 항상 "저속"/"고속"(한글)으로 돌려주므로,
    # 화면 언어가 영어일 때는 여기서 화면 표시용으로만 번역합니다
    # (원본 데이터/로직은 그대로 두고 보여주는 글자만 바꿉니다).
    labels = T.get("mode_labels", {})
    names = [labels.get(m["mode"], m["mode"]) for m in modes]
    rates = [m["defect_rate_pct"] for m in modes]
    max_rate = max(rates)
    colors = [COLOR_RED if r == max_rate else COLOR_MUTED for r in rates]

    split_var = mode_info.get("split_variable", "").replace("_", " ")

    fig = go.Figure(go.Bar(
        x=names, y=rates,
        marker_color=colors,
        text=[f"{r}%" for r in rates],
        textposition="outside",
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title=T["t_mode"].format(v=split_var),
        height=360,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=COLOR_GRID, zeroline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig



daily_rate = get_daily_defect_rate(df)


# ---------------------------------------------------------------------
# 답변 아래 차트 — '실제로 호출된 도구'를 보고 정합니다.
# 질문 문장을 비교하지 않으므로, 사용자가 직접 타이핑해도 차트가 나옵니다.
# ---------------------------------------------------------------------
def decide_charts(tools_used, data):
    """도구 이름 목록을 보고, 붙일 차트 정보를 리스트로 돌려줍니다."""
    used = set(tools_used)
    spec = []

    # 현황 요약 질문은 여러 도구를 한꺼번에 부릅니다 -> 대시보드 전체를 보여줍니다.
    if len(used & {"count_defects_by_reason", "list_part_codes", "get_worst_day"}) >= 2:
        return [{"kind": "overview"}]

    if "get_worst_day" in used:
        spec.append({"kind": "trend"})

    wants_cause = "compare_normal_vs_defect" in used
    if wants_cause or "get_operating_modes" in used:
        parts = f.list_part_codes(data)["parts"]
        top = next((p["part_code"] for p in parts if p["n_defect"] >= 5), None)
        if top:
            spec.append({"kind": "mode", "part_code": top})

    if wants_cause:
        # 실제로 차이가 나온 (원인·품번·조건) 조합을 하나만 골라 비교 차트를 붙입니다.
        for reason in ("가스", "미성형", "초기허용불량"):
            for part in ("CN7", "RG3"):
                for mode in ("고속", "저속", None):
                    r = f.compare_normal_vs_defect(data, reason,
                                                   part_code=part, mode=mode)
                    if r.get("top_differences"):
                        spec.append({"kind": "compare", "reason": reason,
                                     "part_code": part, "mode": mode})
                        return spec
    return spec


def render_answer_charts(spec, data, T):
    """decide_charts가 만든 정보를 실제 차트로 그립니다."""
    if not spec:
        return

    if spec[0].get("kind") == "overview":
        render_kpi_row(data, T)
        daily = get_daily_defect_rate(data)
        render_chart_row([make_production_fig(daily, T), make_defect_rate_fig(daily, T)])
        render_chart_row([make_reason_fig(data, T),
                          make_part_fig(data, T),
                          make_side_fig(data, T)])
        return

    figs = []
    for item in spec:
        kind = item.get("kind")
        if kind == "trend":
            figs.append(make_defect_rate_fig(get_daily_defect_rate(data), T))
        elif kind == "mode":
            figs.append(make_mode_compare_fig(
                f.detect_operating_modes(data, item["part_code"]), T))
        elif kind == "compare":
            figs.append(make_variable_compare_fig(
                f.compare_normal_vs_defect(data, item["reason"],
                                           part_code=item["part_code"],
                                           mode=item.get("mode")), T))

    figs = [fig for fig in figs if fig is not None]
    if not figs:
        st.info(T["no_sample"])
        return
    if len(figs) == 1:
        render_chart_card(figs[0])
    else:
        render_chart_row(figs)


# ---------------------------------------------------------------------
# 예시 질문 버튼
# ---------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

st.write(T["examples"])
col1, col2, col3, col4 = st.columns(4)
example_clicked = None
if col1.button(T["b1"]):
    example_clicked = T["q1"]
if col2.button(T["b2"]):
    example_clicked = T["q2"]
if col3.button(T["b3"]):
    example_clicked = T["q3"]
if col4.button(T["b4"]):
    # 데이터로 답할 수 없는 질문임을 솔직하게 인정하는 모습을 보여주는 버튼입니다.
    example_clicked = T["q4"]

# 둘째 줄 — 미성형/RG3는 검증된 조치안이 없는 조합이라, '모른다'를 조치 제안
# 맥락에서 한 번 더 보여줄 수 있는 버튼입니다.
# "지금 공정 상황이 어때요?"는 전체 현황을 대시보드로 보여주는 질문입니다.
col5, col6 = st.columns(2)
if col5.button(T["b5"]):
    example_clicked = T["q5"]
if col6.button(T["b6"]):
    example_clicked = T["q6"]

# ---------------------------------------------------------------------
# 대화
# ---------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant":
            render_answer_charts(msg.get("charts"), df, T)

user_input = st.chat_input(T["input"]) or example_clicked

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner(T["spinner"]):
            history = st.session_state.messages[:-1][-6:]
            tools_used = []
            answer = agent.ask(user_input, df, history=history,
                               lang=lang, tools_used=tools_used)
            charts = decide_charts(tools_used, df)
        st.write(answer)
        render_answer_charts(charts, df, T)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "charts": charts}
    )