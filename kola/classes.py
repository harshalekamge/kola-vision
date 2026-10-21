"""Single source of truth for the UI element classes Kola's vision model detects.

The ORDER matters: the class id in YOLO label files is the index in this list.
Do not reorder after you have collected data (append new classes at the end).

Classes 0–11 were in the first model (v1). Classes 12–23 were added in v2
(more sidebar destinations); a v1 model still works, since Kola falls back to
reading the label with OCR for any class the loaded model doesn't know.
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
    # --- v2: more sidebar destinations ---
    "your_channel",    # 12 sidebar (You): Your channel
    "playlists",       # 13 sidebar (You): Playlists
    "music",           # 14 sidebar (Explore): Music
    "gaming",          # 15 sidebar (Explore): Gaming
    "playables",       # 16 sidebar (Explore): Playables
    "premium",         # 17 sidebar (More from YouTube): YouTube Premium
    "youtube_music",   # 18 sidebar (More from YouTube): YouTube Music
    "youtube_kids",    # 19 sidebar (More from YouTube): YouTube Kids
    "report_history",  # 20 sidebar (bottom): Report history
    "liked_videos",    # 21 sidebar (You): Liked videos
    "your_videos",     # 22 sidebar (You): Your videos (opens YouTube Studio)
    "downloads",       # 23 sidebar (You): Downloads
]

# Sidebar destinations, top to bottom as they appear in the expanded sidebar.
# Kola uses this order to decide whether to scroll the sidebar up or down.
SIDEBAR_ORDER = [
    "home", "shorts", "subscriptions",
    "your_channel", "history", "playlists", "watch_later", "liked_videos", "your_videos", "downloads",
    "music", "gaming", "playables",
    "premium", "youtube_music", "youtube_kids",
    "report_history",
]
SIDEBAR_CLASSES = set(SIDEBAR_ORDER)

# The collapsed sidebar (mini guide) only shows these (Downloads appears there on some accounts).
# Seeing any other sidebar item means the sidebar is already expanded.
MINI_GUIDE_CLASSES = {"home", "shorts", "subscriptions", "downloads"}

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
    "your_channel": "Your channel", "playlists": "Playlists", "music": "Music", "gaming": "Gaming",
    "playables": "Playables", "premium": "YouTube Premium", "youtube_music": "YouTube Music",
    "youtube_kids": "YouTube Kids", "report_history": "Report history",
    "liked_videos": "Liked videos", "your_videos": "Your videos", "downloads": "Downloads",
}
