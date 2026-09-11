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

import html
import json
import re

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
        "headline": "Answers backed by data, not guesswork",
        "badges": [
            "📊 Every answer backed by real data, with auto-generated charts",
            "🗣️ Ask in plain shop-floor language, no jargon needed",
            "📁 Upload your own data and get instant analysis",
        ],
        "caption": "An AI assistant for your injection-molding process data. Ask in plain language and get answers backed by real production data, along with charts. AI can make mistakes — please double-check important information.",
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
        "t_rate_days": "Daily defect rate (%) · last {d} days",
        "t_reason": "Defects by reason",
        "t_part": "Defect rate by part",
        "t_side": "Defect rate by side (LH/RH)",
        "t_var": "Normal vs defective · {ctx}",
        "t_mode": "{p} · Defect rate by operating mode (by {v})",
        "l_prod": "Production",
        "l_rate": "Defect rate",
        "l_worst": "Peak {v}%",
        "l_worst_name": "Peak",
        "l_normal": "Normal",
        "l_defect": "Defective",
        "l_same_day": "Normal (same day)",
        "mode_labels": {"저속": "Low speed", "고속": "High speed"},
        "reason_labels": {"가스": "Gas", "미성형": "Short shot", "초기허용불량": "Startup scrap"},
        # [주야간] 주야간 차트·합성 데이터 안내
        "t_shift": "Defect rate by shift · combined vs same part and mode",
        "t_shift_prod": "Production by shift · too little on one shift to compare",
        "shift_labels": {"주간": "Day shift", "야간": "Night shift"},
        "l_all": "All combined",
        "synthetic_banner": ("Synthetic demo data: some production times were shifted to create "
                             "day-shift records. Sensor values and defect labels are unchanged. "
                             "This is not a real factory result."),
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
        "headline": "감이 아니라 데이터로 답하는 공정 어시스턴트",
        "badges": [
            "📊 답변마다 실제 데이터 근거 + 그래프 자동 생성",
            "🗣️ 어려운 용어 없이, 현장에서 쓰는 말 그대로 질문",
            "📁 내 데이터 업로드해서 바로 분석",
        ],
        "caption": "사출성형 공정 데이터를 분석하는 AI 어시스턴트입니다. 현장에서 쓰는 말 그대로 물어보면, 실제 생산 데이터를 근거로 답변과 그래프를 함께 보여드려요. AI가 생성한 답변은 부정확할 수 있으니 중요한 내용은 다시 확인해 주세요.",
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
        "t_rate_days": "일별 불량률(%) · 최근 {d}일",
        "t_reason": "불량 원인별 건수",
        "t_part": "품번별 불량률",
        "t_side": "좌우(LH/RH) 불량률",
        "t_var": "정상 vs 불량 · {ctx}",
        "t_mode": "{p} 운전조건별 불량률 ({v} 기준)",
        "l_prod": "생산량",
        "l_rate": "불량률",
        "l_worst": "최고 {v}%",
        "l_worst_name": "최고 불량률",
        "l_normal": "정상",
        "l_defect": "불량",
        "l_same_day": "정상(같은 날)",
        "mode_labels": {"저속": "저속", "고속": "고속"},
        "reason_labels": {"가스": "가스", "미성형": "미성형", "초기허용불량": "초기허용불량"},
        # [주야간] 주야간 차트·합성 데이터 안내
        "t_shift": "교대별 불량률 · 전체 합산 vs 같은 품번·조건",
        "t_shift_prod": "교대별 생산량 · 한쪽 생산이 적어 비교 불가",
        "shift_labels": {"주간": "주간", "야간": "야간"},
        "l_all": "전체 합산",
        "synthetic_banner": ("시연용 합성 데이터입니다. 주간 생산을 만들기 위해 일부 생산 시각만 옮겼고, "
                             "센서값과 불량 판정은 그대로입니다. 실제 공장 결과가 아닙니다."),
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
COLOR_AXIS = "#383835"    # 축선/기준선 (팔레트의 baseline/axis 톤)
COLOR_TEXT = "#c3c2b7"    # 라벨/눈금 글자 (막대 색을 그대로 쓰지 않고 별도 텍스트 톤 사용)
COLOR_SURFACE = "#0e1117"  # Streamlit 다크 테마 배경. 마커 테두리/툴팁 배경에 맞춰 씁니다.
CHART_FONT = "'Source Sans Pro', -apple-system, 'Segoe UI', sans-serif"

# [디자인 수정] 기본 plotly 차트가 "파워포인트 기본 차트 같다"는 피드백을 받아서,
# 폰트/축선/툴팁/막대 모서리 등 세부 마감을 다시 잡았습니다. 굵은 색은 데이터에만
# 쓰고, 축/그리드/라벨은 절제된 톤으로 - 라는 원칙으로 아래 공통 스타일을 정의합니다.
CHART_BASE_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=48, b=10),
    font=dict(family=CHART_FONT, color=COLOR_TEXT, size=12),
    hoverlabel=dict(bgcolor=COLOR_SURFACE, bordercolor=COLOR_GRID,
                     font=dict(family=CHART_FONT, color="#ffffff", size=12)),
    bargap=0.45,
)

# 막대/선/마커에 공통으로 쓰는 마감 스펙 (둥근 막대 끝, 굵기 있는 마커+테두리).
BAR_MARKER_STYLE = dict(cornerradius=4, line=dict(width=0))
LABEL_FONT = dict(family=CHART_FONT, color=COLOR_TEXT, size=12)


def chart_title(text):
    """모든 차트 제목을 같은 폰트/크기/왼쪽 정렬로 통일합니다.

    fig.update_layout(title=..., **CHART_BASE_LAYOUT)처럼 title을 매번
    별도 인자로 넘기기 때문에, title 스타일은 CHART_BASE_LAYOUT 안에 두지
    않고 이 헬퍼로 각 호출부에서 직접 만듭니다 (안 그러면 title 키가
    두 번 넘어가서 "multiple values for keyword argument" 에러가 납니다).
    """
    return dict(text=text, font=dict(family=CHART_FONT, color="#ffffff", size=15),
                x=0.02, xanchor="left")


def axis_style(**overrides):
    """축선을 팔레트의 절제된 톤으로 통일합니다 (plotly 기본 회색 대신)."""
    base = dict(showline=True, linecolor=COLOR_AXIS, ticks="outside",
                tickcolor=COLOR_AXIS, tickfont=LABEL_FONT, zeroline=False)
    base.update(overrides)
    return base

# ---------------------------------------------------------------------
# 사이드바 — 언어 / 업로드 / 초기화
# ---------------------------------------------------------------------
# [지원님 작업] 답변을 만드는 동안 언어 토글을 누르면, Streamlit이 진행 중이던 답변
# 생성을 그 자리에서 중단해버려서 답변이 통째로 사라집니다. 그래서 답변 생성 중에는
# 언어 토글(과 질문을 새로 보낼 수 있는 다른 버튼들)을 비활성화해 누르지 못하게 막습니다.
is_generating = st.session_state.get("is_generating", False)

with st.sidebar:
    st.markdown("### Language / 언어")
    # 심사위원이 처음 열었을 때 영어가 보이도록 영어를 기본값으로 둡니다.
    _choice = st.radio("Language", ["English", "한국어"], index=0,
                       horizontal=True, label_visibility="collapsed",
                       disabled=is_generating)
    lang = "en" if _choice == "English" else "ko"
    T = LANG[lang]

    st.markdown("### " + T["settings"])
    uploaded_file = st.file_uploader(T["upload"], type="csv", key="csv_uploader",
                                      disabled=is_generating)
    if st.button(T["reset"], disabled=is_generating):
        st.session_state.messages = []
        st.rerun()

st.title("🏭 ShopFloor Copilot")

# 처음 보는 사람도 "이게 뭐하는 앱인지, 뭐가 좋은지"를 3초 안에 알 수 있게
# 헤드라인 한 줄 + 핵심 장점 3가지를 보여줍니다.
# (테두리 박스로 감싸면 아래 예시 질문 버튼이랑 비슷해 보여서 "이것도 눌러야
#  하나?" 하는 착각을 줄 수 있습니다. 그래서 버튼처럼 안 보이게, 배경이 옅은
#  알약 모양 태그로 한 줄에 나란히 붙여서 보여줍니다.)
st.markdown(f"#### {T['headline']}")
_badge_html = "".join(
    f'<span style="display:inline-block;background:rgba(57,135,229,0.12);'
    f'color:#3987e5;border-radius:999px;padding:5px 14px;margin:2px 8px 8px 0;'
    f'font-size:0.85rem;font-weight:500;white-space:nowrap;">{_badge}</span>'
    for _badge in T["badges"]
)
st.markdown(_badge_html, unsafe_allow_html=True)


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

# 소개문구 + 기준일을 한 캡션 안에 묶어서 보여줍니다. 예전에는 둘을 따로 된 캡션으로
# 나눠서 보여줘서, 기준일이 마치 또 하나의 독립된 안내문처럼 붕 떠 보였습니다.
# (2020년 데이터를 쓰는 이유를 심사위원이 알 수 있게 기준일 자체는 남겨두되,
#  존재감은 낮춰서 소개문구에 딸린 부가정보처럼 보이게 합니다.)
st.caption(f"{T['caption']}  \n{T['ref_date'].format(d=df['date'].max(), n=len(df))}")

# [주야간] 업로드한 파일이 시연용 합성 데이터면, 실제 결과로 오해하지 않게 눈에 띄게 알립니다.
if f.is_synthetic(df):
    st.warning(T["synthetic_banner"], icon="🧪")


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
def render_kpi_row(data, T, key_prefix="kpi"):
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
    # [버그 수정] st.metric()은 key 인자를 받지 않습니다(공식 문서 기준 미지원 파라미터라
    # TypeError가 남). 실제 배포 사이트에서 "현재 상황 요약" 질문에 이 대시보드가
    # 처음 정상적으로 그려지자마자 이 에러로 죽는 게 확인됐습니다. 같은 KPI가
    # 여러 메시지에 걸쳐 반복돼도 구분되게 하려던 목적은 st.metric 대신 그걸
    # 감싸는 st.container 쪽에 key를 줘서 그대로 달성합니다(container는 key를
    # 지원합니다).
    for i, (col, (label, value, delta)) in enumerate(zip(st.columns(4, gap="medium"), kpis)):
        with col, st.container(border=True, key=f"{key_prefix}_{i}"):
            st.metric(label, value, delta, delta_color="off")


def render_chart_card(fig, key=None):
    """차트 하나를 테두리 있는 카드 안에 넣어서 그립니다. (배경에 붕 떠 보이는 것 방지)

    key: 같은 figure가 여러 메시지에 걸쳐 반복돼도 Streamlit이 서로 다른
         요소로 인식하도록 하는 고유값입니다. (StreamlitDuplicateElementId 방지)
    """
    with st.container(border=True):
        # [디자인 수정] 기본 plotly 툴바(카메라/줌/팬 아이콘)가 계속 떠 있으면
        # 완제품이 아니라 "그래프 그리는 도구" 느낌이 나서 꺼둡니다.
        st.plotly_chart(fig, use_container_width=True, key=key,
                        config={"displayModeBar": False})


def render_chart_row(figs, key_prefix="row"):
    figs = [fig for fig in figs if fig is not None]
    if not figs:
        return
    for i, (col, fig) in enumerate(zip(st.columns(len(figs), gap="medium"), figs)):
        with col:
            render_chart_card(fig, key=f"{key_prefix}_{i}")


# ---------------------------------------------------------------------
# 차트 1-1. 일별 생산량
# 차트 1-2. 일별 불량률 (최고 불량률 날 강조)
# 두 지표는 단위(개 vs %)도 다르고 쓰이는 질문 맥락도 달라서, 억지로 한 차트에
# 묶지 않고 다른 차트들처럼 완전히 독립된 카드로 나눠서 보여줍니다.
# ---------------------------------------------------------------------
def make_production_fig(daily, T):
    fig = go.Figure(go.Bar(
        x=daily["date"], y=daily["생산"],
        marker=dict(color=COLOR_BLUE, **BAR_MARKER_STYLE),
        hovertemplate="%{x|%m/%d}<br>%{y}<extra></extra>",
    ))
    fig.update_layout(
        title=chart_title(T["t_prod"]),
        height=340,
        # [버그 수정] 날짜 범위가 좁을 때(예: 최근 7일) plotly가 자동으로 하루보다
        # 촘촘한 간격(예: 12시간)으로 눈금을 잡아서, tickformat="%m/%d"에는 시간이
        # 안 보이니까 같은 날짜가 두 번씩 찍혀 보이는 문제가 있었습니다.
        # dtick을 하루(밀리초 단위 86400000)로 고정해서 항상 하루에 눈금 하나만
        # 찍히게 합니다.
        xaxis=axis_style(showgrid=False, tickformat="%m/%d", dtick=86400000),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False),
        **CHART_BASE_LAYOUT,
    )
    return fig


def make_defect_rate_fig(daily, T, days=None):
    # [수정 P2] "이번 주"(days=7)를 물었는데 전체 기간 차트가 나오던 문제.
    # functions.get_worst_day와 똑같이 데이터 마지막 날을 '오늘'로 보고 자릅니다.
    title = T["t_rate"]
    if days:
        cutoff = daily["date"].max() - pd.Timedelta(days=int(days) - 1)
        daily = daily[daily["date"] >= cutoff]
        title = T["t_rate_days"].format(d=int(days))
    if daily.empty:
        return None
    worst_idx = daily["불량률(%)"].idxmax()
    worst_row = daily.loc[worst_idx]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["불량률(%)"],
        mode="lines+markers",
        line=dict(color=COLOR_BLUE, width=2, shape="spline", smoothing=0.3),
        # [디자인 수정] 마커를 8px 이상으로 키우고, 배경색으로 얇은 테두리(ring)를
        # 둘러서 선 위에 놓여도 뭉개지지 않고 또렷하게 보이게 합니다.
        marker=dict(size=8, color=COLOR_BLUE, line=dict(width=2, color=COLOR_SURFACE)),
        name=T["l_rate"],
        hovertemplate="%{x|%m/%d}<br>%{y}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[worst_row["date"]], y=[worst_row["불량률(%)"]],
        mode="markers+text",
        marker=dict(size=16, color=COLOR_RED, symbol="star",
                    line=dict(width=2, color=COLOR_SURFACE)),
        text=[T["l_worst"].format(v=worst_row["불량률(%)"])],
        textposition="top center",
        textfont=LABEL_FONT,
        name=T["l_worst_name"],
        hovertemplate="%{x|%m/%d}<br>%{y}%<extra></extra>",
    ))
    fig.update_layout(
        title=chart_title(title),
        height=340,
        showlegend=False,
        # [버그 수정] make_production_fig와 같은 이유로, 날짜 범위가 좁은
        # "최근 N일" 질문에서 같은 날짜가 두 번씩 찍히던 문제를 dtick 고정으로 막습니다.
        xaxis=axis_style(showgrid=False, tickformat="%m/%d", dtick=86400000),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False, ticksuffix="%"),
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

    # [수정 P3] 영어 화면에서 막대 이름이 '가스'로 나오던 문제
    labels = T.get("reason_labels", {})
    reasons = [labels.get(r["reason"], r["reason"]) for r in rows][::-1]
    counts = [r["count"] for r in rows][::-1]
    max_count = max(counts)
    colors = [COLOR_RED if c == max_count else COLOR_MUTED for c in counts]

    fig = go.Figure(go.Bar(
        x=counts, y=reasons, orientation="h",
        marker=dict(color=colors, **BAR_MARKER_STYLE),
        text=[str(c) for c in counts],
        textposition="outside",
        textfont=LABEL_FONT,
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title=chart_title(T["t_reason"]),
        height=340,
        xaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False),
        yaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
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
        marker=dict(color=colors, **BAR_MARKER_STYLE),
        text=[f"{r}%" for r in rates],
        textposition="outside",
        textfont=LABEL_FONT,
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title=chart_title(T["t_part"]),
        height=340,
        xaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False, ticksuffix="%"),
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
        marker=dict(color=colors, **BAR_MARKER_STYLE),
        text=[f"{r}%" for r in rates],
        textposition="outside",
        textfont=LABEL_FONT,
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        title=chart_title(T["t_side"]),
        height=340,
        xaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 5. (STEP2 질문 전용) 정상 vs 불량 — 주요 변수 비교
# ---------------------------------------------------------------------
def make_variable_compare_fig(compare_result, T, top_n=4, context=""):
    diffs = (compare_result or {}).get("top_differences") or []
    if not diffs:
        return None
    diffs = diffs[:top_n]
    variables = [d["variable"].replace("_", " ") for d in diffs]
    normal_vals = [d["normal_mean"] for d in diffs]
    defect_vals = [d["defect_mean"] for d in diffs]
    # [수정 P4] 불량이 난 날의 정상 제품 평균도 같이 그립니다.
    # 이 막대가 불량 막대와 비슷하면 "그날이 원래 그랬다"는 뜻이라 원인으로 볼 수 없습니다.
    same_day_vals = [(d.get("same_day_check") or {}).get("same_day_normal_mean") for d in diffs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=variables, y=normal_vals, name=T["l_normal"],
        marker=dict(color=COLOR_BLUE, **BAR_MARKER_STYLE),
        text=[str(v) for v in normal_vals], textposition="outside", textfont=LABEL_FONT,
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    if any(v is not None for v in same_day_vals):
        fig.add_trace(go.Bar(
            x=variables, y=same_day_vals, name=T["l_same_day"],
            marker=dict(color=COLOR_MUTED, **BAR_MARKER_STYLE),
            text=["" if v is None else str(v) for v in same_day_vals], textposition="outside",
            textfont=LABEL_FONT,
            hovertemplate="%{x}: %{y}<extra></extra>",
        ))
    fig.add_trace(go.Bar(
        x=variables, y=defect_vals, name=T["l_defect"],
        marker=dict(color=COLOR_RED, **BAR_MARKER_STYLE),
        text=[str(v) for v in defect_vals], textposition="outside", textfont=LABEL_FONT,
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    fig.update_layout(
        # 기존에는 위쪽 여백(margin.t=40)이 좁은 채로 제목이랑 범례를 둘 다
        # 그 안에 밀어넣어서 글씨가 겹쳐 보였습니다. 여백을 넉넉히 키우고,
        # 범례는 그 넓어진 여백의 아래쪽(그래프 바로 위)에, 제목은 위쪽에
        # 오도록 확실히 떨어뜨립니다.
        title=chart_title(T["t_var"].format(ctx=context)),
        barmode="group",
        bargap=0.35,
        bargroupgap=0.15,
        height=360,
        margin=dict(l=10, r=10, t=80, b=10),
        font=dict(family=CHART_FONT, color=COLOR_TEXT, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=LABEL_FONT, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=COLOR_SURFACE, bordercolor=COLOR_GRID,
                         font=dict(family=CHART_FONT, color="#ffffff", size=12)),
        xaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False),
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
        marker=dict(color=colors, **BAR_MARKER_STYLE),
        text=[f"{r}%" for r in rates],
        textposition="outside",
        textfont=LABEL_FONT,
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.update_layout(
        # [수정 P5] 어느 품번 차트인지 제목에 밝힙니다. (RG3 차트인데 품번이 안 보이던 문제)
        title=chart_title(T["t_mode"].format(p=mode_info.get("part_code", ""), v=split_var)),
        height=360,
        xaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False, ticksuffix="%"),
        **CHART_BASE_LAYOUT,
    )
    return fig


# ---------------------------------------------------------------------
# 차트 7. [주야간] 교대별 불량률 — 전체 합산과 같은 품번·조건끼리 비교를 나란히
# ---------------------------------------------------------------------
# 합산 막대만 보면 "야간이 문제"처럼 보입니다. 바로 옆에 같은 품번·조건끼리 비교한
# 막대를 붙여서, 차이가 사라지는지 한눈에 보이게 합니다.
# 비교할 수 없는 데이터(한쪽 교대 생산이 너무 적음)면 교대별 생산량만 보여줍니다.
def make_shift_fig(shift_result, T):
    r = shift_result or {}
    if r.get("error"):
        return None
    labels = T.get("shift_labels", {})
    names = ("주간", "야간")
    colors = {"주간": COLOR_MUTED, "야간": COLOR_BLUE}

    if not r.get("comparable"):
        prod = r.get("production_by_shift") or {}
        counts = [prod.get(n, 0) for n in names]
        fig = go.Figure(go.Bar(
            x=[labels.get(n, n) for n in names], y=counts,
            marker=dict(color=[colors[n] for n in names], **BAR_MARKER_STYLE),
            text=[f"{c:,}" for c in counts], textposition="outside", textfont=LABEL_FONT,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        ))
        fig.update_layout(
            title=chart_title(T["t_shift_prod"]),
            height=340,
            xaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
            yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False),
            **CHART_BASE_LAYOUT,
        )
        return fig

    mode_labels = T.get("mode_labels", {})
    # 비교할 수 있는 그룹만 그립니다. (몇 건 안 되는 그룹은 막대가 오해를 부릅니다)
    groups = [g for g in r.get("by_group", []) if g.get("comparable")]
    # 품번을 지정한 비교면 "RG3 (전체 합산)"처럼 어느 품번의 합산인지 밝힙니다.
    all_label = f"{r['part_code']} ({T['l_all']})" if r.get("part_code") else T["l_all"]
    x = [all_label] + [
        " · ".join(v for v in (g["part_code"], mode_labels.get(g["mode"], g["mode"] or "")) if v)
        for g in groups
    ]
    rows = [r["overall"]] + groups

    fig = go.Figure()
    for n in names:
        rates = [row[n]["defect_rate_pct"] for row in rows]
        fig.add_trace(go.Bar(
            x=x, y=rates, name=labels.get(n, n),
            marker=dict(color=colors[n], **BAR_MARKER_STYLE),
            text=["" if v is None else f"{v}%" for v in rates],
            textposition="outside", textfont=LABEL_FONT,
            customdata=[[row[n]["n_defect"], row[n]["total"]] for row in rows],
            hovertemplate="%{x}<br>%{y}% (%{customdata[0]} / %{customdata[1]:,})<extra></extra>",
        ))
    layout = {**CHART_BASE_LAYOUT, "margin": dict(l=10, r=10, t=80, b=10)}
    fig.update_layout(
        title=chart_title(T["t_shift"]),
        barmode="group",
        bargroupgap=0.15,
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=LABEL_FONT, bgcolor="rgba(0,0,0,0)"),
        xaxis=axis_style(showgrid=False, linecolor=COLOR_GRID),
        yaxis=axis_style(showgrid=True, gridcolor=COLOR_GRID, showline=False, ticksuffix="%"),
        **layout,
    )
    return fig


# ---------------------------------------------------------------------
# 답변 아래 차트 — '실제로 호출된 도구'를 보고 정합니다.
# 질문 문장을 비교하지 않으므로, 사용자가 직접 타이핑해도 차트가 나옵니다.
# ---------------------------------------------------------------------
def decide_charts(tool_log, data):
    """AI가 실제로 호출한 도구와 그 입력값을 보고 붙일 차트를 정합니다.

    [수정 P6]
    - 에러가 난 호출에는 차트를 붙이지 않습니다.
      (본문은 "확인하지 못했다"인데 아래에 금형온도 차트가 뜨던 모순)
    - AI가 분석한 품번·원인·조건 그대로 그립니다.
      (예전에는 AI가 무엇을 분석했든 항상 가스 → CN7 → 고속 차트를 그렸습니다)
    - tool_log 대신 옛 형식(도구 이름 문자열 목록)이 와도 동작합니다.
    """
    calls = [c if isinstance(c, dict) else {"name": c, "input": {}, "error": False}
             for c in (tool_log or [])]
    ok = [c for c in calls if not c.get("error")]
    used = {c["name"] for c in ok}
    spec = []

    # 현황 요약 질문은 보통 여러 도구를 한꺼번에 부릅니다 -> 대시보드 전체를 보여줍니다.
    # [수정 P7] list_part_codes 하나에 품번·불량률·좌우 정보가 다 들어있어서,
    # AI가 그 도구를 (get_recent_defects 등 다른 '현황' 도구와 함께, 또는 그
    # 도구 하나만으로) "지금 상황이 어때요?" 같은 요약 질문에 답을 끝내는
    # 경우가 있습니다. 처음엔 list_part_codes 단독 호출만 예외로 뒀는데, 실제
    # 배포본에서는 list_part_codes + get_recent_defects 조합처럼 요약 질문인데도
    # 두 조건 다 못 채우는 경우가 있어 "현재 상황 요약" 버튼을 눌러도 차트가
    # 하나도 안 뜨는 문제가 계속 있었습니다.
    # 그래서 기준을 이렇게 정리합니다: compare_normal_vs_defect나
    # get_operating_modes처럼 '특정 원인/조건을 콕 집어 분석'하는 도구를 쓰지
    # 않았다면, list_part_codes를 썼다는 것 자체가 이미 품번별 현황을 종합해서
    # 답했다는 뜻이므로 요약 질문으로 보고 대시보드를 보여줍니다.
    overview_tools = {"count_defects_by_reason", "list_part_codes",
                      "get_worst_day", "get_recent_defects"}
    narrow_tools = {"compare_normal_vs_defect", "get_operating_modes", "compare_shifts"}
    if not (used & narrow_tools) and (
        len(used & overview_tools) >= 2 or "list_part_codes" in used
    ):
        return [{"kind": "overview"}]

    # [주야간] 교대 비교를 했으면 교대별 차트를 가장 먼저 붙입니다.
    shift_call = next((c for c in ok if c["name"] == "compare_shifts"), None)
    if shift_call:
        spec.append({"kind": "shift",
                     "part_code": f._normalize_part(shift_call["input"].get("part_code"))})

    trend = next((c for c in ok if c["name"] == "get_worst_day"), None)
    if trend:
        spec.append({"kind": "trend", "days": trend["input"].get("days")})

    # AI가 품번을 지정해서 조건을 본 경우, 그 품번의 운전조건 차트
    mode_parts = []
    for c in ok:
        if c["name"] in ("compare_normal_vs_defect", "get_operating_modes"):
            pc = f._normalize_part(c["input"].get("part_code"))
            if pc and pc not in mode_parts:
                mode_parts.append(pc)

    # AI가 비교한 원인·품번·조건 중 실제로 차이가 나온 조합 하나만 비교 차트로 그립니다.
    analyzable = [p["part_code"] for p in f.list_part_codes(data)["parts"] if p["n_defect"] >= 5]
    for c in ok:
        if c["name"] != "compare_normal_vs_defect":
            continue
        reason = f._normalize_reason(c["input"].get("reason"), data)
        if not reason:
            continue  # 원인을 섞은 비교는 차트 한 장으로 그리지 않습니다
        part = f._normalize_part(c["input"].get("part_code"))
        mode = f._normalize_mode(c["input"].get("mode"))
        for p in ([part] if part else analyzable):
            for m in ([mode] if mode else ["고속", "저속", None]):
                r = f.compare_normal_vs_defect(data, reason, part_code=p, mode=m)
                if r.get("top_differences"):
                    spec.append({"kind": "mode", "part_code": p})
                    spec.append({"kind": "compare", "reason": reason,
                                 "part_code": p, "mode": m})
                    return spec

    if mode_parts:
        spec.append({"kind": "mode", "part_code": mode_parts[0]})
    return spec


def render_answer_charts(spec, data, T, key_prefix="chart"):
    """decide_charts가 만든 정보를 실제 차트로 그립니다.

    key_prefix: 이 답변(메시지)을 구분하는 고유값입니다. 채팅 기록이 쌓이면서
                같은 종류/같은 값의 차트가 여러 번 그려져도 서로 다른 요소로
                인식되도록, 호출하는 쪽(메시지 인덱스 등)에서 매번 다르게 넘겨줍니다.
    """
    if not spec:
        return

    if spec[0].get("kind") == "overview":
        render_kpi_row(data, T, key_prefix=f"{key_prefix}_kpi")
        daily = get_daily_defect_rate(data)
        render_chart_row([make_production_fig(daily, T), make_defect_rate_fig(daily, T)],
                          key_prefix=f"{key_prefix}_trend")
        render_chart_row([make_reason_fig(data, T),
                          make_part_fig(data, T),
                          make_side_fig(data, T)],
                          key_prefix=f"{key_prefix}_row")
        return

    figs = []
    for item in spec:
        kind = item.get("kind")
        if kind == "shift":
            figs.append(make_shift_fig(f.compare_shifts(data, item.get("part_code")), T))
        elif kind == "trend":
            figs.append(make_defect_rate_fig(get_daily_defect_rate(data), T,
                                             days=item.get("days")))
        elif kind == "mode":
            figs.append(make_mode_compare_fig(
                f.detect_operating_modes(data, item["part_code"]), T))
        elif kind == "compare":
            # 차트 제목에 "CN7 · High speed · Gas"처럼 무엇을 비교했는지 밝힙니다.
            ctx = " · ".join(x for x in (
                item["part_code"],
                T.get("mode_labels", {}).get(item.get("mode"), item.get("mode") or ""),
                T.get("reason_labels", {}).get(item["reason"], item["reason"]),
            ) if x)
            figs.append(make_variable_compare_fig(
                f.compare_normal_vs_defect(data, item["reason"],
                                           part_code=item["part_code"],
                                           mode=item.get("mode")), T, context=ctx))

    figs = [fig for fig in figs if fig is not None]
    if not figs:
        st.info(T["no_sample"])
        return
    if len(figs) == 1:
        render_chart_card(figs[0], key=f"{key_prefix}_single")
    else:
        render_chart_row(figs, key_prefix=key_prefix)


# ---------------------------------------------------------------------
# 답변 텍스트 렌더링 — 첫 문단(직답)을 크게 강조하고 나머지는 보조 설명으로.
# [디자인 수정] "한눈에 결과를 못 본다"는 피드백. 지금까지는 결론이든 배경
# 설명이든 전부 같은 크기 본문으로 쭉 나열돼서, 정작 궁금했던 답을 찾으려면
# 문단을 다 읽어야 했습니다. AI가 답변 맨 앞에 두는 짧은 직답 문장(예: "네,
# 11월 4일에 불량이 유독 많았습니다.")을 큼직한 강조 카드로 먼저 보여주고,
# 나머지 근거/디테일은 그 아래 원래 크기로 붙입니다.
# ---------------------------------------------------------------------
_MAX_HEADLINE_LEN = 160


def render_chat_answer(text):
    if not text:
        return
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    headline, rest = (paragraphs[0], paragraphs[1:]) if paragraphs else (None, [])

    # 첫 "문단"이 목록(-, *, 1.)이거나, 그 안에 줄바꿈이 섞여 있거나(헤더+하위
    # 불릿이 한 덩어리로 묶인 경우), 너무 길면 "직답 한 줄"이 아니라 이미 본문
    # 설명일 가능성이 높으므로, 강조하지 않고 원래 방식대로 통짜로 보여줍니다.
    is_list_like = bool(headline) and re.match(r"^\s*([-*]|\d+[.)])\s", headline)
    has_internal_break = bool(headline) and "\n" in headline.strip()
    if (not headline or not rest or is_list_like or has_internal_break
            or len(headline) > _MAX_HEADLINE_LEN):
        st.write(text)
        return

    headline_html = html.escape(headline.strip()).replace("**", "")
    st.markdown(
        f'<div style="font-size:1.1rem;font-weight:700;line-height:1.5;'
        f'color:#ffffff;background:rgba(57,135,229,0.12);'
        f'border-left:4px solid {COLOR_BLUE};border-radius:8px;'
        f'padding:12px 16px;margin-bottom:10px;">{headline_html}</div>',
        unsafe_allow_html=True,
    )
    st.write("\n\n".join(rest))


# ---------------------------------------------------------------------
# 예시 질문 버튼
# ---------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# 소개 영역(제목~기준일)과 예시 질문 사이에 구분선을 넣어서, 설명이 끝나고
# "이제부터는 실제로 써보는 영역"이라는 게 한눈에 구분되게 합니다.
st.divider()

st.write(T["examples"])
col1, col2, col3, col4 = st.columns(4)
example_clicked = None
if col1.button(T["b1"], disabled=is_generating):
    example_clicked = T["q1"]
if col2.button(T["b2"], disabled=is_generating):
    example_clicked = T["q2"]
if col3.button(T["b3"], disabled=is_generating):
    example_clicked = T["q3"]
if col4.button(T["b4"], disabled=is_generating):
    # 데이터로 답할 수 없는 질문임을 솔직하게 인정하는 모습을 보여주는 버튼입니다.
    example_clicked = T["q4"]

# 둘째 줄 — 미성형/RG3는 검증된 조치안이 없는 조합이라, '모른다'를 조치 제안
# 맥락에서 한 번 더 보여줄 수 있는 버튼입니다.
# "지금 공정 상황이 어때요?"는 전체 현황을 대시보드로 보여주는 질문입니다.
col5, col6 = st.columns(2)
if col5.button(T["b5"], disabled=is_generating):
    example_clicked = T["q5"]
if col6.button(T["b6"], disabled=is_generating):
    example_clicked = T["q6"]

user_input = st.chat_input(T["input"], disabled=is_generating) or example_clicked

# [지원님 작업] 질문이 들어오면 바로 답변 생성에 들어가지 않고, 우선 "생성 중" 상태만
# 표시해두고 한 번 다시 그립니다(st.rerun). 이렇게 하면 화면에 disabled=True가
# 반영된(회색으로 눌리지 않는) 언어 토글이 사용자에게 먼저 보이고, 그다음 실제
# 답변 생성이 시작됩니다. 그동안은 토글을 눌러도 반응하지 않으니, 답변이
# 중간에 날아가는 일이 없습니다.
if user_input and not is_generating:
    st.session_state.is_generating = True
    st.session_state.pending_question = user_input
    st.rerun()

# ---------------------------------------------------------------------
# 대화
# ---------------------------------------------------------------------
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        # [지원님 작업] 사용자 질문·AI 답변 둘 다 질문 당시 한국어·영어 버전을 함께
        # 저장해두고, 지금 켜진 언어 토글에 맞는 쪽을 골라서 보여줍니다. 이렇게 하면
        # 언어 버튼을 눌렀을 때 과거 대화(질문+답변) 전체가 바로 그 언어로 바뀌어
        # 보입니다. (구버전 세션에서 넘어온 메시지처럼 content_{lang}이 없을 때는
        # content로 대체합니다.)
        display_text = msg.get(f"content_{lang}", msg["content"])
        if msg["role"] == "assistant":
            render_chat_answer(display_text)
        else:
            st.write(display_text)
        if msg["role"] == "assistant":
            # 메시지 인덱스를 key_prefix로 넘겨서, 같은 차트가 다른 메시지에서
            # 반복돼도 고유한 key를 갖게 합니다.
            render_answer_charts(msg.get("charts"), df, T, key_prefix=f"msg{idx}")

# [지원님 작업] 실제 답변 생성은 여기서, pending_question이 있을 때만 진행합니다.
# 위쪽에서 이미 언어 토글·예시 버튼·업로드 등을 disabled 상태로 그린 뒤라
# 이 구간이 도는 동안 사용자가 그런 버튼을 눌러도 반응하지 않습니다.
pending_question = st.session_state.get("pending_question")
if pending_question:
    q = pending_question
    # 질문도 반대 언어로 미리 번역해서 같이 저장합니다.
    other_lang_q = "en" if lang == "ko" else "ko"
    translated_q = agent.translate_text(q, other_lang_q)
    q_content_ko = q if lang == "ko" else translated_q
    q_content_en = translated_q if lang == "ko" else q
    # content는 항상 한국어판 기준으로 저장해서, agent.ask에 넘어갈 history가
    # 시스템 프롬프트(한국어)와 일관된 맥락을 유지하게 합니다.
    st.session_state.messages.append({
        "role": "user",
        "content": q_content_ko,
        "content_ko": q_content_ko,
        "content_en": q_content_en,
    })
    with st.chat_message("user"):
        st.write(q)

    with st.chat_message("assistant"):
        with st.spinner(T["spinner"]):
            history = st.session_state.messages[:-1][-6:]
            tools_used, tool_log = [], []
            answer = agent.ask(q, df, history=history,
                               lang=lang, tools_used=tools_used, tool_log=tool_log)
            charts = decide_charts(tool_log, df)

            # [지원님 작업] 답변이 나오면, 반대 언어 버전도 바로 번역해서 같이
            # 만들어둡니다. (전체 도구 호출을 다시 하는 게 아니라 완성된 답변
            # 문장만 가볍게 번역하므로 API 호출이 1번 더 늘어나는 정도입니다.)
            other_lang = "en" if lang == "ko" else "ko"
            translated = agent.translate_text(answer, other_lang)
            content_ko = answer if lang == "ko" else translated
            content_en = translated if lang == "ko" else answer
        render_chat_answer(answer)
        # 이번 턴에 새로 나온 답변이므로, 아직 히스토리에 없는 고유한 key_prefix를 씁니다.
        render_answer_charts(charts, df, T, key_prefix="current")

    # content는 항상 한국어판을 기준으로 저장해서, 다음 질문의 history로 넘어갈 때도
    # 시스템 프롬프트(한국어)와 일관된 맥락을 유지하게 합니다.
    # content_ko / content_en은 화면 표시용으로, 언어 토글에 따라 골라서 보여줍니다.
    st.session_state.messages.append({
        "role": "assistant",
        "content": content_ko,
        "content_ko": content_ko,
        "content_en": content_en,
        "charts": charts,
    })

    # 답변이 끝났으니 "생성 중" 상태를 풀고, 화면을 다시 그려서
    # 언어 토글·버튼을 원래대로(누를 수 있게) 되돌립니다.
    st.session_state.pending_question = None
    st.session_state.is_generating = False
    st.rerun()