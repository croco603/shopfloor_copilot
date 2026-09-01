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

# ---------------------------------------------------------------------
# Claude에게 알려줄 '도구 목록'
# 이름(name)과 설명(description)이 Claude가 함수를 고르는 유일한 단서입니다.
# ---------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_worst_day",
        "description": (
            "날짜별 불량률을 계산해 불량이 가장 많았던 날을 찾는다. "
            "'이번 주에 불량 많았던 날 있었어?', '요즘 불량률 어때?' 같은 질문에 사용."
        ),
        "input_schema": {"type": "object", "properties": {}},
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
            "분석 가능한 품번 목록과 품번별 불량 건수를 알려준다. "
            "어떤 품번을 봐야 할지 판단할 때 먼저 호출한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "불량 원인(선택)."},
            },
        },
    },
    {
        "name": "check_answerable",
        "description": (
            "질문이 현재 데이터로 답변 가능한지(O), 조건부 가능한지(Δ), 불가능한지(X) 확인한다. "
            "다른 도구를 호출하기 전에, 특히 '왜~', '~하면 뭐가 달라져?' 류의 애매한 질문에는 "
            "먼저 이 도구로 답변 가능 여부부터 확인한다. "
            "question_tag는 새로 지어내지 말고 아래 등록된 태그 중 뜻이 가장 가까운 것을 "
            "그대로 사용한다 (완전히 새로운 주제일 때만 새 영어 태그를 만든다): "
            "gas_vs_normal(가스 불량 원인 비교), worst_day(불량 많았던 날), "
            "part_defect_rate(품번별 불량률), cycle_time_5_6(5vs6번 사이클타임 비교), "
            "day_vs_night(주간vs야간 불량 비교, '야간에 왜 불량이 많아' 류 질문은 반드시 이 태그), "
            "equipment_compare(설비 간 비교), predict_next_defect(다음 불량 예측)."
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

[되묻지 않기]
- 현장 작업자는 몰라서 물어본 것입니다. 사용자에게 원인을 되묻지 마세요.
  ("그날 무슨 일이 있었나요?", "설정을 바꾸셨나요?" 같은 질문 금지)
- 대신 도구를 더 호출해 직접 알아내거나, 다음에 무엇을 분석할지 제안하세요.
  예: "이어서 그날 불량의 원인을 분석해 드릴까요?"

[숫자 표기]
- 컬럼 영문명 대신 현장 용어를 쓰세요.
  Max_Injection_Speed=사출속도, Injection_Time=사출시간, Filling_Time=충전시간,
  Mold_Temperature_N=금형온도 N번, Barrel_Temperature_N=배럴온도 N번,
  Average_Screw_RPM=스크류 평균 회전수, Max_Back_Pressure=최대 배압,
  Cycle_Time=사이클타임, Plasticizing_Time=가소화시간
"""

# 함수 이름 -> 실제 파이썬 함수 매핑 (Claude가 고른 도구 이름으로 실제 함수를 찾기 위함)
FUNCTION_MAP = {
    "get_worst_day": lambda df, **kw: f.get_worst_day(df),
    "compare_normal_vs_defect": lambda df, **kw: f.compare_normal_vs_defect(
        df, kw["reason"], part_code=kw.get("part_code"), mode=kw.get("mode")),
    "get_operating_modes": lambda df, **kw: f.detect_operating_modes(df, kw["part_code"]),
    "suggest_action": lambda df, **kw: f.suggest_action(
        df, kw["reason"], part_code=kw.get("part_code")),
    "list_part_codes": lambda df, **kw: f.list_part_codes(df, kw.get("reason")),
    "check_answerable": lambda df, **kw: f.check_answerable(kw["question_tag"]),
}


def ask(question: str, df, history=None) -> str:
    """사용자 질문 하나를 받아 최종 답변 문자열을 반환합니다."""
    messages = (history or []) + [{"role": "user", "content": question}]

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    # Claude가 도구를 호출하고 싶어하면, 실제 함수를 실행하고 결과를 다시 넘겨줍니다.
    while response.stop_reason == "tool_use":
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
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
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    final_text = "".join(b.text for b in response.content if b.type == "text")
    return final_text


if __name__ == "__main__":
    df = f.load_data()
    print(ask("가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?", df))