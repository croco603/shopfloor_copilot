"""
agent.py
--------
'안내데스크 직원' 역할입니다.
현장 작업자의 자연어 질문을 받아서:
  1) Claude에게 "어떤 함수를 부를지" 판단시키고 (tool use)
  2) functions.py의 진짜 함수를 실행하고
  3) 결과를 다시 Claude에게 넘겨서 사람이 이해하기 쉬운 답변으로 만들게 합니다.

초보자를 위한 포인트:
- Claude에게 함수를 '설명'하는 부분(tools 리스트)이 이 코드의 핵심입니다.
  설명이 애매하면 Claude가 엉뚱한 함수를 고를 수 있으니, 문서에 있는
  질문 예시 문구를 description에 그대로 넣어주는 게 정확도를 높이는 요령입니다.
"""

import json
import anthropic
from dotenv import load_dotenv
import functions as f


load_dotenv()
client = anthropic.Anthropic()  # API 키는 환경변수 ANTHROPIC_API_KEY 로 설정
MODEL = "claude-haiku-4-5-20251001"
# 답변에 표가 들어가면 1024로는 중간에 잘립니다.
# 잘린 답변(또는 빈 답변)이 대화 기록에 들어가면 다음 질문에서 API 오류가 납니다.
MAX_TOKENS = 4096

# ---------------------------------------------------------------------
# Claude에게 알려줄 '도구 목록'
# 이름(name)과 설명(description)이 Claude가 함수를 고르는 유일한 단서입니다.
# ---------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_worst_day",
        "description": (
            "날짜별 불량률을 계산해 불량이 가장 많았던 날을 찾는다. "
            "'이번 주에 불량 많았던 날 있었어?', '요즘 불량률 어때?', "
            "'최근에 불량이 늘어나는 추세야?' 같은 질문에 사용. "
            "데이터의 마지막 생산일을 '오늘'로 보고 계산한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": ("최근 며칠만 볼지. '이번 주'는 7, '최근 2주'는 14. "
                                    "생략하면 전체 기간."),
                },
            },
        },
    },
    {
        "name": "compare_normal_vs_defect",
        "description": (
            "특정 불량 원인(가스/미성형/초기허용불량) 그룹과 정상 제품의 센서값을 "
            "같은 품번 안에서 비교해, 차이가 큰 변수 순으로 보여준다. "
            "'가스 불량 났을 때 정상이랑 뭐가 달랐어?' 같은 원인 추적 질문에 사용. "
            "part_code를 지정하지 않으면 품번별 결과를 모두 돌려준다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "불량 원인. '가스', '미성형', '초기허용불량' 중 하나.",
                },
                "part_code": {
                    "type": "string",
                    "description": "품번 코드. 'CN7' 또는 'RG3'. 지정하지 않으면 전체 품번별 결과.",
                },
                "mode": {
                    "type": "string",
                    "description": (
                        "운전 조건. '저속' 또는 '고속'. 한 품번 안에서도 조건이 갈리는 경우에만 사용. "
                        "지정하지 않으면 조건별 결과를 모두 돌려준다."
                    ),
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "get_operating_modes",
        "description": (
            "한 품번 안에 서로 다른 운전 조건이 있는지 확인하고, 조건별 불량률을 알려준다. "
            "'CN7 불량 왜 나?', '조건별로 차이 있어?' 같은 질문이나, "
            "원인 분석 전에 조건이 갈리는지 확인할 때 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "part_code": {"type": "string", "description": "품번 코드. 'CN7' 또는 'RG3'."},
            },
            "required": ["part_code"],
        },
    },
    {
        "name": "suggest_action",
        "description": (
            "특정 불량 원인에 대해 조정해야 할 공정 조건을 제안한다. "
            "'그럼 뭘 조정해야 해?', '뭐부터 점검해야 해?' 같은 조치 질문에 사용. "
            "조치는 품번마다 다르므로 가능하면 part_code를 함께 넘긴다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "part_code": {
                    "type": "string",
                    "description": "품번 코드. 'CN7' 또는 'RG3'.",
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "list_part_codes",
        "description": (
            "분석 가능한 품번 목록과 품번별 불량 건수·불량률을 알려준다. "
            "'불량 줄이려면 뭘 먼저 봐야 해?', '어떤 품번을 봐야 할지' 판단할 때 먼저 호출한다. "
            "결과는 defect_rate_pct(불량률) 기준으로 정렬되어 있다. "
            "n_defect(건수)만 보고 우선순위를 말하지 마라 — 생산량이 많은 품번은 "
            "불량률이 낮아도 건수만 많아 보일 수 있다. 반드시 defect_rate_pct 기준으로 답하라. "
            "결과의 by_side에는 좌우(LH/RH)별 불량률이 들어 있어, "
            "'LH랑 RH 중 어디가 불량이 많아?' 질문에도 이 도구로 답할 수 있다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "불량 원인(선택)."},
            },
        },
    },
    {
        "name": "count_defects_by_reason",
        "description": (
            "불량 원인(가스/미성형/초기허용불량)별 건수와 비중을 센다. "
            "'가스랑 미성형 중에 뭐가 더 자주 나?', '불량 원인 중에 뭐가 제일 비중이 커?' "
            "같은 질문에 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "part_code": {"type": "string", "description": "품번 코드(선택). 'CN7' 또는 'RG3'."},
            },
        },
    },
    {
        "name": "get_recent_defects",
        "description": (
            "가장 최근에 발생한 불량을 한 건씩 조회한다. 각 건마다 같은 품번·같은 운전 조건의 "
            "정상 제품과 비교해 크게 벗어난 값을 함께 돌려준다. "
            "'최근 불량 5건 원인 알려줘', '방금 난 불량 왜 그래?' 같은 질문에 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "조회할 건수. 기본 5건."},
            },
        },
    },
    {
        "name": "check_variable",
        "description": (
            "특정 값 하나가 불량과 관계있는지만 콕 집어 확인한다. "
            "'금형온도가 불량이랑 관계있어?', '사출압력이 영향을 미쳐?', "
            "'지금 배럴온도 설정 괜찮아?'처럼 값을 지정한 질문에는 "
            "compare_normal_vs_defect 대신 반드시 이 도구를 사용한다. "
            "(compare_normal_vs_defect는 상위 몇 개만 돌려주므로, 지정한 값이 "
            "목록에 없으면 답할 수 없다.) "
            "part_code를 생략하면 불량이 있는 모든 품번을 자동으로 계산하므로, "
            "사용자에게 품번을 되묻지 말고 그냥 호출하라. "
            "해당 품번에 운전 조건(저속/고속)이 있는데 mode를 지정하지 않으면 "
            "자동으로 저속/고속을 나눠 by_mode로 돌려준다 — 이때 두 조건의 "
            "결과가 다를 수 있으므로 반드시 조건별로 나누어 답하라."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "variable": {
                    "type": "string",
                    "description": ("확인할 값의 현장 용어. 사출속도, 사출시간, 충전시간, 사출압력, "
                                    "보압, 배압, 금형온도, 배럴온도, 호퍼온도, 스크류회전수, "
                                    "사이클타임, 가소화시간, 쿠션위치, 형체시간 중 하나."),
                },
                "reason": {"type": "string", "description": "불량 원인(선택). 생략하면 전체 불량 대상."},
                "part_code": {
                    "type": "string",
                    "description": ("품번 코드. 'CN7' 또는 'RG3'. 생략하면 불량이 있는 "
                                    "모든 품번을 자동으로 계산한다. 사용자에게 품번을 되묻지 말 것."),
                },
                "mode": {"type": "string", "description": "운전 조건(선택). '저속' 또는 '고속'."},
            },
            "required": ["variable"],
        },
    },
    {
        "name": "check_answerable",
        "description": (
            "질문이 현재 데이터로 답변 가능한지(O), 조건부 가능한지(Δ), 불가능한지(X) 확인한다. "
            "다른 도구를 호출하기 전에, 특히 '왜~', '~하면 뭐가 달라져?' 류의 애매한 질문에는 "
            "먼저 이 도구로 답변 가능 여부부터 확인한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question_tag": {
                    "type": "string",
                    "description": "질문을 대표하는 짧은 영어 태그. 예: day_vs_night, equipment_compare",
                }
            },
            "required": ["question_tag"],
        },
    },
]

SYSTEM_PROMPT = """\
당신은 사출성형 공정 현장 작업자를 돕는 'ShopFloor Copilot'입니다.

[기본 원칙]
- 항상 도구(tool)를 통해 실제 데이터를 확인한 뒤 답변하세요. 데이터 없이 추측하지 마세요.
- 답할 수 없는 질문에는 반드시 다음 3가지를 포함해 답하세요:
  1) 답할 수 없다는 사실을 명시
  2) 왜 답할 수 없는지 데이터 근거 제시
  3) 대신 할 수 있는 것을 제안
- 현장 작업자가 이해하기 쉬운 말로, 전문 용어는 풀어서 설명하세요.

[품번 원칙 — 가장 중요]
- 이 공장은 품번마다 금형과 설정값이 다릅니다. 원인도 품번마다 다릅니다.
- 원인이나 조치를 말할 때는 반드시 어느 품번인지 함께 밝히세요.
- 한 품번에서 나온 결론을 다른 품번에 적용하지 마세요.
- 여러 품번의 값을 평균 내어 "목표값"으로 제시하지 마세요. 어느 품번에도 맞지 않습니다.

[운전 조건 원칙 — 품번 다음으로 중요]
- 같은 품번 안에서도 서로 다른 조건으로 돌리는 경우가 있습니다.
  예: CN7의 스크류 회전수는 29 아니면 292이고, 평균 124.7은 존재하지 않는 값입니다.
- 조건이 갈리는 품번은 조건별로 나누어 말하세요. 조건별 불량률 차이를 먼저 알려주세요.
- 실제 사례: CN7 고속 조건 1.50% vs 저속 조건 0.05%로 30배 차이납니다.

[표본이 적을 때]
- low_sample_warning이 true이면 "원인입니다"라고 단정하지 말고
  "우선 확인해볼 값입니다"처럼 표현하고, 몇 건 기준인지 함께 밝히세요.
- 표본 건수를 스스로 "충분하다"고 평가하지 마세요. 건수만 사실대로 밝히세요.

[할 수 없는 것을 제안하지 않기 — 매우 중요]
- 답할 수 없다고 말한 뒤에, 도구 목록에 없는 분석을 대안으로 제시하지 마세요.
  못 하는 것을 할 수 있다고 광고하는 셈이며, 다음 질문에서 바로 들통납니다.
- 대안을 제시할 때는 반드시 지금 가진 도구로 실제 실행 가능한 것만 말하세요.
- 특히 주야간 비교, 교대조 비교, 불량 확률 예측, 원료 로트 분석은
  이 데이터로 불가능합니다. 절대 제안하지 마세요.
- suggest_action이 has_verified_rule=false를 돌려주면, 검증된 조치안이 없다는 사실을
  밝히고 "확인해볼 값"만 제시하세요. 조치를 지어내지 마세요.

[되묻지 않기 — 자주 어기는 규칙이니 특히 주의]
- 현장 작업자는 몰라서 물어본 것입니다. 사용자에게 되묻지 마세요.
- 특히 다음은 절대 묻지 마세요. 도구가 알아서 처리하거나, 도구로 확인하면 됩니다.
  · "어느 품번인가요?" → part_code를 비우고 호출하면 전체 품번이 나옵니다.
  · "어떤 불량인가요?" → count_defects_by_reason으로 확인하거나 전체로 답하세요.
  · "둘 다 확인해드릴까요?" → 묻지 말고 둘 다 확인해서 답하세요.
  · "확인해 보실까요?" → 묻지 말고 확인해서 결과를 주세요.
  · "그날 무슨 일이 있었나요?", "설정을 바꾸셨나요?" → 사용자가 아는 정보가 아닙니다.
- 답을 다 준 뒤에 "다음으로 무엇을 분석할까요?"라고 제안하는 것은 괜찮습니다.
  하지만 답을 주기 전에 정보를 요구하는 것은 안 됩니다.

[LH/RH 질문]
- list_part_codes 결과의 by_side에 좌우별 불량률이 들어 있습니다.
  "LH랑 RH 중 어디가 불량이 많아?"는 이 값으로 답하세요.

[값을 지정한 질문]
- "금형온도가 관계있어?"처럼 특정 값을 지목한 질문에는 반드시 check_variable을 쓰세요.
  compare_normal_vs_defect는 상위 몇 개만 돌려주므로 그 값이 없을 수 있습니다.
- "몇 도 이상/이하면 위험해요?"처럼 구체적인 임계값(숫자 하나)을 묻는 질문에는,
  check_variable 결과의 normal_range와 defect_range를 함께 확인하세요.
  ranges_overlap이 true이면 두 범위가 겹친다는 뜻이므로, "OO도 이상이면 위험"처럼
  단정적인 숫자를 만들어내지 마세요. 대신 "평균적으로 정상보다 높게/낮게 나타나는
  경향이 있습니다" 정도로 답하고, 정상군도 그 값까지 나온 적이 있다는 사실을 함께 밝히세요.

[답변 길이]
- 핵심 3가지 이내로 간결하게 쓰세요. 이모지는 쓰지 않습니다.
- 표로 보여줄 수 있는 것은 표로 정리하세요.

[숫자 표기]
- 컬럼 영문명 대신 현장 용어를 쓰세요.
  Max_Injection_Speed=사출속도, Injection_Time=사출시간, Filling_Time=충전시간,
  Mold_Temperature_N=금형온도 N번, Barrel_Temperature_N=배럴온도 N번,
  Average_Screw_RPM=스크류 평균 회전수, Max_Back_Pressure=최대 배압,
  Cycle_Time=사이클타임, Plasticizing_Time=가소화시간
"""

# 답변 언어를 정하는 규칙. app.py의 언어 토글에서 lang을 넘겨받습니다.
# 시스템 프롬프트 뒤에 덧붙이는 방식이라, 위의 모든 원칙은 그대로 적용됩니다.
LANG_RULE = {
    "ko": "",
    "en": (
        "\n\n[Language]\n"
        "Answer in English. All rules above still apply.\n"
        "Use these field terms: mold temperature, barrel temperature, hopper temperature,\n"
        "injection speed, injection time, filling time, plasticizing time,\n"
        "screw RPM, back pressure, holding pressure, cycle time, cushion position.\n"
        "Keep defect reason names as: gas, short shot (미성형), initial tolerance defect (초기허용불량).\n"
        "Part codes (CN7, RG3) and operating modes stay as they are, but translate\n"
        "'저속' as 'low-speed' and '고속' as 'high-speed'."
    ),
}

# 함수 이름 -> 실제 파이썬 함수 매핑 (Claude가 고른 도구 이름으로 실제 함수를 찾기 위함)
FUNCTION_MAP = {
    "get_worst_day": lambda df, **kw: f.get_worst_day(df, days=kw.get("days")),
    "compare_normal_vs_defect": lambda df, **kw: f.compare_normal_vs_defect(
        df, kw["reason"], part_code=kw.get("part_code"), mode=kw.get("mode")),
    "get_operating_modes": lambda df, **kw: f.detect_operating_modes(df, kw["part_code"]),
    "suggest_action": lambda df, **kw: f.suggest_action(
        df, kw["reason"], part_code=kw.get("part_code")),
    "list_part_codes": lambda df, **kw: f.list_part_codes(df, kw.get("reason")),
    "count_defects_by_reason": lambda df, **kw: f.count_defects_by_reason(
        df, part_code=kw.get("part_code")),
    "get_recent_defects": lambda df, **kw: f.get_recent_defects(df, n=kw.get("n", 5)),
    "check_variable": lambda df, **kw: f.check_variable(
        df, kw["variable"], reason=kw.get("reason"),
        part_code=kw.get("part_code"), mode=kw.get("mode")),
    "check_answerable": lambda df, **kw: f.check_answerable(kw["question_tag"]),
}


def ask(question: str, df, history=None, lang: str = "ko", tools_used=None) -> str:
    """사용자 질문 하나를 받아 최종 답변 문자열을 반환합니다.

    lang       : 'ko' 또는 'en'. 답변 언어를 정합니다.
    tools_used : 리스트를 넘기면, 이번 답변에서 실제로 호출된 도구 이름이 담깁니다.
                 app.py가 "어떤 그래프를 그릴지" 판단할 때 씁니다.
                 (질문 문자열을 비교하는 방식은 사용자가 직접 타이핑하면 빗나갑니다.)
    """
    system = SYSTEM_PROMPT + LANG_RULE.get(lang, "")

    # history는 app.py의 st.session_state.messages에서 그대로 넘어옵니다.
    # app.py가 화면 표시용으로 role/content 외의 필드(예: show_chart 같은 UI 상태값)를
    # 같이 저장해도, Claude API는 role/content 외의 필드를 절대 허용하지 않습니다.
    # 여기서 role/content만 남기고 나머지는 걸러내야 API 호출이 깨지지 않습니다.
    # 내용이 빈 메시지도 API가 거부하므로 함께 걸러냅니다.
    clean_history = [
        {"role": h["role"], "content": h["content"]}
        for h in (history or [])
        if str(h.get("content", "")).strip()
    ]
    messages = clean_history + [{"role": "user", "content": question}]

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=TOOLS,
        messages=messages,
    )

    # Claude가 도구를 호출하고 싶어하면, 실제 함수를 실행하고 결과를 다시 넘겨줍니다.
    while response.stop_reason == "tool_use":
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            if tools_used is not None:
                tools_used.append(block.name)   # 어떤 도구를 썼는지 app.py에 알려줍니다
            func = FUNCTION_MAP.get(block.name)
            if func is None:
                result = {"error": f"알 수 없는 도구: {block.name}"}
            else:
                result = func(df, **block.input)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

    final_text = "".join(b.text for b in response.content if b.type == "text")
    # 답변이 비어 있으면 그대로 대화 기록에 저장되어 다음 질문에서 API 오류를 냅니다.
    if not final_text.strip():
        return ("답변을 만들지 못했습니다. 질문을 조금 더 구체적으로 해주시겠어요?"
                if lang == "ko" else
                "I couldn't generate an answer. Could you make the question more specific?")
    return final_text


if __name__ == "__main__":
    df = f.load_data()
    print(ask("가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?", df))