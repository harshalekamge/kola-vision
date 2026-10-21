"""Placeholder command parser: plain English -> steps.

This stands in for the language-understanding module until it is connected.
That module only has to produce the same step list (see README "Interface").

Step actions: left_click, right_click, double_click, hover, type, press,
select_all, scroll, wait, wait_for.
"""
import re

# Longer phrases first, so "report history" wins over "history" and "youtube music" over "music".
SIDEBAR_WORDS = [
    ("youtube music", "youtube_music"), ("youtube kids", "youtube_kids"), ("youtube premium", "premium"),
    ("report history", "report_history"), ("your channel", "your_channel"), ("my channel", "your_channel"),
    ("watch later", "watch_later"), ("playlists", "playlists"), ("playables", "playables"),
    ("premium", "premium"), ("gaming", "gaming"), ("music", "music"), ("history", "history"),
    ("subscriptions", "subscriptions"), ("subscription", "subscriptions"),
    ("home", "home"), ("shorts", "shorts"),
]
ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
            "fourth": 3, "4th": 3, "fifth": 4, "5th": 4, "last": -1}
ORD_RE = r"(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)"


def _action(low):
    if "right click" in low or "right-click" in low:
        return "right_click"
    if "double click" in low or "double-click" in low:
        return "double_click"
    if re.search(r"\bhover\b", low):
        return "hover"
    return "left_click"


def _ordinal(text):
    m = re.search(ORD_RE, text)
    return ORDINALS[m.group(1)] if m else 0


def plan(command: str):
    """Returns (steps, explanation). Raises ValueError if not understood."""
    c = command.strip().rstrip(".!")
    low = c.lower()
    act = _action(low)

    # Scenario 2 — search, then optionally play a result
    m = re.search(r"\bsearch(?: youtube)?(?: for)?\s+(.+?)(?:\s*,|\s+and\s+|\s+then\s+|$)", low)
    if m:
        query = c[m.start(1):m.end(1)].strip(" '\"")
        steps = [
            {"action": "left_click", "target": {"type": "search_box"}},
            {"action": "select_all"},
            {"action": "type", "text": query},
            {"action": "left_click", "target": {"type": "search_button"}},
            {"action": "wait_for", "target": {"type": "video_card"}, "timeout": 10},
        ]
        rest = low[m.end():]
        if re.search(r"\b(play|open|watch|click)\b", rest):
            contains = []
            age = re.search(r"\b(\d+|a|an|one)\s+(second|minute|hour|day|week|month|year)s?\s+ago", rest)
            if age:
                contains.append(age.group(0).replace("an ", "1 ").replace("a ", "1 ").replace("one ", "1 "))
            title = re.search(r"\b(?:called|titled|named)\s+(.+)$", c[m.end():], re.I)
            if title:
                contains.append("~" + title.group(1).strip(" '\""))
            tgt = {"type": "video_card"}
            if contains:
                tgt["contains"] = contains
            idx = _ordinal(rest)
            if idx:
                tgt["index"] = idx
            steps.append({"action": "left_click", "target": tgt, "settle": 3})
        return steps, f'Search YouTube for "{query}"' + (" and open the matching video" if len(steps) > 5 else "")

    # Scenario 4 — a button on a sponsored card
    m = re.search(r"(?:click|press|tap)(?: on)?(?: the)?\s+(.+?)\s+button\s+(?:on|in|of)\s+(?:the\s+)?(.+?)\s*(?:ad|advert|advertisement|sponsored(?: card| video)?)\b", low)
    if m:
        label = c[m.start(1):m.end(1)].strip(" '\"")
        sponsor = m.group(2).strip()
        inside = {"type": "sponsored_card"}
        if sponsor and sponsor not in ("the", "this", "that"):
            inside["contains"] = ["~" + sponsor]
        return ([{"action": act, "target": {"type": "text", "text": label, "inside": inside}, "settle": 3}],
                f'{act} the "{label}" button on the {sponsor or "sponsored"} ad')

    # Scenario 5 — Shorts shelf
    if "shorts" in low and (re.search(ORD_RE, low) or "shelf" in low) and re.search(r"\b(play|open|watch|click|video|short)\b", low):
        idx = _ordinal(low)
        tgt = {"type": "short_card"}
        if idx:
            tgt["index"] = idx
        return [{"action": act, "target": tgt, "settle": 3}], f"Open Shorts card #{idx + 1 if idx >= 0 else 'last'}"

    # Scenario 3 — topic chips
    m = re.search(r"(?:switch|change)(?: the)?(?: feed)? to\s+(.+?)(?:\s+(?:videos|chip|feed|category|tab))?$", low) \
        or re.search(r"(?:filter(?: the feed)?(?: by| to)?|show(?: me)?(?: only)?)\s+(.+?)\s+(?:videos|chip|feed|category)$", low) \
        or re.search(r"(?:click|select|open)(?: the)?\s+(.+?)\s+(?:chip|category|filter)$", low)
    if m:
        topic = c[m.start(1):m.end(1)].strip(" '\"")
        return [{"action": act, "target": {"type": "chip", "text": topic}, "settle": 2}], f'Select the "{topic}" chip'

    # Scenario 1 — sidebar destinations
    for word, cls in SIDEBAR_WORDS:
        if re.search(rf"\b{word}\b", low):
            return [{"action": act, "target": {"type": cls}, "settle": 2}], f"{act} sidebar item {cls}"

    # Generic — "click X" clicks visible text X
    m = re.search(r"(?:click|press|tap|open|select|hover(?: over)?)(?: on)?(?: the)?\s+(.+)$", low)
    if m:
        label = c[m.start(1):m.end(1)].strip(" '\"")
        label = re.sub(r"\s+(button|link|tab)$", "", label, flags=re.I)
        return [{"action": act, "target": {"type": "text", "text": "~" + label}, "settle": 2}], f'{act} text "{label}"'

    raise ValueError("Sorry, I don't understand that command yet.")
