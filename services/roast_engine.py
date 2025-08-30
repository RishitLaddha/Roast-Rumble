# services/roast_engine.py
import random
import re
from typing import Dict, Any, List

# We DO NOT construct the model here.
# app.py passes a ready GeminiRoaster instance in `run_duel(...)`.

def _get_bio(p: Dict[str, Any]) -> str:
    """Be tolerant to different persona key names."""
    return (
        p.get("bio")
        or p.get("persona")
        or p.get("persona_bio")
        or p.get("description")
        or ""
    )

_word_re = re.compile(r"[A-Za-z']+")

def _punch_score(line: str) -> float:
    """
    Tiny, deterministic heuristic to nudge the meter:
    - more punctuation & shortness -> slightly punchier
    - ALL CAPS tokens add a touch
    - bounded 0..1
    """
    if not line:
        return 0.0
    text = line.strip()

    excl = text.count("!")
    qst  = text.count("?")
    dots = text.count("...")

    tokens = _word_re.findall(text)
    caps = sum(1 for t in tokens if len(t) >= 2 and t.isupper())

    length_penalty = max(0.0, (len(text) - 80) / 140.0)  # longer -> less punch

    raw = 0.25 * excl + 0.15 * qst + 0.2 * dots + 0.1 * caps + 0.6
    raw -= 0.6 * length_penalty
    return max(0.0, min(1.0, raw))

def run_duel(
    *,
    roaster,                       # GeminiRoaster instance (from services.gemini_client)
    arena_theme: str,
    persona_a: Dict[str, Any],
    persona_b: Dict[str, Any],
    rounds: int = 3,
    max_words: int = 40,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Orchestrates one duel:
    - Calls Gemini for A then B each round
    - Updates a running 'hype meter' ( -1 .. +1 )
    - Returns events and a final winner label ('A' or 'B')
    """
    rng = random.Random(seed)

    a_name = persona_a.get("name", "Player A")
    b_name = persona_b.get("name", "Player B")
    a_bio  = _get_bio(persona_a)
    b_bio  = _get_bio(persona_b)

    meter = 0.0
    events: List[Dict[str, Any]] = []

    for _ in range(max(1, rounds)):
        # Speaker A roasts B
        a_line = roaster.roast_line(
            character_name=a_name,
            character_persona_bio=a_bio,
            opponent_name=b_name,
            opponent_persona_bio=b_bio,
            arena_theme=arena_theme,
            max_words=max_words,
        )
        # Speaker B roasts A
        b_line = roaster.roast_line(
            character_name=b_name,
            character_persona_bio=b_bio,
            opponent_name=a_name,
            opponent_persona_bio=a_bio,
            arena_theme=arena_theme,
            max_words=max_words,
        )

        # Heuristic scoring + a small random spice (deterministic via seed)
        a_p = _punch_score(a_line)
        b_p = _punch_score(b_line)
        spice = rng.uniform(-0.12, 0.12)

        delta = (b_p - a_p) * 0.40 + spice  # positive -> toward B, negative -> toward A
        meter = max(-1.0, min(1.0, meter + delta))

        events.append({
            "a_line": a_line,
            "b_line": b_line,
            "meter_after": round(meter, 4),
        })

    # Decide winner: never draw. Left side (A) wins when meter <= 0
    winner = "A" if meter <= 0 else "B"

    return {
        "arena": arena_theme,
        "persona_a_name": a_name,
        "persona_b_name": b_name,
        "events": events,
        "winner": winner,
    }
