"""Parse persona_full_survey_results.json and print summary."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

with open("tmp/persona_full_survey_results.json", encoding="utf-8") as f:
    data = json.load(f)

results = data["results"]
questions = data["questions"]

SEP = "=" * 80
print(SEP)
print("15-PERSONA FULL SURVEY TEST RESULTS")
print(SEP)
print(f"Questions: {len(questions)}")
print(f"Personas tested: {len(results)}")
print()

success = sum(1 for r in results.values() if r is not None)
fail = sum(1 for r in results.values() if r is None)
print(f"Success: {success}/15")
print(f"Failed:  {fail}/15")
print()

print(f"{'Name':<10} {'Intent':>6} {'Sent':<10} {'Ans':>5} Verdict")
print("-" * 75)
for name in sorted(results.keys()):
    r = results[name]
    if r is None:
        print(f"{name:<10} FAILED")
        continue
    intent = r.get("overall_intent", "?")
    sent = r.get("sentiment", "?")
    ans = len(r.get("answers", []))
    verdict = r.get("one_sentence_verdict", "")
    print(f"{name:<10} {intent:>6} {sent:<10} {ans:>3}/30 {verdict}")

print()
print("SCORE DISTRIBUTION:")
scores: dict[int, list[str]] = {}
for name, r in results.items():
    if r is None:
        continue
    s = r.get("overall_intent", 0)
    scores.setdefault(s, []).append(name)
for s in sorted(scores.keys()):
    print(f"  {s}分: {scores[s]}")

print()
print("ANSWER COMPLETENESS:")
incomplete = []
for name, r in results.items():
    if r is None:
        continue
    ans_count = len(r.get("answers", []))
    if ans_count != 30:
        incomplete.append(f"{name}: {ans_count}/30")
if incomplete:
    for i in incomplete:
        print(f"  INCOMPLETE: {i}")
else:
    print("  ALL 15 personas answered all 30 questions")

print()
print("THINKING PROCESS LENGTH:")
for name in sorted(results.keys()):
    r = results[name]
    if r is None:
        continue
    tp = r.get("thinking_process", "")
    print(f"  {name:<10}: {len(tp)} chars")

print()
print("SENTIMENT DISTRIBUTION:")
sentiments: dict[str, list[str]] = {}
for name, r in results.items():
    if r is None:
        continue
    s = r.get("sentiment", "unknown")
    sentiments.setdefault(s, []).append(name)
for s, names in sentiments.items():
    print(f"  {s}: {names}")
