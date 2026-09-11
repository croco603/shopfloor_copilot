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

# ---------------------------------------------------------------------
# [수정 F1] AI가 넘기는 이름을 데이터 값으로 통일 — 영어 모드 버그 방지
# ---------------------------------------------------------------------
# 영어로 질문하면 AI가 reason="gas", mode="high-speed"처럼 영어로 도구를 부릅니다.
# 데이터에는 '가스', '고속'으로 적혀 있어서, 변환하지 않으면
#   - "해당 불량 없음"이 되거나 (가스 조치안이 있는데도 "없음"이라고 답한 버그)
#   - mode="low-speed"가 '저속'이 아니라서 고속 데이터가 계산되는 조용한 버그가 납니다.
# 변환은 reason / part_code / mode를 받는 모든 함수의 맨 앞에서 한 번만 합니다.
# (같은 규칙을 여러 곳에 복사하면 한 곳을 놓칩니다 — 실제로 겪은 버그)
REASON_ALIASES = {
    "가스": "가스", "gas": "가스", "gasdefect": "가스", "gasmark": "가스",
    "gastrap": "가스", "burnmark": "가스",
    "미성형": "미성형", "shortshot": "미성형", "shortshots": "미성형", "short": "미성형",
    "shortshotdefect": "미성형", "incompletefill": "미성형", "incompletefilling": "미성형",
    "초기허용불량": "초기허용불량", "initialtolerancedefect": "초기허용불량",
    "initialtolerance": "초기허용불량", "initialdefect": "초기허용불량",
    "startupscrap": "초기허용불량", "startupdefect": "초기허용불량",
    # 9/11 로컬 버전에 있던 표기도 그대로 받습니다.
    "gasdefects": "가스", "incompletemolding": "미성형",
    "initialtolerancedefects": "초기허용불량", "initialallowabledefect": "초기허용불량",
}
# "원인을 따로 정하지 않음(전체 불량)"을 뜻하는 표현들
ALL_WORDS = {"", "all", "any", "none", "null", "total", "both", "defect", "defects",
             "alldefects", "anydefect", "전체", "불량", "전체불량", "모든불량", "모두"}
MODE_ALIASES = {
    "저속": "저속", "low": "저속", "lowspeed": "저속", "slow": "저속", "lowmode": "저속",
    "고속": "고속", "high": "고속", "highspeed": "고속", "fast": "고속", "highmode": "고속",
}


def _key(text) -> str:
    """'High-Speed', 'high_speed', 'high speed'를 모두 'highspeed'로 맞춥니다."""
    return str(text).lower().replace(" ", "").replace("_", "").replace("-", "")


def _normalize_reason(reason, df=None):
    """원인 이름을 데이터 값('가스' 등)으로 바꿉니다. 지정하지 않았으면 None."""
    if reason is None or _key(reason) in ALL_WORDS:
        return None
    raw = str(reason).strip()
    if df is not None and raw in set(df["Reason"].dropna()):
        return raw  # 업로드한 데이터에 이미 그 이름이 있으면 그대로 씁니다
    return REASON_ALIASES.get(_key(raw), raw)


def _normalize_part(part_code):
    if part_code is None or _key(part_code) in ALL_WORDS:
        return None
    return str(part_code).strip().upper()


def _normalize_mode(mode):
    """'low-speed' -> '저속'. 모르는 값이면 None(= 조건을 나눠서 둘 다 계산)."""
    if mode is None or _key(mode) in ALL_WORDS:
        return None
    return MODE_ALIASES.get(_key(mode))


def _valid_reasons(df) -> list:
    return sorted(df["Reason"].dropna().unique().tolist())


def _reason_error(df, reason):
    """데이터에 없는 원인 이름이면 에러 dict를, 괜찮으면 None을 돌려줍니다.
    에러에 '쓸 수 있는 값'을 같이 넣어야 AI가 이유를 지어내지 않고 다시 호출합니다.
    """
    valid = _valid_reasons(df)
    if reason is None or reason in valid:
        return None
    return {
        "error": f"'{reason}'는 데이터에 없는 불량 원인 이름입니다.",
        "valid_reasons": valid,
        "available_reasons": valid,   # 9/11 로컬 버전과 같은 키 (호환용)
        "hint": ("데이터에 문제가 있다는 뜻이 아닙니다. valid_reasons 중 하나로 다시 호출하거나, "
                 "reason을 비워서 원인별 결과를 모두 받으세요."),
    }


# ---------------------------------------------------------------------
# [수정 F2] 중복 기록 처리 여부 (팀 결정 전까지 False)
# ---------------------------------------------------------------------
# 기본 데이터에는 _id만 다르고 나머지가 전부 같은 행이 2,764개 있습니다.
# (CN7의 10/27·10/29·10/30·11/03이 하루치씩 통째로 두 번 저장됨)
# True로 바꾸면 중복을 빼고 분석합니다. 이때 71건·0.89% 같은 건수 숫자가
# 60건·1.15%로 바뀌므로, 프롬프트·ACTION_RULES·발표자료 숫자도 함께 고쳐야 합니다.
DROP_DUPLICATE_ROWS = False

# 업로드된 파일에 반드시 있어야 하는 컬럼들.
# 이 중 하나라도 없으면 이후 분석 함수들이 KeyError로 앱을 죽입니다.
REQUIRED_COLUMNS = ["TimeStamp", "PassOrFail", "PART_NAME", "Reason"] + SENSOR_COLS


def validate_columns(df: pd.DataFrame) -> list:
    """업로드된 데이터프레임에 분석에 필요한 컬럼이 다 있는지 확인합니다.
    없는 컬럼 이름 리스트를 돌려줍니다. (빈 리스트면 전부 있다는 뜻)
    load_data()로 넘기기 전에 반드시 이 함수로 먼저 확인하세요.
    """
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def load_data(source=None) -> pd.DataFrame:
    """CSV를 불러와서 날짜 타입 등을 정리합니다.

    source가 없으면 기본 데이터 파일(DATA_PATH)을 읽습니다.
    source에 파일 경로나 업로드된 파일 객체(UploadedFile)를 넘기면 그걸 읽습니다.
    앱이 켜질 때 한 번만 불러오고 메모리에 캐싱해서 재사용하세요.
    (매 질문마다 다시 읽으면 느려집니다)
    """
    if source is None:
        source = DATA_PATH
    elif hasattr(source, "seek"):
        # 업로드 파일은 validate_columns에서 이미 한 번 읽혔을 수 있으므로
        # 스트림 위치를 처음으로 되돌려야 다시 읽을 수 있습니다.
        source.seek(0)

    df = pd.read_csv(source)
    missing = validate_columns(df)
    if missing:
        raise ValueError(f"필요한 컬럼이 없습니다: {', '.join(missing[:5])}")

    if DROP_DUPLICATE_ROWS:
        df = df[~df.drop(columns=["_id"], errors="ignore").duplicated()].reset_index(drop=True)

    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"])
    df["date"] = df["TimeStamp"].dt.date
    # 품번 코드(CN7/RG3 등)를 미리 뽑아둡니다. 품번별 비교에 사용합니다.
    df["part_code"] = df["PART_NAME"].str.extract(PART_CODE_PATTERN)
    # 좌우 구분(LH/RH)도 뽑아둡니다. "LH랑 RH 중 어디가 불량이 많아?"에 답하기 위함입니다.
    df["side"] = df["PART_NAME"].str.extract(r"\b(LH|RH)\b")
    return df


def list_part_codes(df: pd.DataFrame, reason: str = None) -> dict:
    """분석에 쓸 수 있는 품번 목록과 각 품번의 불량 건수·불량률을 알려줍니다.
    agent가 '어떤 품번으로 비교할지' 정할 때 참고합니다.

    [수정 F3]
    - reason을 영어로 받아도 동작합니다.
    - 좌우(LH/RH)를 품번·운전 조건별로도 나눕니다. 전체 합산만 주면
      "모든 품번에서 RH가 높다"는 틀린 말이 나옵니다. (RG3 저속은 LH가 더 높음)
    - 생산량이 적은 품번(JX1·SP2는 2개)은 불량률로 판단하지 말라고 표시합니다.
    """
    reason = _normalize_reason(reason, df)
    err = _reason_error(df, reason)
    if err:
        return err

    def _row(g, **keys):
        is_target = (g["Reason"] == reason) if reason else (g["PassOrFail"] == "N")
        total, n_defect = len(g), int(is_target.sum())
        row = dict(keys)
        row.update({
            "total": total,
            "n_defect": n_defect,
            "defect_rate_pct": round(n_defect / total * 100, 2) if total else 0.0,
        })
        if total < LOW_SAMPLE_LIMIT:
            row["low_volume"] = f"생산 {total}개뿐이라 불량률로 판단할 수 없습니다."
        return row

    # 건수만 보면 생산량이 많은 품번이 항상 1위로 보입니다.
    # (CN7 불량 39건, RG3 32건이지만 불량률은 RG3 2.55%로 CN7 0.58%의 4배 이상)
    # 그래서 "먼저 봐야 할 품번"은 건수가 아니라 불량률로 정렬합니다.
    rows = [_row(g, part_code=code) for code, g in df.groupby("part_code")]
    rows.sort(key=lambda r: r["defect_rate_pct"], reverse=True)

    by_side, by_part_side = [], []
    if "side" in df.columns and df["side"].notna().any():
        sided = df.dropna(subset=["side"])
        by_side = [_row(g, side=s) for s, g in sided.groupby("side")]
        by_side.sort(key=lambda r: r["defect_rate_pct"], reverse=True)

        for code, g in sided.groupby("part_code"):
            # LH·RH가 같은 시각에 함께 기록되면 한 번 사출(같은 샷)에서 나온 한 쌍입니다.
            # 이때 두 제품의 센서값은 똑같으므로, 좌우 차이는 센서값으로 설명할 수 없습니다.
            both = g.groupby("TimeStamp")["side"].nunique()
            paired = bool(len(both) and (both == 2).mean() >= 0.9)
            info = detect_operating_modes(df, code)
            if info.get("has_modes"):
                col, thr = info["split_variable"], info["threshold"]
                groups = [("저속", g[g[col] < thr]), ("고속", g[g[col] >= thr])]
            else:
                groups = [(None, g)]
            for m, sub in groups:
                for s, gg in sub.groupby("side"):
                    r = _row(gg, part_code=code, mode=m, side=s)
                    r["paired_shots"] = paired
                    by_part_side.append(r)

    return {
        "reason": reason,
        "parts": rows,
        "by_side": by_side,
        "by_part_side": by_part_side,
        "note": ("defect_rate_pct(불량률) 기준으로 정렬했습니다. n_defect(건수)만 보고 "
                 "우선순위를 판단하지 마세요. low_volume이 있는 품번은 불량률을 말하지 마세요. "
                 "by_side는 모든 품번을 합친 값이라 품번·조건마다 방향이 뒤집힐 수 있습니다. "
                 "좌우를 말할 때는 by_part_side를 확인하고 '모든 품번에서'라고 일반화하지 마세요. "
                 "paired_shots=true이면 LH·RH가 같은 샷에서 나와 센서값이 같습니다. "
                 "그 좌우 차이는 설비 설정값으로 설명할 수 없고, 금형의 좌우 캐비티 쪽이 확인 대상입니다."),
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
    # [수정 F4] 추세 질문용 날짜순 표. (불량률순 표로 추세를 설명하면 순서가 뒤죽박죽이 됩니다)
    in_date_order = daily.reset_index().to_dict(orient="records")
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
                 "돌린 날일 수 있으니 worst_day_production을 확인하세요. "
                 "추세를 물으면 daily_in_date_order를 날짜순으로 설명하고, "
                 "생산량(total)이 30개 미만인 날의 불량률은 판단 근거로 쓰지 마세요."),
        "table": top.to_dict(orient="records"),
        "daily_in_date_order": in_date_order,
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


# ---------------------------------------------------------------------
# [수정 F5] 시간 교란 안전장치 — "그날이 원래 그랬던 것"을 걸러냅니다
# ---------------------------------------------------------------------
# CN7 가스 불량 13건은 전부 10/16 새벽 36분 사이에 났습니다.
# 그날은 정상 제품도 금형온도가 25.0/27.6℃로 높았습니다.
# 다른 날짜의 정상 제품과 섞어 비교하면 "불량일 때 금형온도가 높다"처럼 보이지만,
# 같은 날 정상 제품과 비교하면 차이가 사라집니다. (품번 → 운전 조건에 이은 세 번째 착시)
MIN_SAME_DAY_NORMAL = 30   # 같은 날 정상 제품이 이보다 적으면 같은 날 비교를 하지 않습니다


def _defect_timing(target: pd.DataFrame) -> dict:
    """불량이 언제 났는지 요약합니다. 짧은 시간에 몰려 있으면 경고를 붙입니다."""
    if len(target) == 0:
        return {}
    counts = target["date"].value_counts()
    first, last = target["TimeStamp"].min(), target["TimeStamp"].max()
    concentrated = bool(counts.iloc[0] / len(target) >= 0.8)
    info = {
        "n_dates": int(len(counts)),
        "dates": [str(d) for d in sorted(counts.index)][:5],
        "first": str(first),
        "last": str(last),
        "concentrated": concentrated,
    }
    if concentrated:
        top = target[target["date"] == counts.index[0]]
        minutes = round((top["TimeStamp"].max() - top["TimeStamp"].min()).total_seconds() / 60)
        info["warning"] = (
            f"불량 {len(target)}건 중 {int(counts.iloc[0])}건이 {counts.index[0]} 하루"
            f"({minutes}분 사이)에 몰려 있습니다. same_day_check에서 차이가 사라지면 "
            "그 값은 불량의 원인이 아니라 '그날의 상태'일 수 있으니 원인으로 단정하지 마세요.")
    return info


def _same_day_check(target: pd.DataFrame, normal: pd.DataFrame, col: str) -> dict:
    """불량이 난 날짜의 정상 제품하고만 다시 비교해서, 차이가 남는지 확인합니다."""
    same = normal[normal["date"].isin(target["date"].unique())]
    if len(same) < MIN_SAME_DAY_NORMAL:
        return {"checked": False, "n_same_day_normal": len(same)}
    m, sd, t = same[col].mean(), same[col].std(), target[col].mean()
    pct = abs(t - m) / abs(m) * 100 if m else 0.0
    if sd and sd > 0:
        survives = pct >= MIN_PCT_DIFF and abs((t - m) / sd) >= MIN_ABS_Z
    else:
        survives = pct >= MIN_PCT_DIFF
    return {
        "checked": True,
        "n_same_day_normal": len(same),
        "same_day_normal_mean": round(float(m), 2),
        "survives_same_day": bool(survives),
    }


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
    target = sub[sub["Reason"] == reason] if reason else sub[sub["PassOrFail"] == "N"]

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
    timing = _defect_timing(target)

    if not rows:
        return {
            "n_defect": len(target),
            "n_normal": len(normal),
            "skipped": False,
            "top_differences": [],
            "defect_timing": timing,
            "note": ("정상 제품과 뚜렷하게 다른 값이 발견되지 않았습니다. "
                     "이 데이터에 없는 요인(원료, 금형 상태 등)일 수 있습니다."),
        }

    rows = rows[:top_n]
    # [수정 F5] 상위 차이마다 "같은 날 정상 제품과 비교해도 차이가 남는지" 붙입니다.
    for r in rows:
        r["same_day_check"] = _same_day_check(target, normal, r["variable"])
    vanished = [r["variable"] for r in rows
                if r["same_day_check"].get("checked")
                and not r["same_day_check"]["survives_same_day"]]

    result = {
        "n_defect": len(target),
        "n_normal": len(normal),
        "skipped": False,
        # 표본이 적으면 "확정"이 아니라 "우선 확인 대상"으로 말하게 하는 신호
        "low_sample_warning": len(target) < LOW_SAMPLE_LIMIT,
        "top_differences": rows,
        "defect_timing": timing,
    }
    if vanished:
        result["same_day_note"] = (
            f"{', '.join(vanished)}: 불량이 난 날의 정상 제품과 비교하면 차이가 사라집니다. "
            "이 값은 원인이라기보다 그날의 상태일 수 있으므로 '원인'이 아니라 "
            "'그날 함께 달랐던 값'이라고 표현하세요.")
    return result


def _compare_part(df: pd.DataFrame, part_code: str, reason: str, top_n: int) -> dict:
    """한 품번을 비교합니다. 그 품번에 운전 조건이 갈리면 조건별로 나눕니다.
    (조건을 나누지 않으면 존재하지 않는 평균과 비교하게 됩니다.)
    """
    info = detect_operating_modes(df, part_code)
    if not info.get("has_modes"):
        return _compare_within(df[df["part_code"] == part_code], reason, top_n)

    by_mode = {}
    for m in ("저속", "고속"):
        sub, _ = _apply_mode(df, part_code, m)
        by_mode[m] = _compare_within(sub, reason, top_n)
    return {
        "operating_modes": info,
        "note": info["note"],
        "by_mode": by_mode,
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

    [수정 F6] reason을 영어로 받아도 되고, 생략하면 원인별로 나누어 전부 비교합니다.
    (원인을 섞으면 서로 반대 방향의 차이가 상쇄되어 "차이 없음"처럼 보입니다.)
    """
    reason = _normalize_reason(reason, df)
    err = _reason_error(df, reason)
    if err:
        return err
    part_code, mode = _normalize_part(part_code), _normalize_mode(mode)

    if reason is None:
        return {
            "reason": None,
            "note": ("불량 원인을 지정하지 않아 원인별로 나누어 비교했습니다. "
                     "원인마다 결과가 다르니 섞어서 결론 내리지 마세요."),
            "by_reason": {r: compare_normal_vs_defect(df, r, part_code, mode, top_n=3)
                          for r in _valid_reasons(df)},
        }

    # 품번 지정이 없으면 품번별로 나눠서 전부 비교
    # (각 품번 안에 운전 조건이 갈리면 그것까지 나눕니다)
    if not part_code:
        return {
            "reason": reason,
            "compared_within_part": True,
            "note": ("품번마다 금형과 설정값이 달라 원인도 다를 수 있으므로 "
                     "품번별로 나누어 비교한 결과입니다. 품번을 뭉쳐서 비교하면 안 됩니다. "
                     "운전 조건이 갈리는 품번은 조건별로도 나누었습니다."),
            "by_part": {code: _compare_part(df, code, reason, top_n)
                        for code in df["part_code"].dropna().unique()},
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

    # [수정 F7] 이 데이터에서의 '지금'을 함께 알려줍니다.
    # 없으면 AI가 가장 최근 불량 시각(11/04 05:33)을 '지금'으로 착각해
    # "지난 1시간 동안"이라고 말합니다. (실제 기준일은 11/06)
    ref_date = df["date"].max()
    ref_day = df[df["date"] == ref_date]

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
            "days_before_reference": (ref_date - row["date"]).days,
            "notable_values": outliers[:2],
        })

    return {
        "reference_date": str(ref_date),
        "last_record_time": str(df["TimeStamp"].max()),
        "reference_day_production": len(ref_day),
        "reference_day_defects": int((ref_day["PassOrFail"] == "N").sum()),
        "time_hint": ("데이터의 '지금'은 last_record_time입니다. 불량 시각을 '지금', '방금', "
                      "'지난 1시간'으로 표현하지 말고 기준일로부터 며칠 전인지 밝히세요. "
                      "기준일(reference_date)에 불량이 0건이면 그 사실을 먼저 말하세요."),
        "note": "각 건은 같은 품번·같은 운전 조건의 정상 제품과 비교한 결과입니다.",
        "caution": "한 건만으로는 원인을 단정할 수 없습니다. 확인해볼 값으로만 제시하세요.",
        "defects": items,
    }


# ---------------------------------------------------------------------
# 특정 변수 확인 — "금형온도가 불량이랑 관계있어요?"
# ---------------------------------------------------------------------
# 현장에서 쓰는 말 -> 실제 컬럼 이름
# 한국어와 영어를 모두 받습니다. 심사위원이 영어로 물어볼 수 있기 때문입니다.
VARIABLE_ALIASES = {
    "사출속도": ["Max_Injection_Speed"],
    "사출시간": ["Injection_Time"],
    "충전시간": ["Filling_Time"],
    "사출압력": ["Max_Injection_Pressure"],
    "보압": ["Max_Switch_Over_Pressure"],
    "전환압력": ["Max_Switch_Over_Pressure"],
    "배압": ["Max_Back_Pressure", "Average_Back_Pressure"],
    # [수정 F8] 금형온도 1·2번은 전부 0, 배럴온도 7번은 거의 0이라 뺐습니다. (의미 없는 값이 섞이면 AI가 헷갈립니다)
    "금형온도": ["Mold_Temperature_3", "Mold_Temperature_4"],
    "배럴온도": [f"Barrel_Temperature_{i}" for i in range(1, 7)],
    # "압력이랑 온도 중에 뭐가 문제야?" 같은 묶음 질문용
    "압력": ["Max_Injection_Pressure", "Max_Switch_Over_Pressure",
           "Max_Back_Pressure", "Average_Back_Pressure"],
    "온도": ["Mold_Temperature_3", "Mold_Temperature_4", "Hopper_Temperature"]
          + [f"Barrel_Temperature_{i}" for i in range(1, 7)],
    "호퍼온도": ["Hopper_Temperature"],
    "스크류회전수": ["Max_Screw_RPM", "Average_Screw_RPM"],
    "사이클타임": ["Cycle_Time"],
    "가소화시간": ["Plasticizing_Time"],
    "쿠션위치": ["Cushion_Position"],
    "형체시간": ["Clamp_Close_Time"],

    # 영어 표현
    "injectionspeed": ["Max_Injection_Speed"],
    "injectiontime": ["Injection_Time"],
    "fillingtime": ["Filling_Time"],
    "injectionpressure": ["Max_Injection_Pressure"],
    "holdingpressure": ["Max_Switch_Over_Pressure"],
    "switchoverpressure": ["Max_Switch_Over_Pressure"],
    "backpressure": ["Max_Back_Pressure", "Average_Back_Pressure"],
    "moldtemperature": ["Mold_Temperature_3", "Mold_Temperature_4"],
    "moldtemp": ["Mold_Temperature_3", "Mold_Temperature_4"],
    "barreltemperature": [f"Barrel_Temperature_{i}" for i in range(1, 7)],
    "barreltemp": [f"Barrel_Temperature_{i}" for i in range(1, 7)],
    "pressure": ["Max_Injection_Pressure", "Max_Switch_Over_Pressure",
                 "Max_Back_Pressure", "Average_Back_Pressure"],
    "temperature": ["Mold_Temperature_3", "Mold_Temperature_4", "Hopper_Temperature"]
                   + [f"Barrel_Temperature_{i}" for i in range(1, 7)],
    "hoppertemperature": ["Hopper_Temperature"],
    "screwrpm": ["Max_Screw_RPM", "Average_Screw_RPM"],
    "screwspeed": ["Max_Screw_RPM", "Average_Screw_RPM"],
    "cycletime": ["Cycle_Time"],
    "plasticizingtime": ["Plasticizing_Time"],
    "cushionposition": ["Cushion_Position"],
    "clampclosetime": ["Clamp_Close_Time"],
}


# 값에 대한 주의사항. check_variable 결과에 함께 실어 보냅니다.
VARIABLE_NOTES = {
    "Max_Switch_Over_Pressure": ("보압(holding pressure)을 직접 잰 값이 아니라, 사출에서 보압으로 "
                                 "넘어가는 순간(V/P 전환)의 압력입니다. '보압'이라고 단정하지 마세요."),
}


def _normalize_variable(name: str) -> str:
    """'Mold Temperature', 'mold_temp', '금형 온도'를 모두 같은 키로 맞춥니다."""
    return name.lower().replace(" ", "").replace("_", "").replace("-", "")


# 조회를 빠르게 하기 위해 정규화된 키로 미리 만들어 둡니다.
_ALIAS_LOOKUP = {_normalize_variable(k): v for k, v in VARIABLE_ALIASES.items()}


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

        meaningful = bool(pct >= MIN_PCT_DIFF and abs(z) >= MIN_ABS_Z)
        results.append({
            "column": c,
            "normal_mean": round(float(m), 2),
            "normal_range": [round(n_min, 2), round(n_max, 2)],
            "defect_mean": round(float(t), 2),
            "defect_range": [round(t_min, 2), round(t_max, 2)],
            "pct_diff": round(pct, 1),
            "z_score": round(z, 2),
            "meaningful": meaningful,
            # [수정 F5] 차이가 있을 때만 같은 날 비교를 붙입니다.
            "same_day_check": _same_day_check(target, normal, c) if meaningful else None,
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
    n_checked = len(results)
    # 값이 여러 개 묶인 질문("온도")은 결과가 너무 길어지면 AI가 숫자를 헷갈립니다.
    # 5개 이상이면 차이가 있는 값만 남깁니다.
    if n_checked > 4:
        results = [r for r in results if r.get("meaningful")]
    return {
        "n_defect": len(target),
        "n_normal": len(normal),
        "skipped": False,
        "low_sample_warning": len(target) < LOW_SAMPLE_LIMIT,
        "related": any_meaningful,
        "n_columns_checked": n_checked,
        "conclusion": ("불량군과 뚜렷한 차이가 있습니다." if any_meaningful
                       else "불량군과 정상군 사이에 뚜렷한 차이가 없습니다. "
                            "이 값은 원인으로 보기 어렵습니다."),
        "defect_timing": _defect_timing(target),
        "details": results,
    }


def _collect_findings(tree, ctx=None) -> list:
    """중첩된 결과(by_reason → by_part → by_mode)에서 '차이가 있는 값'만 한 줄씩 뽑습니다.
    AI가 긴 결과를 뒤지다 숫자를 잘못 옮기지 않도록 요약표를 따로 줍니다.
    """
    ctx = ctx or {}
    found = []
    if not isinstance(tree, dict):
        return found
    for d in tree.get("details") or []:
        if d.get("meaningful"):
            sd = d.get("same_day_check") or {}
            found.append({**ctx, "n_defect": tree.get("n_defect"), "column": d["column"],
                          "normal_mean": d["normal_mean"], "defect_mean": d["defect_mean"],
                          "pct_diff": d["pct_diff"],
                          "survives_same_day": sd.get("survives_same_day")})
    for key, label in (("by_reason", "reason"), ("by_part", "part_code"), ("by_mode", "mode")):
        for k, sub in (tree.get(key) or {}).items():
            found += _collect_findings(sub, {**ctx, label: k})
    return found


def check_variable(df: pd.DataFrame, variable: str, reason: str = None,
                   part_code: str = None, mode: str = None) -> dict:
    """특정 변수 하나가 불량과 관계있는지만 콕 집어 확인합니다.
    compare_normal_vs_defect는 상위 몇 개만 돌려주기 때문에,
    "금형온도가 관계있어요?"처럼 변수를 지정한 질문에는 이 함수를 씁니다.

    주의: 운전 조건이 있는 품번에서 mode를 지정하지 않으면 두 조건이 섞여
    결론이 왜곡될 수 있습니다. 그래서 조건이 있으면 자동으로 나누어 계산합니다.
    """
    cols = _ALIAS_LOOKUP.get(_normalize_variable(variable))
    if not cols:
        cols = [c for c in SENSOR_COLS
                if _normalize_variable(c) == _normalize_variable(variable)]
    if not cols:
        return {"error": f"'{variable}'에 해당하는 값을 찾을 수 없습니다.",
                "available": list(VARIABLE_ALIASES.keys()),
                "hint": ("데이터에 그 값이 없다는 뜻이 아닐 수 있습니다. available 중 가장 가까운 "
                         "이름으로 다시 호출하세요.")}

    # [수정 F9] 이름 통일 + 원인을 지정하지 않으면 원인별로 나눕니다.
    # (가스·미성형·초기허용불량을 섞으면 CN7 고속 가스의 금형온도 차이가 묻혀서
    #  "금형온도는 관계없다"는 틀린 단정이 나왔습니다.)
    reason = _normalize_reason(reason, df)
    err = _reason_error(df, reason)
    if err:
        return err
    part_code, mode = _normalize_part(part_code), _normalize_mode(mode)
    notes = {c: VARIABLE_NOTES[c] for c in cols if c in VARIABLE_NOTES}

    if reason is None:
        by_reason = {r: check_variable(df, variable, r, part_code, mode)
                     for r in _valid_reasons(df)}
        return {
            "variable": variable,
            "reason": None,
            "note": ("불량 원인을 지정하지 않아 원인별로 나누어 계산했습니다. 원인을 섞으면 차이가 "
                     "묻힐 수 있습니다. findings에 하나라도 있으면 '관계없다'고 단정하지 말고, "
                     "어느 원인·품번·조건에서 차이가 있었는지 밝히세요."),
            "findings": _collect_findings({"by_reason": by_reason}),
            "variable_notes": notes,
            "by_reason": by_reason,
        }

    # 품번을 지정하지 않았다고 사용자에게 되묻지 않습니다.
    # 분석할 만한 품번(불량이 있는 품번)을 스스로 골라 전부 계산해서 돌려줍니다.
    if not part_code:
        targets = [c for c in df["part_code"].dropna().unique()
                   if (df[df["part_code"] == c]["PassOrFail"] == "N").sum() >= MIN_DEFECT_SAMPLES]
        if not targets:
            return {"variable": variable, "error": "불량 표본이 충분한 품번이 없습니다."}
        return {
            "variable": variable,
            "reason": reason,
            "note": ("품번을 지정하지 않아 불량이 있는 품번을 모두 계산했습니다. "
                     "품번마다 결과가 다를 수 있으니 답변에 품번을 반드시 밝히세요."),
            "by_part": {c: check_variable(df, variable, reason, part_code=c)
                        for c in targets},
        }

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


# [수정 F10] 조치안을 데이터로 다시 확인해서 고쳤습니다.
#  - ("가스","RG3")의 "스크류 회전수 231 vs 276"은 저속·고속을 섞어서 나온 숫자라 삭제
#    (조건을 나누면 두 조건 모두 차이 없음). 대신 같은 샷 좌우 비교 결과로 교체
#  - ("미성형","CN7")은 불량 4건·2건이라 비교 자체가 생략되는 표본이라 삭제
#  - ("가스","CN7")은 금형온도 차이가 같은 날 정상 제품과 비교하면 사라져서 표현을 낮춤
#  - 새 조치안을 넣기 전에는 반드시 compare_normal_vs_defect로 같은 날 비교까지 확인할 것
ACTION_RULES = {
    ("가스", "CN7"): [
        "가스 불량 13건은 모두 2020-10-16 05:21~05:57(36분)에 몰려 발생 — "
        "그 시간대 작업 기록(금형 교체, 재가동, 원료 투입)부터 확인",
        "그날은 정상 제품도 금형온도 3·4번이 약 25.0/27.6℃로 다른 날(약 22~24℃)보다 높았음 — "
        "불량과 정상의 차이는 아니므로 원인 확정이 아니라 냉각수 유량·온도 기록과 대조해볼 후보",
        "고속 조건 불량률(1.50%)이 저속(0.05%)보다 높지만, 두 조건을 서로 다른 기간에 돌려서 "
        "조건 탓인지 시기 탓인지는 이 데이터로 구분할 수 없음",
    ],
    ("가스", "RG3"): [
        "고속 조건 가스 불량 17건은 모두 RH(오른쪽)에서 발생, 같은 샷에서 나온 LH는 0건 — "
        "설비 설정값은 좌우가 같으므로 금형 RH 캐비티 쪽(가스 빼기 벤트, 게이트) 점검 후보",
        "저속 조건 가스 불량 5건은 2020-11-04 05:17~05:33(16분)에 몰려 발생 — 그 시간대 작업 기록 확인",
    ],
    ("초기허용불량", "CN7"): [
        "20건 모두 2020-10-27 00:56~01:05(10분) 가동 직후에 발생 — 공정 불량이 아니라 "
        "시동 초기 폐기분으로 보고 별도 관리",
        "같은 날 정상 제품보다 충전시간이 길고(약 6.0초 vs 4.5초) 배압이 높음 — 조건이 안정되기 전 생산분",
    ],
}


def suggest_action(df: pd.DataFrame, reason: str = None, part_code: str = None) -> dict:
    """원인별 조치안 + 품번별 불량률을 반환합니다.

    조치안은 반드시 (원인, 품번) 쌍으로 관리합니다.
    품번마다 원인이 다르기 때문에, 한 품번에서 얻은 조치를
    다른 품번에 그대로 적용하면 위험합니다.

    [수정 F10]
    - 영어 원인 이름으로 불러도 조치안을 찾습니다. ("gas"로 불러서 "조치안 없음"이 나오던 버그)
    - 품번별 표에 '이 원인의 불량률'과 '전체 불량률'을 이름을 달리해서 넣습니다.
      (전체 불량률 2.55%를 AI가 "가스 불량률"이라고 부르던 버그)
    """
    reason = _normalize_reason(reason, df)
    err = _reason_error(df, reason)
    if err:
        return err
    part_code = _normalize_part(part_code)

    if reason is None:
        return {
            "reason": None,
            "note": "원인을 지정하지 않아 원인별 조치안을 모두 돌려줍니다.",
            "by_reason": {r: suggest_action(df, r, part_code) for r in _valid_reasons(df)},
        }

    table = []
    for code, g in df.groupby("part_code"):
        n_reason = int((g["Reason"] == reason).sum())
        row = {
            "part_code": code,
            "total": len(g),
            "n_defect_this_reason": n_reason,
            "this_reason_rate_pct": round(n_reason / len(g) * 100, 2),
            "overall_defect_rate_pct": round((g["PassOrFail"] == "N").mean() * 100, 2),
        }
        if len(g) < LOW_SAMPLE_LIMIT:
            row["low_volume"] = f"생산 {len(g)}개뿐이라 판단할 수 없습니다. '위험 없음'이라고 말하지 마세요."
        table.append(row)
    table.sort(key=lambda r: r["this_reason_rate_pct"], reverse=True)
    table_note = ("this_reason_rate_pct가 이 원인의 불량률입니다. overall_defect_rate_pct는 모든 원인을 "
                  "합친 불량률이므로 이 원인의 불량률이라고 부르지 마세요.")

    if part_code:
        actions = ACTION_RULES.get((reason, part_code), [])
        part_row = next((r for r in table if r["part_code"] == part_code), None)
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
                "part_rate": part_row,
                "table_note": table_note,
            }
        return {
            "reason": reason,
            "part_code": part_code,
            "actions": actions,
            "has_verified_rule": True,
            "part_rate": part_row,
            "table_note": table_note,
        }

    # 품번 지정이 없으면 품번별 조치안을 모두 반환
    by_part = {r["part_code"]: ACTION_RULES[(reason, r["part_code"])]
               for r in table if (reason, r["part_code"]) in ACTION_RULES}
    return {
        "reason": reason,
        "note": ("품번마다 원인이 다르므로 조치도 품번별로 다릅니다. "
                 "actions_by_part에 없는 품번은 검증된 조치안이 없는 것입니다."),
        "actions_by_part": by_part,
        "has_verified_rule": bool(by_part),
        "part_rate_table": table,
        "table_note": table_note,
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
    # [수정 F12] 영어 테스트에서 나온 질문 — 데이터로 확인해서 채움
    "holding_pressure": ("X", "보압을 직접 측정한 값이 없습니다. V/P 전환 시점의 압력(전환압력)만 있습니다."),
    "left_right_cause": ("Δ", "LH·RH는 같은 샷에서 나와 센서값이 똑같습니다. 좌우 차이가 있다는 사실은 말할 수 있지만, "
                              "그 원인은 센서 데이터로 알 수 없고 금형 좌우 캐비티를 직접 점검해야 합니다."),
    "setting_is_ok": ("Δ", "설정값의 규격(허용 범위)이 데이터에 없어 '괜찮다/아니다'를 판정할 수 없습니다. "
                           "불량 제품과 정상 제품의 값 차이만 비교할 수 있습니다."),
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
    print(get_worst_day(df, days=7)["table"])
    print("\n=== STEP2 테스트 (CN7 고속 조건) ===")
    print(detect_operating_modes(df, "CN7")["modes"])
    r = compare_normal_vs_defect(df, "가스", part_code="CN7", mode="고속")
    print(r["top_differences"])
    print(r.get("same_day_note"))
    print("\n=== STEP3 테스트 ===")
    print(suggest_action(df, "가스", part_code="CN7"))
    print("\n=== STEP4 테스트 ===")
    print(check_answerable("day_vs_night"))

    # [수정 F11] 영어 모드 회귀 테스트 — 하나라도 실패하면 AssertionError가 납니다.
    print("\n=== 영어 입력 테스트 ===")
    assert suggest_action(df, "gas", part_code="cn7")["has_verified_rule"] is True
    assert suggest_action(df, "Gas")["actions_by_part"], "gas 조치안을 못 찾음"
    assert "error" not in compare_normal_vs_defect(df, "short shot", part_code="RG3")
    assert "by_reason" in compare_normal_vs_defect(df, None)
    assert "error" in compare_normal_vs_defect(df, "scratch")          # 없는 원인은 에러
    assert "valid_reasons" in compare_normal_vs_defect(df, "scratch")
    low = compare_normal_vs_defect(df, "gas", part_code="RG3", mode="low-speed")
    assert low["mode"] == "저속", "low-speed가 저속으로 바뀌지 않음"
    assert "error" not in check_variable(df, "injection pressure")
    mt = check_variable(df, "mold temperature")
    assert mt["findings"], "원인별로 나누면 금형온도 차이가 보여야 함"
    assert list_part_codes(df, "gas")["parts"][0]["n_defect"] > 0
    assert "reference_date" in get_recent_defects(df)
    print("모든 테스트 통과")