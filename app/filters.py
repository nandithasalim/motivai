import re

MILESTONE_STREAKS = [7, 14, 21, 30, 60, 100]
BANNED_WORDS = ["hate", "kill", "stupid", "idiot", "terrible", "awful"]

# \b at the start: "kill"/"killed" match, but "skill" does not
BANNED_PATTERN = re.compile(r"\b(?:" + "|".join(BANNED_WORDS) + r")", re.IGNORECASE)


def content_filter(text: str) -> bool:
    return bool(BANNED_PATTERN.search(text))


def get_model(streak_count: int) -> str:
    if streak_count in MILESTONE_STREAKS:
        return "gpt-4o"
    return "gpt-4o-mini"