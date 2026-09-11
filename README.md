# ShopFloor Copilot

AI agent that helps factory workers find the root cause of manufacturing defects — just by asking in plain language.

## Problem

Factory workers often notice something is wrong (e.g. "more scratches today") but don't know how to dig into the production data to find out why. ShopFloor Copilot lets them ask questions in natural language and get data-backed answers.

## Demo Flow

1. **Status** — "Was there a day with unusually high defect rate this week?"
2. **Root Cause** — "What was different between defective and normal products when gas defects happened?"
3. **Action** — "What should we adjust?"
4. **Honesty check** — For questions the data can't answer (e.g. "why more defects at night?"), the agent says so honestly instead of guessing.

## Data Source

Injection Molding AI Dataset from KAMP
(Korea AI Manufacturing Platform, https://www.kamp-ai.kr)

Provider: KAIST
Contributors: UNIST / EPM Solutions Co., Ltd.
Registered: 2020-12-14
Usage: Modification permitted

- 7,996 rows x 45 columns
- 71 defective cases (0.89%)
- Defect reasons: Gas (35) / Startup scrap, labeled "initial tolerance defect" (20) / Short shot (16)

## How It Avoids Misleading Answers

Averages over the whole dataset pointed to the wrong causes three times. The app now narrows every comparison step by step:

1. **Same part** — CN7 and RG3 run with different molds and settings.
2. **Same operating mode** — CN7 screw RPM is either ~29 or ~292; the average (124.7) never actually occurs.
3. **Same day** — all 13 CN7 gas defects happened within 36 minutes on 2020-10-16, and normal parts from that day had the same mold temperature. A difference that disappears against same-day normal parts is not reported as a cause.

When nothing survives these checks, the app says so instead of inventing a cause.

## Sample Upload Data (Synthetic)

`synthetic_shift_demo.csv` is a **synthetic demo file** for trying the upload feature. It is not real factory data.

- The original KAMP data was produced almost entirely at night (98.6%), so day and night shifts cannot be compared.
  The app says so instead of guessing.
- To show what a shift comparison looks like, `make_synthetic_shift_data.py` moves the timestamps of some
  production runs forward by 10 hours. Sensor values, pass/fail labels and defect reasons are unchanged.
- In this file the night shift looks worse when everything is combined (1.44% vs 0.61%),
  but within the same part and operating mode the two shifts are similar. The night shift simply ran
  more of the parts that always have higher defect rates.
- When this file is uploaded, the app shows a "synthetic data" warning and the agent says so in its answers.

## Tech Stack

- Python 3.13
- Streamlit (web UI)
- Anthropic Claude API (claude-haiku-4-5)
- pandas (data analysis)

## Setup

1. Clone this repository
```bash
git clone https://github.com/croco603/shopfloor_copilot.git
cd shopfloor_copilot
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Add your Claude API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your_key_here
```

4. The dataset (`labeled_data.csv`) is already included in this repository.

## Run

```bash
streamlit run app.py
```

## Team

Kim Segwan, Minho, Jiwon — Mirae Future Tech School
Built for AI Builders Hackathon 2026

## Known Limitations

- The app may take 30–60 seconds to wake up if it has not been used for a few days (Streamlit Cloud).
- Action rules and field terms are specific to injection molding.
- 2,764 rows in the dataset appear to be duplicate records (same timestamp, part and sensor values).
  Daily defect rates are unaffected, but raw counts include them.
- LH and RH parts come from the same shot and share identical sensor values, so the data cannot explain
  why one side has more defects; the mold cavity itself has to be inspected.