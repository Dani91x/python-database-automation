"""Run prediction for a single fixture and save results."""
import json
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.predict_fixture import predict_fixture

fixture_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1378100

print(f"Running prediction for fixture {fixture_id}...")
result = predict_fixture(fixture_id)

# Save to file
out_path = f"_prediction_{fixture_id}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, default=str)

print(f"Saved to {out_path}")

# Print summary
print("\n" + "=" * 60)
print(f"FIXTURE: {fixture_id}")
print("=" * 60)

# Reliability & coverage
reliability = result.get("reliability", {})
coverage = result.get("coverage", {})
print(f"\nReliability: {reliability.get('grade', '?')} ({reliability.get('score', 0)})")
print(f"Coverage: {coverage.get('features_pct', 0):.1%}")

# Bet signals
bets = result.get("bet_signals", [])
if bets:
    print(f"\nVALUE BETS ({len(bets)}):")
    for b in bets:
        print(
            f"  [{b.get('market')}] {b.get('action')} "
            f"| EV={b.get('expected_value', 0):.3f} "
            f"| odds={b.get('decimal_odds', 0)} "
            f"| Kelly={b.get('kelly_stake', 0):.2f}"
        )
else:
    print("\nNo value bets found")

# Predictions summary (targets)
targets = result.get("targets", {})
print(f"\nPREDICTIONS ({len(targets)} targets):")
for target, probs in sorted(targets.items()):
    if isinstance(probs, dict) and probs:
        best = max(probs, key=probs.get)
        prob = probs.get(best, 0)
        print(f"  {target}: {best} ({prob:.1%})")
