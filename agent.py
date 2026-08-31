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
            "특정 불량 원인(가스/미성형/초기허용불량) 그룹과 정상 제품의 센서값을 비교해 "
            "차이가 큰 변수 순으로 보여준다. "
            "'가스 불량 났을 때 정상이랑 뭐가 달랐어?' 같은 원인 추적 질문에 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "불량 원인. '가스', '미성형', '초기허용불량' 중 하나.",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "suggest_action",
        "description": (
            "특정 불량 원인에 대해 조정해야 할 공정 조건과 우선 점검 대상 제품을 제안한다. "
            "'그럼 뭘 조정해야 해?', '뭐부터 점검해야 해?' 같은 조치 질문에 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
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
- 항상 도구(tool)를 통해 실제 데이터를 확인한 뒤 답변하세요. 데이터 없이 추측하지 마세요.
- 답할 수 없는 질문에는 반드시 다음 3가지를 포함해 답하세요:
  1) 답할 수 없다는 사실을 명시
  2) 왜 답할 수 없는지 데이터 근거 제시
  3) 대신 할 수 있는 것을 제안
- 현장 작업자가 이해하기 쉬운 말로, 전문 용어는 풀어서 설명하세요.
"""

# 함수 이름 -> 실제 파이썬 함수 매핑 (Claude가 고른 도구 이름으로 실제 함수를 찾기 위함)
FUNCTION_MAP = {
    "get_worst_day": lambda df, **kw: f.get_worst_day(df),
    "compare_normal_vs_defect": lambda df, **kw: f.compare_normal_vs_defect(df, kw["reason"]),
    "suggest_action": lambda df, **kw: f.suggest_action(df, kw["reason"]),
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
