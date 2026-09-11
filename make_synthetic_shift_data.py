"""
make_synthetic_shift_data.py
----------------------------
업로드 시연용 '합성 데이터(synthetic_shift_demo.csv)'를 만드는 스크립트입니다.
★ 실제 공장 데이터가 아닙니다. 앱이 "다른 데이터를 올려도 분석한다"는 것을 보여주기 위한 샘플입니다.

왜 만들었나
  원본 KAMP 데이터는 98.6%가 야간(20시~08시) 생산이라 주야간 불량률을 비교할 수 없습니다.
  그래서 일부 생산 구간의 '시각'만 10시간 뒤로 옮겨 주간 생산처럼 만들었습니다.

무엇을 바꿨나 (바꾼 것은 TimeStamp 하나뿐)
  - 센서값, 판정(PassOrFail), 불량 사유(Reason)는 한 글자도 바꾸지 않습니다.
  - 아래 MOVE_TO_DAY 구간에 속한 행만 TimeStamp에 10시간을 더합니다.
    (예: 새벽 01:00 생산 → 오전 11:00 생산)
  - 모든 행에 Data_Note = "SYNTHETIC_DEMO"를 붙입니다.
    앱은 이 표시를 보고 화면에 "합성 데이터" 안내를 띄웁니다.

일부러 만든 결과 — 교란변수 시연
  같은 품번·조건마다 생산 구간의 일부만 주간으로 옮겼습니다.
  그 결과, 합쳐서 보면 야간 불량률이 주간보다 2배 넘게 높지만,
  품번·조건별로 나누면 주간과 야간의 불량률이 비슷합니다.
  주간에는 불량률이 낮은 CN7 저속을 주로 돌리고, 야간에는 불량률이 높은
  RG3·CN7 고속을 더 많이 돌린 것처럼 만들었기 때문입니다.

실행: python make_synthetic_shift_data.py
"""

import pandas as pd

SOURCE = "labeled_data.csv"
OUTPUT = "synthetic_shift_demo.csv"
SHIFT_HOURS = 10

# 주간으로 옮길 생산 구간 (시작, 끝). 이 사이에 찍힌 행만 옮깁니다.
MOVE_TO_DAY = [
    ("2020-10-23 00:00", "2020-10-23 08:00"),   # RG3 고속 생산분 500개
    ("2020-10-27 00:00", "2020-10-27 06:00"),   # CN7 고속 생산분 1,255개
    ("2020-10-29 23:00", "2020-10-30 08:00"),   # CN7 저속 생산분 1,642개
    ("2020-11-03 00:00", "2020-11-03 09:00"),   # CN7 저속 생산분 1,852개 (+ JX1 2개)
]


def main():
    # 모든 칸을 '글자' 그대로 읽습니다. 숫자로 읽었다가 다시 저장하면
    # 30.899999618530277 → 30.89999961853028처럼 끝자리가 달라질 수 있어서입니다.
    df = pd.read_csv(SOURCE, dtype=str, keep_default_na=False)
    ts = pd.to_datetime(df["TimeStamp"])

    move = pd.Series(False, index=df.index)
    for start, end in MOVE_TO_DAY:
        move |= (ts >= start) & (ts < end)

    new_ts = ts.where(~move, ts + pd.Timedelta(hours=SHIFT_HOURS))
    # 원본과 같은 글자 형식(YYYY-MM-DD HH:MM:SS)으로 저장합니다.
    df["TimeStamp"] = new_ts.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["Data_Note"] = "SYNTHETIC_DEMO"

    df.to_csv(OUTPUT, index=False, encoding="utf-8")
    print(f"{OUTPUT} 저장 완료: {len(df):,}행 중 {int(move.sum()):,}행의 시각을 {SHIFT_HOURS}시간 옮김")


if __name__ == "__main__":
    main()
