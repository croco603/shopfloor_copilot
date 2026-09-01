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
# 주의: 일련번호(PART_FACT_SERIAL)처럼 공정과 무관한 숫자 컬럼은 절대 넣지 말 것.
#      숫자라서 계산은 되지만, "몇 번째로 생산된 제품인가"는 원인이 될 수 없음.
SENSOR_COLS = [
    "Injection_Time", "Filling_Time", "Plasticizing_Time", "Cycle_Time",
    "Clamp_Close_Time", "Cushion_Position", "Switch_Over_Position",
    "Plasticizing_Position", "Clamp_Open_Position", "Max_Injection_Speed",
    "Max_Screw_RPM", "Average_Screw_RPM", "Max_Injection_Pressure",
    "Max_Switch_Over_Pressure", "Max_Back_Pressure", "Average_Back_Pressure",
    "Barrel_Temperature_1", "Barrel_Temperature_2", "Barrel_Temperature_3",
    "Barrel_Temperature_4", "Barrel_Temperature_5", "Barrel_Temperature_6",
    "Barrel_Temperature_7", "Hopper_Temperature",
    "Mold_Temperature_1", "Mold_Temperature_2",
    "Mold_Temperature_3", "Mold_Temperature_4",
]

# 품번(PART_NAME)에서 앞부분 코드만 뽑아내기 위한 패턴
# 예: "CN7 W/S SIDE MLD'G RH" -> "CN7"
PART_CODE_PATTERN = r"^(CN7|RG3|SP2|JX1)"


def load_data() -> pd.DataFrame:
    """CSV를 불러와서 날짜 타입 등을 정리합니다.
    앱이 켜질 때 한 번만 불러오고 메모리에 캐싱해서 재사용하세요.
    (매 질문마다 다시 읽으면 느려집니다)
    """
    df = pd.read_csv(DATA_PATH)
    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"])
    df["date"] = df["TimeStamp"].dt.date
    # 품번 코드(CN7/RG3 등)를 미리 뽑아둡니다. 품번별 비교에 사용합니다.
    df["part_code"] = df["PART_NAME"].str.extract(PART_CODE_PATTERN)
    return df


def list_part_codes(df: pd.DataFrame, reason: str = None) -> dict:
    """분석에 쓸 수 있는 품번 목록과 각 품번의 불량 건수를 알려줍니다.
    agent가 '어떤 품번으로 비교할지' 정할 때 참고합니다.
    """
    rows = []
    for code, g in df.groupby("part_code"):
        n_defect = (g["Reason"] == reason).sum() if reason else (g["PassOrFail"] == "N").sum()
        rows.append({
            "part_code": code,
            "total": len(g),
            "n_defect": int(n_defect),
        })
    rows.sort(key=lambda r: r["n_defect"], reverse=True)
    return {"reason": reason, "parts": rows}


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
MIN_DEFECT_SAMPLES = 5  # 이보다 적으면 비교 자체를 하지 않습니다


def _compare_within(sub: pd.DataFrame, reason: str, top_n: int) -> dict:
    """하나의 품번 안에서만 불량군과 정상군을 비교하는 내부 함수."""
    normal = sub[sub["PassOrFail"] == "Y"]
    target = sub[sub["Reason"] == reason]

    if len(target) < MIN_DEFECT_SAMPLES:
        return {
            "n_defect": len(target),
            "skipped": True,
            "note": f"불량 표본이 {len(target)}건뿐이라 비교를 생략했습니다.",
        }

    rows = []
    for col in SENSOR_COLS:
        n_mean, n_std = normal[col].mean(), normal[col].std()
        t_mean = target[col].mean()
        if not n_std or n_std <= 0:
            continue  # 정상군 안에서 값이 전혀 변하지 않는 컬럼은 비교 의미가 없음
        rows.append({
            "variable": col,
            "normal_mean": round(n_mean, 2),
            "defect_mean": round(t_mean, 2),
            "z_score": round((t_mean - n_mean) / n_std, 2),
        })

    rows.sort(key=lambda r: abs(r["z_score"]), reverse=True)

    return {
        "n_defect": len(target),
        "n_normal": len(normal),
        "skipped": False,
        # 표본이 적으면 "확정"이 아니라 "우선 확인 대상"으로 말하게 하는 신호
        "low_sample_warning": len(target) < 20,
        "top_differences": rows[:top_n],
    }


def compare_normal_vs_defect(df: pd.DataFrame, reason: str,
                             part_code: str = None, top_n: int = 5) -> dict:
    """특정 불량 원인(reason) 그룹과 정상 그룹의 센서값을 비교합니다.

    ★ 반드시 '같은 품번 안에서' 비교합니다.
       품번이 다르면 금형과 설정값 자체가 달라서, 전체를 한꺼번에 비교하면
       "불량이라서 다른 것"과 "품번이라서 다른 것"이 뒤섞입니다.
       (실제로 이 데이터에서 사출속도는 CN7 55.5 / RG3 128.2로 두 배 넘게 다릅니다.
        섞어서 비교하면 사출속도가 원인인 것처럼 보이지만, 같은 품번 안에서는
        정상과 불량의 사출속도가 거의 같습니다.)

    part_code를 지정하지 않으면 품번별로 각각 따로 비교해서 모두 돌려줍니다.
    """
    if reason not in df["Reason"].dropna().unique():
        return {"error": f"'{reason}' 원인에 해당하는 데이터가 없습니다.", "n_defect": 0}

    if part_code:
        sub = df[df["part_code"] == part_code]
        if len(sub) == 0:
            return {"error": f"'{part_code}' 품번 데이터가 없습니다."}
        result = _compare_within(sub, reason, top_n)
        result.update({"reason": reason, "part_code": part_code,
                       "compared_within_part": True})
        return result

    # 품번 지정이 없으면 품번별로 나눠서 전부 비교
    by_part = {}
    for code, g in df.groupby("part_code"):
        by_part[code] = _compare_within(g, reason, top_n)

    return {
        "reason": reason,
        "compared_within_part": True,
        "note": ("품번마다 금형과 설정값이 달라 원인도 다를 수 있으므로 "
                 "품번별로 나누어 비교한 결과입니다. 품번을 뭉쳐서 비교하면 안 됩니다."),
        "by_part": by_part,
    }


# ---------------------------------------------------------------------
# STEP 3. 조치 제안 — "그럼 뭘 조정해야 해요?"
# ---------------------------------------------------------------------
# 원인별 조치 제안은 "데이터가 지목한 변수 + 공정 상식"을 결합해서 만듭니다.
# 완전 자동화하기보다, 팀이 검증한 조치 문구를 미리 정의해두고
# compare_normal_vs_defect() 결과의 상위 변수와 매칭하는 방식을 추천합니다.
ACTION_RULES = {
    ("가스", "CN7"): [
        "금형온도 3·4번 확인 — 불량 시 평균 25.1/27.7℃, 정상 22.1/23.5℃로 높았음",
        "금형온도가 오르는 원인(냉각수 유량, 연속 가동 시간) 점검",
    ],
    ("가스", "RG3"): [
        "스크류 평균 회전수 확인 — 불량 시 231, 정상 276으로 낮았음",
        "가소화가 충분히 이루어지는지 확인",
    ],
    ("미성형", "CN7"): [
        "사출속도 확인 — 불량 시 58.9, 정상 55.6으로 다소 높았음",
        "금형온도 3·4번도 함께 확인 (가스 불량과 유사한 패턴)",
    ],
    ("초기허용불량", "CN7"): [
        "초기 생산분 특성일 가능성 — 충전시간이 길고 사출속도가 낮음",
        "정상 조건 도달 전 생산분이므로 별도 관리 대상으로 분류 검토",
    ],
}


def suggest_action(df: pd.DataFrame, reason: str, part_code: str = None) -> dict:
    """원인별 조치안 + 품번별 불량률을 반환합니다.

    조치안은 반드시 (원인, 품번) 쌍으로 관리합니다.
    품번마다 원인이 다르기 때문에, 한 품번에서 얻은 조치를
    다른 품번에 그대로 적용하면 위험합니다.
    """
    part_rate = df.groupby("part_code").apply(
        lambda g: round((g["PassOrFail"] == "N").mean() * 100, 2)
    ).sort_values(ascending=False)

    if part_code:
        actions = ACTION_RULES.get((reason, part_code), [])
        return {
            "reason": reason,
            "part_code": part_code,
            "actions": actions,
            "has_verified_rule": len(actions) > 0,
            "part_defect_rate_pct": float(part_rate.get(part_code, 0)),
        }

    # 품번 지정이 없으면 품번별 조치안을 모두 반환
    by_part = {
        code: ACTION_RULES.get((reason, code), [])
        for code in part_rate.index
        if ACTION_RULES.get((reason, code))
    }
    return {
        "reason": reason,
        "note": "품번마다 원인이 다르므로 조치도 품번별로 다릅니다.",
        "actions_by_part": by_part,
        "part_defect_rate_table": part_rate.reset_index(
            name="fail_rate_pct"
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
    print(compare_normal_vs_defect(df, "가스", part_code="CN7")["top_differences"][:3])
    print("\n=== STEP3 테스트 ===")
    print(suggest_action(df, "가스", part_code="CN7"))
    print("\n=== STEP4 테스트 ===")
    print(check_answerable("day_vs_night"))