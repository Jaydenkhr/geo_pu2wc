#!/usr/bin/env python3
"""논문1 표 2(채널 귀속별 인용 분포)와 단계 × 엔진 분포를 공개 데이터에서 다시 계산한다.

사용법:  python reproduce_table2.py ../data/classified_citations_final.csv
기준: 원문 회차(wave == '원문'), 리다이렉트 제외 행('(제외)') 18건 제외 → N' = 3,422
"""
import csv, sys
from collections import Counter, defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "../data/classified_citations_final.csv"
rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig"))
        if r["wave"] == "원문" and r["axis2_5범주"] != "(제외)"]

CATS = ["owned", "earned", "shared", "commerce", "etc"]
LABEL = {"owned": "자사", "earned": "획득", "shared": "공유", "commerce": "중개·거래", "etc": "미분류"}
ENG = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "perplexity": "Perplexity"}

n = len(rows)
tot = Counter(r["axis2_5범주"] for r in rows)
print(f"표 2 — 원문 회차 N' = {n:,}")
for c in CATS:
    print(f"  {LABEL[c]:6s} {tot[c]:5,d}  {tot[c]/n*100:5.1f}%")

print("\n단계 × 엔진 (자사/획득/공유/중개·거래/미분류, 계)")
cell = defaultdict(Counter)
for r in rows:
    cell[(r["tier"], ENG.get(r["engine"], r["engine"]))][r["axis2_5범주"]] += 1
for key in sorted(cell):
    c = cell[key]; s = sum(c.values())
    print(f"  {key[0]} {key[1]:10s} " + " ".join(f"{c[k]:4d}" for k in CATS) + f"  {s:5d}")
