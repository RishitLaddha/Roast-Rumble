import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env so CLI/tests work even without app.py doing it first
load_dotenv()

# ----------------------------
# Defaults (can be overridden via __init__)
# ----------------------------
DEFAULT_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
DEFAULT_MODEL_NAME = (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip()

# --------------------------------
# Master prompt (opponent-aware)
# --------------------------------
MASTER_PROMPT = """
You are RoastMaster, the host of a retro arcade-style roast battle game.
Your role: generate ONE roast line for the character currently speaking.

### Context
- Speaker (roasting): {character_name}
- Speaker persona: {character_persona_bio}
- Opponent being roasted: {opponent_name}
- Opponent persona: {opponent_persona_bio}
- Arena theme: {arena_theme}

### Absolute Rules
1. **Target Opponent Only**
   - The roast MUST focus on the opponent ({opponent_name}).
   - Never roast the speaker themselves.
   - Roasts must feel personal, witty, and opponent-specific (use quirks, tropes, or lore from the opponent’s persona).

2. **Stay In-Character**
   - Speaker must deliver the roast fully in their own style, tone, and quirks.
   - Draw only from the persona description provided for {character_name}.
   - Avoid deep or niche lore; keep references common and obvious.

3. **Keep It Short & Punchy**
   - Maximum {max_words} words.
   - 1–2 sentences only.

4. **Arena Tie-Ins (Optional)**
   - If it fits naturally, weave in a reference to the current arena theme ({arena_theme}).

5. **Rating & Safety (PG-16)**
   - Allowed: mild swears (e.g., “hell”, “crap”), spicy sarcasm, light innuendo.
   - Not allowed: slurs, graphic/sexual content, hate speech, targeting real people, serious health/violence/politics/religion.
   - Keep it playful and fictional.

6. **Simple Vocab, Easy to Read**
   - Use everyday words. No complex, fancy, or academic terms.
   - Avoid long metaphors or stacked clauses. Be clear and direct.

7. **Strict Output Format**
   - Output ONLY the roast line.
   - No explanations, labels, or quotation marks.
"""

class GeminiRoaster:
    """
    Small wrapper around the Gemini model for roast lines.

    Accepts explicit api_key/model_name, or falls back to .env:
      GEMINI_API_KEY, GEMINI_MODEL
    """

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.api_key = (api_key or DEFAULT_API_KEY or "").strip()
        self.model_name = (model_name or DEFAULT_MODEL_NAME or "").strip()

        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set (or empty). Check your .env (no spaces around '=').")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

    # -------------- helpers --------------
    def _clean_and_clip(self, text: str, max_words: int) -> str:
        """Ensure one line, no quotes/labels, clipped to word budget."""
        line = (text or "").strip()
        line = line.replace("\n", " ").replace("—", "-")

        # Strip a leading "Speaker:" label if the model adds one
        if ":" in line and len(line.split(":", 1)[0].split()) <= 3:
            maybe_label, rest = line.split(":", 1)
            if all(ch.isalnum() or ch in " .-'_"
                   for ch in maybe_label.strip()):
                line = rest.strip()

        # Strip surrounding quotes if present
        if line.startswith(("\"", "“", "‘")) and line.endswith(("\"", "”", "’")):
            line = line[1:-1].strip()

        # Word budget
        words = line.split()
        if len(words) > max_words:
            line = " ".join(words[:max_words])
            if not line.endswith((".", "!", "?")):
                line += "…"
        return line

    # -------------- main API --------------
    def roast_line(
        self,
        *,
        character_name: str,
        character_persona_bio: str,
        opponent_name: str,
        opponent_persona_bio: str,
        arena_theme: str,
        max_words: int = 26,
        temperature: float = 0.9,
    ) -> str:
        """Generate one roast line with strict controls."""
        prompt = MASTER_PROMPT.format(
            character_name=character_name,
            character_persona_bio=character_persona_bio,
            opponent_name=opponent_name,
            opponent_persona_bio=opponent_persona_bio,
            arena_theme=arena_theme,
            max_words=max_words,
        )

        gen_cfg = {
            "temperature": float(temperature),
            "max_output_tokens": max(48, max_words * 2),
        }

        # Simple retries
        for _ in range(3):
            try:
                resp = self.model.generate_content(
                    prompt,
                    generation_config=gen_cfg,
                    safety_settings={},  # defaults are fine; we also constrain via prompt
                )
                text = getattr(resp, "text", "") or ""
                line = self._clean_and_clip(text, max_words)
                if not line:
                    continue

                # Final self-targeting guard: if it talks about self w/o opponent,
                # try again.
                lowered = line.lower()
                if any(tok in lowered for tok in [" i ", " me ", " my ", " myself "]) and (
                    opponent_name.lower() not in lowered
                ):
                    continue

                return line
            except Exception:
                # try again
                pass

        # Fallback (safe, opponent-mentioned)
        return f"{opponent_name}, even the arena lights dim out of secondhand embarrassment."
