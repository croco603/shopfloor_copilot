"""
functions.py
------------
'참고자료 캐비닛' 역할을 하는 파일입니다.
STEP 1~4 데모 시나리오에 필요한 계산을 각각 하나의 함수로 만들어뒀습니다.
Claude(에이전트)는 이 함수들을 '도구(tool)'로 호출해서 답을 만듭니다.

초보자를 위한 설계 원칙:
1. 함수 하나 = 질문 하나. 여러 질문을 한 함수에 억지로 몰아넣지 않습니다.
2. 함수는 '숫자/표'만 반환합니다. 사람 말로 풀어 설명하는 건 이 함수의 역할이 아니고,
   그건 agent.py에서 Claude가 담당합니다. (역할을 섞으면 나중에 디버깅이 어려워져요)
3. 모든 함수는 실패해도 앱이 죽지 않도록 dict 형태로 결과를 반환합니다.
"""

import pandas as pd

DATA_PATH = "labeled_data.csv"

# 사용할 센서 컬럼들 (전처리된 45개 컬럼 중 분석에 쓰는 것들)
SENSOR_COLS = [
    "Injection_Time", "Filling_Time", "Plasticizing_Time", "Cycle_Time",
    "Clamp_Close_Time", "Cushion_Position", "Switch_Over_Position",
    "Plasticizing_Position", "Clamp_Open_Position", "Max_Injection_Speed",
    "Max_Screw_RPM", "Average_Screw_RPM", "Max_Injection_Pressure",
    "Max_Switch_Over_Pressure", "Max_Back_Pressure", "Average_Back_Pressure",
    "Barrel_Temperature_1", "Barrel_Temperature_2", "Barrel_Temperature_3",
    "Barrel_Temperature_4", "Barrel_Temperature_5", "Barrel_Temperature_6",
    "Barrel_Temperature_7", "Hopper_Temperature",
    "Mold_Temperature_3", "Mold_Temperature_4",
]


def load_data() -> pd.DataFrame:
    """CSV를 불러와서 날짜 타입 등을 정리합니다.
    앱이 켜질 때 한 번만 불러오고 메모리에 캐싱해서 재사용하세요.
    (매 질문마다 다시 읽으면 느려집니다)
    """
    df = pd.read_csv(DATA_PATH)
    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"])
    df["date"] = df["TimeStamp"].dt.date
    return df


# ---------------------------------------------------------------------
# STEP 1. 현황 파악 — "이번 주에 불량 유독 많았던 날 있었어요?"
# ---------------------------------------------------------------------
def get_worst_day(df: pd.DataFrame, top_n: int = 5) -> dict:
    """날짜별 불량률을 계산해서 가장 안 좋았던 날을 찾습니다."""
    daily = df.groupby("date")["PassOrFail"].agg(
        total="count",
        fail=lambda x: (x == "N").sum(),
    )
    daily["fail_rate_pct"] = (daily["fail"] / daily["total"] * 100).round(2)
    daily = daily.sort_values("fail_rate_pct", ascending=False)

    top = daily.head(top_n).reset_index()
    return {
        "worst_date": str(top.iloc[0]["date"]) if len(top) else None,
        "worst_fail_rate_pct": float(top.iloc[0]["fail_rate_pct"]) if len(top) else None,
        "table": top.to_dict(orient="records"),
    }


# ---------------------------------------------------------------------
# STEP 2. 원인 추적 (★핵심) — "가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?"
# ---------------------------------------------------------------------
def compare_normal_vs_defect(df: pd.DataFrame, reason: str, top_n: int = 8) -> dict:
    """특정 불량 원인(reason) 그룹과 정상 그룹의 센서값을 비교합니다.
    z-score(정상군 표준편차 대비 몇 배 벗어났는지)로 정렬해서
    '차이가 큰 순서'로 변수를 보여줍니다.
    """
    normal = df[df["PassOrFail"] == "Y"]
    target = df[df["Reason"] == reason]

    if len(target) == 0:
        return {"error": f"'{reason}' 원인에 해당하는 데이터가 없습니다.", "n_samples": 0}

    rows = []
    for col in SENSOR_COLS:
        n_mean, n_std = normal[col].mean(), normal[col].std()
        t_mean = target[col].mean()
        z = (t_mean - n_mean) / n_std if n_std and n_std > 0 else None
        rows.append({
            "variable": col,
            "normal_mean": round(n_mean, 2),
            "defect_mean": round(t_mean, 2),
            "z_score": round(z, 2) if z is not None else None,
        })

    rows.sort(key=lambda r: abs(r["z_score"]) if r["z_score"] is not None else 0, reverse=True)

    return {
        "reason": reason,
        "n_samples": len(target),
        # 표본이 20건 이하면 "참고용" 수준이라는 걸 answerability_check에서 같이 처리합니다.
        "low_sample_warning": len(target) <= 20,
        "top_differences": rows[:top_n],
    }


# ---------------------------------------------------------------------
# STEP 3. 조치 제안 — "그럼 뭘 조정해야 해요?"
# ---------------------------------------------------------------------
# 원인별 조치 제안은 "데이터가 지목한 변수 + 공정 상식"을 결합해서 만듭니다.
# 완전 자동화하기보다, 팀이 검증한 조치 문구를 미리 정의해두고
# compare_normal_vs_defect() 결과의 상위 변수와 매칭하는 방식을 추천합니다.
ACTION_RULES = {
    "가스": [
        "사출속도(Max_Injection_Speed)를 정상 생산 구간 수준으로 하향 검토",
        "충전시간(Filling_Time)이 충분히 확보되는지 확인",
    ],
    "미성형": [
        "사출속도/충전시간 조건이 가스 불량과 동일 패턴 → 같은 원인일 가능성 우선 점검",
        "동일 시간대 설비 이상 여부(로그) 확인",
    ],
}


def suggest_action(df: pd.DataFrame, reason: str) -> dict:
    """원인별 조치안 + 우선 점검 대상(PART_NAME별 불량률)을 함께 반환합니다."""
    actions = ACTION_RULES.get(reason, [])

    part_rate = df.groupby("PART_NAME")["PassOrFail"].apply(
        lambda x: round((x == "N").mean() * 100, 2)
    ).sort_values(ascending=False)

    return {
        "reason": reason,
        "actions": actions,
        "priority_check_part": part_rate.index[0] if len(part_rate) else None,
        "part_defect_rate_table": part_rate.reset_index().rename(
            columns={"PassOrFail": "fail_rate_pct"}
        ).to_dict(orient="records"),
    }


# ---------------------------------------------------------------------
# STEP 4. "모른다" 판별 로직 — 심사에서 가장 중요한 부분
# ---------------------------------------------------------------------
# 문서의 21개 질문 O/△/X 분류를 여기에 그대로 옮겨 담습니다.
# 실제 서비스에서는 이 dict를 문서 3장의 표 내용으로 채워 넣으세요.
# key: 질문을 대표하는 짧은 태그, value: (상태, 사유)
QUESTION_CATALOG = {
    "gas_vs_normal": ("O", None),
    "worst_day": ("O", None),
    "part_defect_rate": ("O", None),
    "cycle_time_5_6": ("Δ", "샘플 20건뿐이고 사이클타임 차이가 0.8초에 그쳐 유의미하다고 보기 어렵습니다."),
    "day_vs_night": ("X", "전체의 98.6%가 야간(20시~08시) 생산분이라 주야간 비교가 불가능합니다."),
    "equipment_compare": ("X", "설비가 사실상 1대입니다 (7,996건 중 7,992건이 동일 설비)."),
    "predict_next_defect": ("X", "불량이 전체의 0.89%(71건)뿐이라 예측 모델 학습이 불가능합니다."),
    # ... 문서에 정리된 나머지 질문들을 이어서 채워 넣으세요.
}


def check_answerable(question_tag: str) -> dict:
    """질문 태그를 보고 O/Δ/X 여부와 사유를 반환합니다.
    Δ, X인 경우 agent.py에서 아래 3원칙을 적용해 답변을 만듭니다.
      1) 답할 수 없다는 사실을 명시한다
      2) 왜 답할 수 없는지 데이터 근거를 든다
      3) 대신 할 수 있는 것을 제안한다
    """
    status, reason = QUESTION_CATALOG.get(question_tag, ("UNKNOWN", "카탈로그에 없는 질문 태그입니다."))
    return {"question_tag": question_tag, "status": status, "reason": reason}


if __name__ == "__main__":
    # 간단한 동작 확인용 (터미널에서 python functions.py 로 실행)
    df = load_data()
    print("=== STEP1 테스트 ===")
    print(get_worst_day(df))
    print("\n=== STEP2 테스트 ===")
    print(compare_normal_vs_defect(df, "가스")["top_differences"][:3])
    print("\n=== STEP3 테스트 ===")
    print(suggest_action(df, "가스"))
    print("\n=== STEP4 테스트 ===")
    print(check_answerable("day_vs_night"))
