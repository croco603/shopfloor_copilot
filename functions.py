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

# 업로드된 데이터가 이 앱에서 쓰일 수 있으려면 반드시 있어야 하는 컬럼들
REQUIRED_COLUMNS = ["TimeStamp", "PassOrFail", "Reason", "PART_NAME"] + SENSOR_COLS


def validate_columns(df: pd.DataFrame) -> list:
    """업로드된 데이터에 우리 앱이 꼭 필요로 하는 컬럼이 다 있는지 확인합니다.
    빠진 컬럼 목록을 돌려줍니다. 빈 리스트면 문제없다는 뜻입니다.
    """
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def load_data(source=None) -> pd.DataFrame:
    """CSV를 불러와서 날짜 타입 등을 정리합니다.
    source가 없으면 기본 데이터(labeled_data.csv)를 불러오고,
    source에 파일이 들어오면(업로드된 파일 등) 그걸 대신 불러옵니다.
    앱이 켜질 때 한 번만 불러오고 메모리에 캐싱해서 재사용하세요.
    (매 질문마다 다시 읽으면 느려집니다)
    """
    df = pd.read_csv(source if source is not None else DATA_PATH)
    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"])
    df["date"] = df["TimeStamp"].dt.date
    # 품번 코드(CN7/RG3 등)를 미리 뽑아둡니다. 품번별 비교에 사용합니다.
    df["part_code"] = df["PART_NAME"].str.extract(PART_CODE_PATTERN)
    return df


def list_part_codes(df: pd.DataFrame, reason: str = None) -> dict:
    """분석에 쓸 수 있는 품번 목록과 각 품번의 불량 건수·불량률을 알려줍니다.
    agent가 '어떤 품번으로 비교할지' 정할 때 참고합니다.
    """
    rows = []
    for code, g in df.groupby("part_code"):
        n_defect = (g["Reason"] == reason).sum() if reason else (g["PassOrFail"] == "N").sum()
        total = len(g)
        rows.append({
            "part_code": code,
            "total": total,
            "n_defect": int(n_defect),
            # 건수만 보면 생산량이 많은 품번이 항상 1위로 보입니다.
            # (예: CN7은 불량 39건, RG3는 32건이지만, 불량률은 RG3가 2.55%로
            #  CN7 0.58%보다 4배 이상 높습니다. 생산량이 6,736 vs 1,256이라
            #  건수만 비교하면 반대로 읽힙니다.)
            # 그래서 "먼저 봐야 할 품번"은 건수가 아니라 불량률로 정렬합니다.
            "defect_rate_pct": round(n_defect / total * 100, 2) if total else 0.0,
        })
    rows.sort(key=lambda r: r["defect_rate_pct"], reverse=True)
    return {
        "reason": reason,
        "parts": rows,
        "note": ("defect_rate_pct(불량률) 기준으로 정렬했습니다. n_defect(건수)만 보고 "
                 "우선순위를 판단하지 마세요 — 생산량이 많은 품번은 건수만 많아 보일 수 있습니다."),
    }


# ---------------------------------------------------------------------
# STEP 1. 현황 파악 — "이번 주에 불량 유독 많았던 날 있었어요?"
# ---------------------------------------------------------------------
def get_worst_day(df: pd.DataFrame, days: int = None, top_n: int = 5) -> dict:
    """날짜별 불량률을 계산해서 가장 안 좋았던 날을 찾습니다.

    days를 주면 데이터의 마지막 날을 '오늘'로 보고 최근 N일만 봅니다.
    "이번 주"는 days=7, "최근 2주"는 days=14로 해석하면 됩니다.
    days를 생략하면 전체 기간을 봅니다.
    """
    reference_date = df["date"].max()   # 이 데이터에서의 '오늘'
    scope = df

    if days:
        cutoff = pd.Timestamp(reference_date) - pd.Timedelta(days=days - 1)
        scope = df[df["date"] >= cutoff.date()]
        if len(scope) == 0:
            return {"error": f"최근 {days}일 안에 생산 기록이 없습니다.",
                    "reference_date": str(reference_date)}

    daily = scope.groupby("date")["PassOrFail"].agg(
        total="count",
        fail=lambda x: (x == "N").sum(),
    )
    daily["fail_rate_pct"] = (daily["fail"] / daily["total"] * 100).round(2)
    daily = daily.sort_values("fail_rate_pct", ascending=False)

    top = daily.head(top_n).reset_index()
    worst_date = str(top.iloc[0]["date"]) if len(top) else None

    # 그날 무엇을 어떤 조건으로 생산했는지 함께 알려줍니다.
    # (불량률이 높은 날은 특정 품번·조건만 돌린 날인 경우가 많습니다.)
    context = []
    if worst_date:
        that_day = df[df["date"].astype(str) == worst_date]
        for pc, g in that_day.groupby("part_code"):
            entry = {"part_code": pc, "count": len(g)}
            info = detect_operating_modes(df, pc)
            if info.get("has_modes"):
                col, thr = info["split_variable"], info["threshold"]
                n_low = int((g[col] < thr).sum())
                entry["mode_mix"] = {"저속": n_low, "고속": len(g) - n_low}
            context.append(entry)

    return {
        "reference_date": str(reference_date),
        "period": (f"최근 {days}일 ({scope['date'].min()} ~ {reference_date})"
                   if days else f"전체 기간 ({df['date'].min()} ~ {reference_date})"),
        "days_with_production": int(scope["date"].nunique()),
        "worst_date": worst_date,
        "worst_fail_rate_pct": float(top.iloc[0]["fail_rate_pct"]) if len(top) else None,
        "worst_day_production": context,
        "hint": ("이 데이터의 마지막 생산일은 " + str(reference_date) + "입니다. "
                 "'오늘'이나 '이번 주'는 이 날짜를 기준으로 해석하며, 답변할 때 "
                 "기준일을 함께 밝히세요. 불량률이 높은 날은 특정 품번이나 운전 조건만 "
                 "돌린 날일 수 있으니 worst_day_production을 확인하세요."),
        "table": top.to_dict(orient="records"),
    }


# ---------------------------------------------------------------------
# STEP 2. 원인 추적 (★핵심) — "가스 불량 났을 때 정상 제품이랑 뭐가 제일 달랐어요?"
# ---------------------------------------------------------------------
MIN_DEFECT_SAMPLES = 5   # 이보다 적으면 비교 자체를 하지 않습니다
LOW_SAMPLE_LIMIT = 30    # 이보다 적으면 "확정"이 아니라 "우선 확인 대상"으로 말합니다
MIN_PCT_DIFF = 2.0       # 정상값 대비 이보다 작게 차이나면 현장에서 의미 없다고 봅니다
MIN_ABS_Z = 0.5          # 표준편차 대비 이보다 작게 움직였으면 차이로 보지 않습니다


# ---------------------------------------------------------------------
# 운전 조건 감지 — "평균의 함정"을 피하기 위한 장치
# ---------------------------------------------------------------------
# 같은 품번이라도 서로 다른 조건으로 돌리는 경우가 있습니다.
# 예: CN7의 스크류 회전수는 29 아니면 292로만 나오고, 그 사이 값이 없습니다.
#     이때 평균 124.7은 실제로 존재하지 않는 값이라 비교 기준이 될 수 없습니다.
#     (실제로 이 두 조건의 불량률은 0.05% vs 1.50%로 30배 차이납니다.)
MIN_MODE_RATIO = 0.03   # 한쪽 조건이 전체의 3% 이상이면 별개 조건으로 봅니다
MIN_MODE_COUNT = 30     # 다만 건수 자체가 이보다 적으면 노이즈로 봅니다


def _find_mode_threshold(s: pd.Series, min_gap_ratio: float = 0.3):
    """값들을 정렬했을 때 중간에 큰 빈 구간이 있으면 그 지점을 경계로 돌려줍니다.
    빈 구간이 없으면(= 값이 고르게 퍼져 있으면) None을 돌려줍니다.
    """
    s = s.dropna()
    v = s.unique()
    v.sort()
    if len(v) < 2:
        return None

    gaps = v[1:] - v[:-1]
    i = int(gaps.argmax())
    span = v[-1] - v[0]
    if span <= 0 or gaps[i] < span * min_gap_ratio:
        return None  # 뚜렷하게 갈리지 않음

    threshold = float((v[i] + v[i + 1]) / 2)

    low, high = s[s < threshold], s[s >= threshold]
    smaller = min(len(low), len(high))
    # 적게 돌린 조건이라도 실제로 존재하면 잡아내야 합니다.
    # (RG3 저속은 전체의 5.5%뿐이지만 불량률이 고속의 4배가 넘습니다.)
    if smaller < MIN_MODE_COUNT or smaller / len(s) < MIN_MODE_RATIO:
        return None

    # 두 덩어리 사이의 간격이, 각 덩어리 내부의 흩어짐보다 훨씬 커야
    # 진짜로 "다른 조건"이라고 볼 수 있습니다.
    # (이 조건이 없으면 6.79와 6.81처럼 사실상 같은 값도 갈라버립니다.)
    spread = max(low.std(), high.std(), 1e-9)
    if gaps[i] < spread * 5:
        return None
    # 대표값 자체가 눈에 띄게 달라야 현장에서 "다른 조건"으로 인식됩니다.
    if abs(high.median() - low.median()) < abs(s.median()) * 0.2:
        return None

    return threshold


def detect_operating_modes(df: pd.DataFrame, part_code: str) -> dict:
    """한 품번 안에 서로 다른 운전 조건이 있는지 찾아냅니다."""
    sub = df[df["part_code"] == part_code]
    if len(sub) < 50:
        return {"part_code": part_code, "has_modes": False}

    normal = sub[sub["PassOrFail"] == "Y"]
    best = None
    for col in SENSOR_COLS:
        thr = _find_mode_threshold(normal[col])
        if thr is None:
            continue
        # 여러 개면 표준편차가 가장 큰(= 가장 뚜렷하게 갈리는) 변수를 고릅니다
        score = normal[col].std()
        if best is None or score > best[2]:
            best = (col, thr, score)

    if best is None:
        return {"part_code": part_code, "has_modes": False}

    col, thr, _ = best
    modes = []
    for name, part in (("저속", sub[sub[col] < thr]), ("고속", sub[sub[col] >= thr])):
        n_fail = int((part["PassOrFail"] == "N").sum())
        modes.append({
            "mode": name,
            "range": f"{col} {'<' if name == '저속' else '>='} {round(thr, 1)}",
            "typical_value": round(float(part[col].median()), 1),
            "total": len(part),
            "n_defect": n_fail,
            "defect_rate_pct": round(n_fail / len(part) * 100, 2) if len(part) else 0.0,
        })

    return {
        "part_code": part_code,
        "has_modes": True,
        "split_variable": col,
        "threshold": round(thr, 1),
        "note": (f"{part_code}는 {col} 값이 두 갈래로 갈립니다. "
                 f"평균값은 실제로 존재하지 않는 값이므로, 조건별로 나누어 보아야 합니다."),
        "modes": modes,
    }


def _apply_mode(df: pd.DataFrame, part_code: str, mode: str):
    """지정한 운전 조건에 해당하는 행만 걸러냅니다."""
    info = detect_operating_modes(df, part_code)
    if not info.get("has_modes"):
        return df[df["part_code"] == part_code], info
    col, thr = info["split_variable"], info["threshold"]
    sub = df[df["part_code"] == part_code]
    sub = sub[sub[col] < thr] if mode == "저속" else sub[sub[col] >= thr]
    return sub, info


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

        # 두 가지를 모두 만족해야 "차이가 있다"고 봅니다.
        #  - pct_diff: 정상값 대비 몇 % 차이나는가 (현장에서 체감되는 크기)
        #  - z_score : 정상군이 평소 흔들리는 폭에 비해 얼마나 벗어났는가
        # 둘 중 하나만 보면 속습니다.
        #  예1) 체결시간 7.13 vs 7.12는 z=2.08이지만 실제 차이가 0.01이라 무의미
        #  예2) 전환위치는 정상의 99.7%가 0인데 이상치 4건 때문에 평균이 2.27이 되어
        #       "100% 차이"로 보이지만, z=-0.06으로 사실상 차이가 없음
        pct = abs(t_mean - n_mean) / abs(n_mean) * 100 if n_mean else 0.0
        z = (t_mean - n_mean) / n_std
        if pct < MIN_PCT_DIFF or abs(z) < MIN_ABS_Z:
            continue

        rows.append({
            "variable": col,
            "normal_mean": round(n_mean, 2),
            "defect_mean": round(t_mean, 2),
            "pct_diff": round(pct, 1),
            "z_score": round(z, 2),
        })

    rows.sort(key=lambda r: abs(r["z_score"]), reverse=True)

    if not rows:
        return {
            "n_defect": len(target),
            "n_normal": len(normal),
            "skipped": False,
            "top_differences": [],
            "note": ("정상 제품과 뚜렷하게 다른 값이 발견되지 않았습니다. "
                     "이 데이터에 없는 요인(원료, 금형 상태 등)일 수 있습니다."),
        }

    return {
        "n_defect": len(target),
        "n_normal": len(normal),
        "skipped": False,
        # 표본이 적으면 "확정"이 아니라 "우선 확인 대상"으로 말하게 하는 신호
        "low_sample_warning": len(target) < LOW_SAMPLE_LIMIT,
        "top_differences": rows[:top_n],
    }


def compare_normal_vs_defect(df: pd.DataFrame, reason: str, part_code: str = None,
                             mode: str = None, top_n: int = 5) -> dict:
    """특정 불량 원인(reason) 그룹과 정상 그룹의 센서값을 비교합니다.

    비교는 항상 두 단계로 좁혀서 합니다.
      1단계 — 같은 품번 안에서만 비교한다.
              품번이 다르면 금형과 설정값 자체가 달라서, 전체를 한꺼번에 비교하면
              "불량이라서 다른 것"과 "품번이라서 다른 것"이 뒤섞입니다.
              (사출속도는 CN7 55.5 / RG3 128.2로 두 배 넘게 다릅니다.)
      2단계 — 같은 운전 조건 안에서만 비교한다.
              한 품번 안에서도 조건이 갈리면 평균이 의미를 잃습니다.
              (CN7 스크류 회전수는 29 아니면 292이고, 평균 124.7은 존재하지 않는 값입니다.)

    인자를 생략하면 그 단계를 나누어 전부 돌려줍니다.
    """
    if reason not in df["Reason"].dropna().unique():
        return {"error": f"'{reason}' 원인에 해당하는 데이터가 없습니다.", "n_defect": 0}

    # 품번 지정이 없으면 품번별로 나눠서 전부 비교
    if not part_code:
        return {
            "reason": reason,
            "compared_within_part": True,
            "note": ("품번마다 금형과 설정값이 달라 원인도 다를 수 있으므로 "
                     "품번별로 나누어 비교한 결과입니다. 품번을 뭉쳐서 비교하면 안 됩니다."),
            "by_part": {code: _compare_within(g, reason, top_n)
                        for code, g in df.groupby("part_code")},
        }

    if part_code not in df["part_code"].dropna().unique():
        return {"error": f"'{part_code}' 품번 데이터가 없습니다."}

    mode_info = detect_operating_modes(df, part_code)

    # 운전 조건이 갈리는데 조건을 지정하지 않았으면, 조건별로 나눠서 전부 비교
    if mode_info.get("has_modes") and not mode:
        by_mode = {}
        for m in ("저속", "고속"):
            sub, _ = _apply_mode(df, part_code, m)
            by_mode[m] = _compare_within(sub, reason, top_n)
        return {
            "reason": reason,
            "part_code": part_code,
            "compared_within_part": True,
            "operating_modes": mode_info,
            "note": mode_info["note"],
            "by_mode": by_mode,
        }

    sub, _ = _apply_mode(df, part_code, mode) if mode else (
        df[df["part_code"] == part_code], mode_info)
    result = _compare_within(sub, reason, top_n)
    result.update({
        "reason": reason,
        "part_code": part_code,
        "mode": mode,
        "compared_within_part": True,
    })
    return result


# ---------------------------------------------------------------------
# STEP 3. 조치 제안 — "그럼 뭘 조정해야 해요?"
# ---------------------------------------------------------------------
# 원인별 조치 제안은 "데이터가 지목한 변수 + 공정 상식"을 결합해서 만듭니다.
# 완전 자동화하기보다, 팀이 검증한 조치 문구를 미리 정의해두고
# compare_normal_vs_defect() 결과의 상위 변수와 매칭하는 방식을 추천합니다.
# ---------------------------------------------------------------------
# 원인별 집계 — "가스랑 미성형 중에 뭐가 더 자주 나요?"
# ---------------------------------------------------------------------
def count_defects_by_reason(df: pd.DataFrame, part_code: str = None) -> dict:
    """불량 원인별 건수와 비중을 세어 돌려줍니다."""
    sub = df[df["part_code"] == part_code] if part_code else df
    if part_code and len(sub) == 0:
        return {"error": f"'{part_code}' 품번 데이터가 없습니다."}

    total = len(sub)
    n_fail = int((sub["PassOrFail"] == "N").sum())
    counts = sub["Reason"].value_counts()

    rows = [{
        "reason": r,
        "count": int(c),
        "share_of_defects_pct": round(c / n_fail * 100, 1) if n_fail else 0.0,
        "rate_of_production_pct": round(c / total * 100, 3) if total else 0.0,
    } for r, c in counts.items()]

    return {
        "part_code": part_code,
        "total_production": total,
        "total_defects": n_fail,
        "overall_defect_rate_pct": round(n_fail / total * 100, 2) if total else 0.0,
        "by_reason": rows,
    }


# ---------------------------------------------------------------------
# 최근 불량 개별 조회 — "가장 최근 불량 5건의 원인을 각각 알려줘"
# ---------------------------------------------------------------------
def get_recent_defects(df: pd.DataFrame, n: int = 5) -> dict:
    """가장 최근에 발생한 불량을 하나씩 돌려줍니다.
    각 건마다, 같은 품번·같은 운전 조건의 정상 제품과 비교해
    가장 크게 벗어난 값 두 개를 함께 알려줍니다.
    """
    fails = df[df["PassOrFail"] == "N"].sort_values("TimeStamp", ascending=False).head(n)
    if len(fails) == 0:
        return {"error": "불량 데이터가 없습니다.", "defects": []}

    items = []
    for _, row in fails.iterrows():
        pc = row["part_code"]
        peers = df[(df["part_code"] == pc) & (df["PassOrFail"] == "Y")]

        # 같은 운전 조건의 정상 제품하고만 비교합니다
        info = detect_operating_modes(df, pc) if pd.notna(pc) else {"has_modes": False}
        if info.get("has_modes"):
            col, thr = info["split_variable"], info["threshold"]
            peers = peers[peers[col] < thr] if row[col] < thr else peers[peers[col] >= thr]

        outliers = []
        if len(peers) >= 30:
            for c in SENSOR_COLS:
                m, sd = peers[c].mean(), peers[c].std()
                if not sd or sd <= 0 or not m:
                    continue
                pct = abs(row[c] - m) / abs(m) * 100
                z = float((row[c] - m) / sd)
                if pct < MIN_PCT_DIFF or abs(z) < MIN_ABS_Z:
                    continue
                outliers.append({"variable": c, "value": round(float(row[c]), 2),
                                 "normal_mean": round(float(m), 2),
                                 "pct_diff": round(pct, 1),
                                 "z_score": round(z, 2)})
            outliers.sort(key=lambda r: abs(r["z_score"]), reverse=True)

        items.append({
            "timestamp": str(row["TimeStamp"]),
            "part_code": pc,
            "part_name": row["PART_NAME"],
            "reason": row["Reason"] if pd.notna(row["Reason"]) else "사유 미기재",
            "notable_values": outliers[:2],
        })

    return {
        "note": "각 건은 같은 품번·같은 운전 조건의 정상 제품과 비교한 결과입니다.",
        "caution": "한 건만으로는 원인을 단정할 수 없습니다. 확인해볼 값으로만 제시하세요.",
        "defects": items,
    }


# ---------------------------------------------------------------------
# 특정 변수 확인 — "금형온도가 불량이랑 관계있어요?"
# ---------------------------------------------------------------------
# 현장에서 쓰는 말 -> 실제 컬럼 이름
VARIABLE_ALIASES = {
    "사출속도": ["Max_Injection_Speed"],
    "사출시간": ["Injection_Time"],
    "충전시간": ["Filling_Time"],
    "사출압력": ["Max_Injection_Pressure"],
    "보압": ["Max_Switch_Over_Pressure"],
    "배압": ["Max_Back_Pressure", "Average_Back_Pressure"],
    "금형온도": ["Mold_Temperature_1", "Mold_Temperature_2",
             "Mold_Temperature_3", "Mold_Temperature_4"],
    "배럴온도": [f"Barrel_Temperature_{i}" for i in range(1, 8)],
    "호퍼온도": ["Hopper_Temperature"],
    "스크류회전수": ["Max_Screw_RPM", "Average_Screw_RPM"],
    "사이클타임": ["Cycle_Time"],
    "가소화시간": ["Plasticizing_Time"],
    "쿠션위치": ["Cushion_Position"],
    "형체시간": ["Clamp_Close_Time"],
}


def _check_variable_within(sub: pd.DataFrame, cols: list, reason: str = None) -> dict:
    """하나의 품번·하나의 운전 조건 안에서만 특정 변수를 비교하는 내부 함수."""
    normal = sub[sub["PassOrFail"] == "Y"]
    target = sub[sub["Reason"] == reason] if reason else sub[sub["PassOrFail"] == "N"]

    if len(target) < MIN_DEFECT_SAMPLES:
        return {"n_defect": len(target), "skipped": True,
                "note": f"불량 표본이 {len(target)}건뿐이라 비교할 수 없습니다."}

    results = []
    for c in cols:
        m, sd, t = normal[c].mean(), normal[c].std(), target[c].mean()
        if not sd or sd <= 0:
            results.append({"column": c, "note": "정상군에서 값이 변하지 않아 비교 불가"})
            continue

        pct = abs(t - m) / abs(m) * 100 if m else 0.0
        z = float((t - m) / sd)

        # 불량군의 실제 관측 범위와 정상군의 범위를 함께 줍니다.
        # "몇 도 이상이면 위험해요?" 같은 질문에 평균만으로 답하면
        # 정상군과 범위가 겹치는 경우를 놓칠 수 있습니다.
        # (예: 정상군도 최대 27.8도까지 나온 적이 있는데, 불량군 평균이 27.65도라고
        #  "27.5도 이상이면 위험"이라 말하면 틀린 확답이 됩니다.)
        n_min, n_max = float(normal[c].min()), float(normal[c].max())
        t_min, t_max = float(target[c].min()), float(target[c].max())
        overlap = not (t_max < n_min or t_min > n_max)

        results.append({
            "column": c,
            "normal_mean": round(float(m), 2),
            "normal_range": [round(n_min, 2), round(n_max, 2)],
            "defect_mean": round(float(t), 2),
            "defect_range": [round(t_min, 2), round(t_max, 2)],
            "pct_diff": round(pct, 1),
            "z_score": round(z, 2),
            "meaningful": bool(pct >= MIN_PCT_DIFF and abs(z) >= MIN_ABS_Z),
            "ranges_overlap": overlap,
            "overlap_note": (
                "정상군과 불량군의 관측 범위가 겹칩니다. 특정 숫자를 '이 값 이상이면 "
                "위험'이라고 단정하지 말고, 평균이 높은/낮은 쪽으로 치우친 경향만 말하세요."
                if overlap else
                "정상군과 불량군의 관측 범위가 겹치지 않습니다. 관측된 defect_range를 "
                "참고 삼아 경계값을 제시할 수 있지만, 표본이 적으면 확정적으로 말하지 마세요."
            ),
        })

    any_meaningful = any(r.get("meaningful") for r in results)
    return {
        "n_defect": len(target),
        "n_normal": len(normal),
        "skipped": False,
        "low_sample_warning": len(target) < LOW_SAMPLE_LIMIT,
        "related": any_meaningful,
        "conclusion": ("불량군과 뚜렷한 차이가 있습니다." if any_meaningful
                       else "불량군과 정상군 사이에 뚜렷한 차이가 없습니다. "
                            "이 값은 원인으로 보기 어렵습니다."),
        "details": results,
    }


def check_variable(df: pd.DataFrame, variable: str, reason: str = None,
                   part_code: str = None, mode: str = None) -> dict:
    """특정 변수 하나가 불량과 관계있는지만 콕 집어 확인합니다.
    compare_normal_vs_defect는 상위 몇 개만 돌려주기 때문에,
    "금형온도가 관계있어요?"처럼 변수를 지정한 질문에는 이 함수를 씁니다.

    주의: 운전 조건이 있는 품번에서 mode를 지정하지 않으면 두 조건이 섞여
    결론이 왜곡될 수 있습니다. 그래서 조건이 있으면 자동으로 나누어 계산합니다.
    """
    cols = VARIABLE_ALIASES.get(variable.replace(" ", ""))
    if not cols:
        cols = [c for c in SENSOR_COLS if c.lower() == variable.lower()]
    if not cols:
        return {"error": f"'{variable}'에 해당하는 값을 찾을 수 없습니다.",
                "available": list(VARIABLE_ALIASES.keys())}

    if not part_code:
        return {"error": "품번을 지정해야 합니다. 품번마다 설정값이 달라 뭉쳐서 보면 안 됩니다.",
                "hint": "part_code에 'CN7' 또는 'RG3'을 넣어주세요."}

    mode_info = detect_operating_modes(df, part_code)

    if mode_info.get("has_modes") and not mode:
        by_mode = {}
        for m in ("저속", "고속"):
            sub, _ = _apply_mode(df, part_code, m)
            by_mode[m] = _check_variable_within(sub, cols, reason)
        return {
            "variable": variable,
            "reason": reason,
            "part_code": part_code,
            "operating_modes": mode_info,
            "note": (mode_info["note"] + " 그래서 저속/고속을 섞지 않고 나누어 "
                     "계산했습니다. 두 조건의 결과가 다를 수 있으니 반드시 "
                     "조건을 밝혀서 답하세요."),
            "by_mode": by_mode,
        }

    sub, _ = _apply_mode(df, part_code, mode) if mode else (
        df[df["part_code"] == part_code], None)
    result = _check_variable_within(sub, cols, reason)
    result.update({
        "variable": variable,
        "reason": reason,
        "part_code": part_code,
        "mode": mode,
    })
    return result


ACTION_RULES = {
    ("가스", "CN7"): [
        "먼저 운전 조건 확인 — 고속(스크류 약 292) 조건의 불량률이 1.50%로 "
        "저속(약 29) 조건 0.05%보다 30배 높음. 가스 불량은 전부 고속 조건에서 발생",
        "고속 조건에서 금형온도 3·4번 확인 — 불량 시 25.1/27.7℃, 정상 22.1/24.1℃",
        "금형온도가 오르는 원인(냉각수 유량·온도, 연속 가동 시간) 점검",
    ],
    ("가스", "RG3"): [
        "스크류 평균 회전수 확인 — 불량 시 231, 정상 276으로 낮았음",
        "가소화가 충분히 이루어지는지 확인",
    ],
    ("미성형", "CN7"): [
        "금형온도 3·4번 확인 (가스 불량과 유사한 패턴)",
        "고속 조건 여부를 함께 확인",
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
        if not actions:
            return {
                "reason": reason,
                "part_code": part_code,
                "actions": [],
                "has_verified_rule": False,
                "note": (f"'{reason} / {part_code}' 조합에 대해서는 팀이 검증한 조치안이 "
                         "아직 없습니다. 조치를 지어내지 말고, 검증된 조치가 없다는 사실을 "
                         "밝힌 뒤 compare_normal_vs_defect 결과를 근거로 "
                         "'확인해볼 값'만 제시하세요."),
                "part_defect_rate_pct": float(part_rate.get(part_code, 0)),
            }
        return {
            "reason": reason,
            "part_code": part_code,
            "actions": actions,
            "has_verified_rule": True,
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
    status, reason = QUESTION_CATALOG.get(
        question_tag, ("UNKNOWN", "카탈로그에 없는 질문 태그입니다."))
    result = {"question_tag": question_tag, "status": status, "reason": reason}
    if status == "UNKNOWN":
        result["guidance"] = (
            "이 질문은 사전에 검토되지 않았습니다. 다른 도구로 실제 데이터를 "
            "확인할 수 있으면 확인하고, 확인할 도구가 없으면 답할 수 없다고 "
            "밝히세요. 추측으로 답하지 마세요.")
    return result


if __name__ == "__main__":
    # 간단한 동작 확인용 (터미널에서 python functions.py 로 실행)
    df = load_data()
    print("=== STEP1 테스트 ===")
    print(get_worst_day(df))
    print("\n=== STEP2 테스트 (CN7 고속 조건) ===")
    print(detect_operating_modes(df, "CN7")["modes"])
    print(compare_normal_vs_defect(df, "가스", part_code="CN7", mode="고속")["top_differences"])
    print("\n=== STEP3 테스트 ===")
    print(suggest_action(df, "가스", part_code="CN7"))
    print("\n=== STEP4 테스트 ===")
    print(check_answerable("day_vs_night"))