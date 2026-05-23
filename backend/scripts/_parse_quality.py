"""Check persona answer quality: voice differentiation, thinking, verdicts."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

with open("tmp/persona_full_survey_results.json", encoding="utf-8") as f:
    data = json.load(f)

results = data["results"]
questions = data["questions"]
q_map = {q["id"]: q for q in questions}

SEP = "=" * 80

# 1. Show thinking process for each persona (voice differentiation check)
print(SEP)
print("THINKING PROCESS COMPARISON (voice check)")
print(SEP)
for name in sorted(results.keys()):
    r = results[name]
    if not r:
        continue
    tp = r.get("thinking_process", "")
    verdict = r.get("one_sentence_verdict", "")
    summary = r.get("summary_comment", "")
    print(f"\n--- {name} (intent={r['overall_intent']}, {r['sentiment']}) ---")
    print(f"  Verdict: {verdict}")
    print(f"  Thinking: {tp[:200]}...")
    print(f"  Summary:  {summary[:150]}...")

# 2. Compare answers on same question across personas
print(f"\n\n{SEP}")
print("KEY QUESTION COMPARISON")
print(SEP)

# q01 (open, first impression) - best for voice check
print("\n--- q01: First impression (open) ---")
for name in sorted(results.keys()):
    r = results[name]
    if not r:
        continue
    for a in r.get("answers", []):
        if a.get("qid") == "q01":
            ans = a.get("answer", "")
            print(f"  {name:<10}: {ans[:100]}")
            break

# q09 (price ceiling) - check price anchors match
print("\n--- q09: Price ceiling (open) ---")
for name in sorted(results.keys()):
    r = results[name]
    if not r:
        continue
    for a in r.get("answers", []):
        if a.get("qid") == "q09":
            ans = a.get("answer", "")
            print(f"  {name:<10}: {ans[:100]}")
            break

# q22 (NPS scale) - check score variety
print("\n--- q22: NPS recommendation (scale 1-5) ---")
nps_scores = {}
for name in sorted(results.keys()):
    r = results[name]
    if not r:
        continue
    for a in r.get("answers", []):
        if a.get("qid") == "q22":
            score = a.get("answer", "?")
            nps_scores[name] = score
            break

for name in sorted(nps_scores.keys()):
    print(f"  {name:<10}: {nps_scores[name]}")
nps_vals = [v for v in nps_scores.values() if isinstance(v, int)]
if nps_vals:
    avg = sum(nps_vals) / len(nps_vals)
    print(f"  Distribution: min={min(nps_vals)} max={max(nps_vals)} avg={avg:.1f}")

# q28 (dealbreaker open) - check persona-specific concerns
print("\n--- q28: What stops you from buying? (open) ---")
for name in sorted(results.keys()):
    r = results[name]
    if not r:
        continue
    for a in r.get("answers", []):
        if a.get("qid") == "q28":
            ans = a.get("answer", "")
            print(f"  {name:<10}: {ans[:120]}")
            break
