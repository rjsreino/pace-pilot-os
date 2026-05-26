import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.sentiment import detect_sentiment

test_phrases = [
    # Pain / injury
    ("i sprained my ankle i think", "pain"),
    ("my foot has plantar fasciitis", "pain"),
    ("tendonitis in my achilles is acting up", "pain"),
    ("knees are aching and stiff", "pain"),
    ("felt a sudden pop in my calf", "pain"),
    ("pulled hamstring", "pain"),
    ("shin splints are hurting", "pain"),
    ("stiff as a board", "pain"),
    ("sharp stabbing knee pain", "pain"),
    
    # Illness / sickness (mapping to fatigue)
    ("i have a fever and cough", "fatigue"),
    ("feeling sick and dizzy", "fatigue"),
    ("i think I have the flu", "fatigue"),
    ("headache and congested", "fatigue"),
    ("under the weather", "fatigue"),
    ("bad cold runny nose", "fatigue"),
    
    # Fatigue
    ("exhausted and tired", "fatigue"),
    ("feeling sluggish and flat", "fatigue"),
    ("drained and sleepy", "fatigue"),
    ("run down", "fatigue"),
    ("worn out", "fatigue"),
    
    # High energy
    ("ready to roll", "high_energy"),
    ("never better", "high_energy"),
    ("feel like a million bucks", "high_energy"),
    ("no pain", "high_energy"),
    ("zero pain", "high_energy"),
    ("nothing hurts", "high_energy"),
    ("good to go", "high_energy"),
    ("not tired at all", "high_energy"),
    ("energized and fresh", "high_energy"),
    ("strong and excited", "high_energy"),
]

print("=== Running Sentiment Tests ===")
passed = 0
failed = 0
for phrase, expected in test_phrases:
    result = detect_sentiment(phrase)
    if result == expected:
        print(f"[PASS] '{phrase}' -> {result}")
        passed += 1
    else:
        print(f"[FAIL] '{phrase}' -> {result} (Expected: {expected})")
        failed += 1

print(f"\nResults: {passed} passed, {failed} failed.")
sys.exit(failed)
