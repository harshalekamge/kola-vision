"""Single source of truth for the UI element classes Kola's vision model detects.

The ORDER matters: the class id in YOLO label files is the index in this list.
Do not reorder after you have collected data (append new classes at the end).
"""

CLASSES = [
    "home",            # 0  sidebar: Home
    "shorts",          # 1  sidebar: Shorts
    "subscriptions",   # 2  sidebar: Subscriptions
    "history",         # 3  sidebar: History
    "watch_later",     # 4  sidebar: Watch later
    "menu_button",     # 5  hamburger (opens / collapses the sidebar)
    "search_box",      # 6  search input
    "search_button",   # 7  magnifying-glass button
    "chip",            # 8  topic filter chip ("All", "Music", "Gaming", ...)
    "video_card",      # 9  a normal video tile (home grid or search result)
    "short_card",      # 10 a vertical card in a Shorts shelf
    "sponsored_card",  # 11 an ad / sponsored tile
]

# Sidebar destinations: if one of these is not visible, Kola opens the menu first.
SIDEBAR_CLASSES = {"home", "shorts", "subscriptions", "history", "watch_later"}

# Elements that appear once per screen: pick the most confident detection
# (protects against look-alikes such as the browser's own address bar).
SINGLETON_CLASSES = SIDEBAR_CLASSES | {"menu_button", "search_box", "search_button"}

# Elements that live in the scrolling feed: if not found, Kola scrolls and looks again.
FEED_CLASSES = {"video_card", "short_card", "sponsored_card"}

FRIENDLY = {
    "home": "Home", "shorts": "Shorts", "subscriptions": "Subscriptions",
    "history": "History", "watch_later": "Watch later", "menu_button": "Menu (≡)",
    "search_box": "Search box", "search_button": "Search button", "chip": "Topic chip",
    "video_card": "Video card", "short_card": "Shorts card", "sponsored_card": "Sponsored card",
}
