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
- Defect reasons: Gas (35) / Initial tolerance defect (20) / Short shot (16)

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

4. Download the dataset from KAMP (kamp-ai.kr) and place `labeled_data.csv` in the project root.

## Run

```bash
streamlit run app.py
```

## Team

Kim Segwan, Minho, Jiwon — Mirae Future Tech School
Built for AI Builders Hackathon 2026