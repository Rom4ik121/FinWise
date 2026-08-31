"""Application configuration, paths, and shared constants."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

try:
    from platformdirs import user_data_dir
except ImportError:  # pragma: no cover - fallback when platformdirs is absent
    user_data_dir = None  # type: ignore[assignment]


from lib.core.color_palette import PALETTE_COLORS

APP_NAME: Final[str] = "finanse"
APP_AUTHOR: Final[str] = "finanse"

DEFAULT_CURRENCY: Final[str] = "RUB"
DEFAULT_THEME: Final[str] = "dark"
DEFAULT_LANGUAGE: Final[str] = "ru"
DEFAULT_UI_STYLE: Final[str] = "neon"
KNOWN_UI_STYLES: Final[tuple[str, ...]] = ("classic", "neon")
DEFAULT_EXCHANGE_UPDATE_INTERVAL_MINUTES: Final[int] = 60

# Money precision
MONEY_QUANTIZE: Final[str] = "0.01"
CRYPTO_MONEY_QUANTIZE: Final[str] = "0.00000001"
# Well-known crypto tickers (display / ledger precision).
CRYPTO_CURRENCY_CODES: Final[frozenset[str]] = frozenset(
    {
        "BTC",
        "ETH",
        "USDT",
        "USDC",
        "BNB",
        "XRP",
        "SOL",
        "ADA",
        "DOGE",
        "TON",
        "TRX",
        "LTC",
        "DOT",
        "MATIC",
        "AVAX",
        "SHIB",
        "LINK",
        "ATOM",
        "UNI",
        "XMR",
        "BCH",
        "NEAR",
        "APT",
        "ARB",
        "OP",
        "SUI",
        "PEPE",
        "WETH",
        "WBTC",
    }
)
# Exchange rates need many decimals (e.g. UZS→BTC can be ~1e-12).
FIAT_RATE_QUANTIZE: Final[str] = "0.00000000000001"
CRYPTO_RATE_QUANTIZE: Final[str] = "0.00000000000001"

DEFAULT_CATEGORIES: Final[tuple[str, ...]] = (
    "Еда",
    "Транспорт",
    "Жильё",
    "Коммунальные",
    "Здоровье",
    "Развлечения",
    "Одежда",
    "Образование",
    "Зарплата",
    "Подарки",
    "Накопление",
    "Инвестиции",
    "Прочее",
)

# Display metadata for account UI (icons / palette keys).
# Currency / crypto glyphs use keys ``ccy_USD``, ``ccy_BTC`` (built from catalog).
ACCOUNT_ICON_GROUPS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "icon_group.finance",
        (
            "payments",
            "account_balance",
            "savings",
            "account_balance_wallet",
            "wallet",
            "safe",
            "credit_card",
            "percent",
            "bar_chart",
            "show_chart",
            "trending_up",
            "pie_chart",
            "smartphone",
            "atm",
            "contactless",
            "qr_code_2",
            "currency_exchange",
            "calculate",
            "autorenew",
            "receipt_long",
            "request_quote",
            "price_check",
            "point_of_sale",
            "monetization_on",
            "paid",
            "token",
            "generating_tokens",
            "sell",
        ),
    ),
    (
        "icon_group.cards",
        (
            "credit_card",
            "contactless",
            "account_balance_wallet",
            "wallet",
            "payments",
            "paid",
            "redeem",
            "card_giftcard",
            "loyalty",
            "style",
            "lock",
        ),
    ),
)

# Flat thematic icons (currency glyphs appended at runtime in the picker).
ACCOUNT_ICONS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        icon for _label, icons in ACCOUNT_ICON_GROUPS for icon in icons
    )
)

ACCOUNT_COLORS: Final[tuple[str, ...]] = PALETTE_COLORS

# Same expanded palette for categories (legacy custom hex values still work).
CATEGORY_COLORS: Final[tuple[str, ...]] = PALETTE_COLORS

# Grouped icon keys for the category picker (label key → icons).
# Keys are stored in DB; mapped to Flet Icons in presentation.icon_registry.
CATEGORY_ICON_GROUPS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "icon_group.finance",
        (
            "account_balance",
            "emoji_events",
            "calculate",
            "credit_card",
            "attach_money",
            "euro",
            "paid",
            "bar_chart",
            "mail",
            "show_chart",
            "savings",
            "payments",
            "handshake",
            "percent",
            "account_balance_wallet",
            "autorenew",
            "work",
            "public",
            "receipt_long",
            "monetization_on",
            "currency_exchange",
            "currency_bitcoin",
            "trending_up",
            "request_quote",
            "price_check",
            "point_of_sale",
            "atm",
            "contactless",
            "qr_code_2",
            "safe",
            "pie_chart",
            "sell",
        ),
    ),
    (
        "icon_group.transport",
        (
            "directions_boat",
            "propane_tank",
            "directions_car",
            "local_car_wash",
            "sensors",
            "tram",
            "alt_route",
            "paragliding",
            "train",
            "moped",
            "two_wheeler",
            "local_parking",
            "policy",
            "local_gas_station",
            "electric_scooter",
            "local_taxi",
            "subway",
            "directions_bus",
            "flight",
            "electric_car",
            "rv_hookup",
            "gavel",
            "local_shipping",
            "tire_repair",
            "flight_takeoff",
            "directions_bike",
            "pedal_bike",
            "directions_walk",
            "sailing",
            "map",
            "ev_station",
            "car_repair",
            "traffic",
            "airport_shuttle",
            "electric_bike",
        ),
    ),
    (
        "icon_group.shopping",
        (
            "shopping_cart",
            "photo_camera",
            "checkroom",
            "sports_esports",
            "local_shipping",
            "dry_cleaning",
            "local_florist",
            "storefront",
            "smartphone",
            "laptop",
            "card_giftcard",
            "diamond",
            "local_offer",
            "shopping_bag",
            "shopping_basket",
            "soap",
            "toys",
            "local_laundry_service",
            "watch",
            "work",
            "face",
            "battery_full",
            "power",
            "cleaning_services",
            "coffee_maker",
            "inventory_2",
            "store",
            "local_grocery_store",
            "local_mall",
            "sell",
            "redeem",
            "devices",
            "videogame_asset",
            "camera_alt",
        ),
    ),
    (
        "icon_group.food",
        (
            "sports_bar",
            "lunch_dining",
            "set_meal",
            "coffee",
            "bakery_dining",
            "local_drink",
            "egg_alt",
            "icecream",
            "kebab_dining",
            "local_pizza",
            "shopping_basket",
            "cookie",
            "cake",
            "eco",
            "water_drop",
            "liquor",
            "local_cafe",
            "egg",
            "grass",
            "kitchen",
            "restaurant",
            "fastfood",
            "local_bar",
            "ramen_dining",
            "dinner_dining",
            "takeout_dining",
            "brunch_dining",
            "restaurant_menu",
            "breakfast_dining",
            "emoji_food_beverage",
            "wine_bar",
            "outdoor_grill",
            "rice_bowl",
            "tapas",
            "local_dining",
            "blender",
        ),
    ),
    (
        "icon_group.home",
        (
            "ac_unit",
            "format_paint",
            "home",
            "chair",
            "light",
            "apartment",
            "sanitizer",
            "cleaning_services",
            "dry_cleaning",
            "computer",
            "local_florist",
            "vpn_key",
            "image",
            "soup_kitchen",
            "hardware",
            "push_pin",
            "wc",
            "local_laundry_service",
            "checkroom",
            "chair_alt",
            "table_restaurant",
            "bed",
            "weekend",
            "iron",
            "handyman",
            "cottage",
            "electrical_services",
            "lightbulb",
            "water_drop",
            "wifi",
            "bolt",
            "local_fire_department",
            "plumbing",
            "kitchen",
            "build",
            "countertops",
            "bathtub",
            "shower",
            "yard",
            "deck",
            "microwave",
            "coffee_maker",
            "king_bed",
            "single_bed",
            "hot_tub",
            "garage",
            "roofing",
            "other_houses",
            "villa",
            "house",
            "carpenter",
            "home_repair_service",
            "construction",
        ),
    ),
    (
        "icon_group.health",
        (
            "vaccines",
            "healing",
            "medical_services",
            "spa",
            "visibility",
            "monitor_heart",
            "eco",
            "health_and_safety",
            "favorite",
            "accessibility_new",
            "local_hospital",
            "medication",
            "psychology",
            "emergency",
            "bloodtype",
            "self_improvement",
            "fitness_center",
            "masks",
            "medication_liquid",
            "hearing",
            "accessible",
            "wheelchair_pickup",
        ),
    ),
    (
        "icon_group.beauty",
        (
            "face_retouching_natural",
            "face",
            "face_3",
            "spa",
            "content_cut",
            "dry",
            "colorize",
            "soap",
            "sanitizer",
            "brush",
            "palette",
            "checkroom",
            "self_improvement",
            "diamond",
            "watch",
            "dry_cleaning",
        ),
    ),
    (
        "icon_group.entertainment",
        (
            "local_bar",
            "celebration",
            "restaurant",
            "casino",
            "sports_esports",
            "groups",
            "gps_fixed",
            "confirmation_number",
            "mic",
            "movie",
            "music_note",
            "theater_comedy",
            "stadium",
            "phishing",
            "headphones",
            "movie_filter",
            "menu_book",
            "nightlife",
            "videogame_asset",
            "sports_soccer",
            "sports_basketball",
            "sports_tennis",
            "camera_alt",
            "photo_camera",
            "live_tv",
            "piano",
            "theaters",
            "local_movies",
            "videocam",
            "palette",
            "brush",
        ),
    ),
    (
        "icon_group.bills",
        (
            "receipt_long",
            "description",
            "car_repair",
            "local_fire_department",
            "eco",
            "lightbulb",
            "smartphone",
            "phone",
            "home",
            "lock",
            "security",
            "water_drop",
            "percent",
            "delete",
            "language",
            "wifi",
            "bolt",
            "touch_app",
            "workspace_premium",
            "local_hospital",
            "hvac",
            "verified",
            "electrical_services",
            "public",
            "request_quote",
            "gavel",
            "router",
            "cell_tower",
            "water",
            "recycling",
            "article",
            "assignment",
            "fact_check",
            "policy",
        ),
    ),
    (
        "icon_group.sport",
        (
            "sports_basketball",
            "directions_bike",
            "emoji_events",
            "emoji_people",
            "sports",
            "kayaking",
            "paragliding",
            "directions_run",
            "kitesurfing",
            "sports_score",
            "downhill_skiing",
            "fitness_center",
            "sports_bar",
            "pool",
            "sports_gymnastics",
            "sports_martial_arts",
            "self_improvement",
            "sports_tennis",
            "sports_soccer",
            "roller_skating",
            "ice_skating",
            "surfing",
            "snowboarding",
            "sports_golf",
            "golf_course",
            "sports_volleyball",
            "sports_baseball",
            "sports_handball",
            "sports_football",
            "sports_motorsports",
            "skateboarding",
            "scuba_diving",
            "pedal_bike",
        ),
    ),
    (
        "icon_group.leisure",
        (
            "sailing",
            "outdoor_grill",
            "festival",
            "hotel",
            "terrain",
            "wb_sunny",
            "beach_access",
            "luggage",
            "pool",
            "park",
            "confirmation_number",
            "forest",
            "hiking",
            "cabin",
            "umbrella",
            "nightlight",
            "museum",
            "landscape",
            "wb_twilight",
            "bungalow",
        ),
    ),
    (
        "icon_group.education",
        (
            "notifications_active",
            "menu_book",
            "workspace_premium",
            "school",
            "computer",
            "military_tech",
            "emoji_events",
            "calculate",
            "account_balance",
            "architecture",
            "science",
            "auto_stories",
            "history_edu",
            "draw",
            "library_books",
            "biotech",
            "cast_for_education",
        ),
    ),
    (
        "icon_group.work",
        (
            "work",
            "business_center",
            "laptop",
            "computer",
            "smartphone",
            "phone_android",
            "cloud",
            "mail",
            "print",
            "badge",
            "co_present",
            "supervisor_account",
        ),
    ),
    (
        "icon_group.family",
        (
            "child_care",
            "boy",
            "pets",
            "escalator_warning",
            "baby_changing_station",
            "man",
            "cruelty_free",
            "family_restroom",
            "girl",
            "home",
            "smart_toy",
            "front_hand",
            "child_friendly",
            "elderly",
            "flutter_dash",
            "pest_control",
            "bug_report",
            "crib",
            "toys",
            "school",
            "volunteer_activism",
            "search",
            "pan_tool",
            "groups",
            "person",
            "face",
            "handshake",
            "diversity_3",
            "diversity_1",
            "woman",
            "elderly_woman",
            "people",
        ),
    ),
    (
        "icon_group.farm",
        (
            "agriculture",
            "yard",
            "grass",
            "compost",
            "park",
            "spa",
            "inventory_2",
            "hardware",
            "forest",
            "eco",
            "water_drop",
            "pest_control",
        ),
    ),
    (
        "icon_group.travel",
        (
            "flight",
            "luggage",
            "beach_access",
            "park",
            "local_florist",
            "eco",
            "wb_sunny",
            "nightlight",
            "umbrella",
            "forest",
            "hiking",
            "museum",
            "cabin",
            "terrain",
            "sailing",
            "hotel",
            "map",
            "public",
        ),
    ),
    (
        "icon_group.other",
        (
            "category",
            "category_outlined",
            "smoking_rooms",
            "info",
            "help",
            "star",
            "church",
            "mosque",
            "synagogue",
            "temple_buddhist",
            "temple_hindu",
            "volunteer_activism",
            "nightlight",
            "favorite",
            "public",
            "home",
            "emoji_events",
            "military_tech",
            "bolt",
            "more_horiz",
            "apps",
        ),
    ),
)

# Flat list kept for seeds / validation / fallbacks.
CATEGORY_ICONS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        icon for _label, icons in CATEGORY_ICON_GROUPS for icon in icons
    )
)

# Canonical ledger category for goal contributions (always stored in Russian seed form;
# UI localizes via localize_category_name / category.savings).
DEFAULT_SAVINGS_CATEGORY: Final[str] = "Накопление"
# Historical / mistaken localized names still treated as the same savings bucket.
SAVINGS_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        DEFAULT_SAVINGS_CATEGORY,
        "Savings",
        "Jamg‘arma",  # U+2018
        "Jamg'arma",  # ASCII apostrophe
    }
)


def normalize_savings_category(name: str | None) -> str:
    """Map any savings alias (or empty) to :data:`DEFAULT_SAVINGS_CATEGORY`."""
    link = (name or "").strip()
    if not link or link in SAVINGS_CATEGORIES:
        return DEFAULT_SAVINGS_CATEGORY
    return link

# Default seed: (name, kind, icon, color)
DEFAULT_CATEGORY_SEED: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("Еда", "expense", "restaurant", "#EF6C00"),
    ("Транспорт", "expense", "directions_car", "#1565C0"),
    ("Жильё", "expense", "home", "#5D4037"),
    ("Коммунальные", "expense", "electrical_services", "#00838F"),
    ("Здоровье", "expense", "local_hospital", "#C62828"),
    ("Развлечения", "expense", "movie", "#6A1B9A"),
    ("Одежда", "expense", "checkroom", "#AD1457"),
    ("Образование", "expense", "school", "#283593"),
    ("Зарплата", "income", "payments", "#2E7D32"),
    ("Подарки", "both", "card_giftcard", "#C0CA33"),
    ("Накопление", "both", "savings", "#00897B"),
    ("Инвестиции", "both", "trending_up", "#4527A0"),
    ("Прочее", "both", "category", "#546E7A"),
)


def _is_android() -> bool:
    """Detect Android (packaged Flet / Serious Python)."""
    if sys.platform == "android":
        return True
    plat = os.environ.get("FLET_PLATFORM", "").strip().lower()
    if plat == "android" or os.environ.get("FLET_ANDROID"):
        return True
    if sys.platform != "linux":
        return False
    try:
        home = Path.home().as_posix()
    except Exception:  # noqa: BLE001
        return False
    return "/data/user/" in home or "/data/data/" in home


def _is_ios() -> bool:
    """Detect iOS (incl. Flet iOS builds via Serious Python, Python 3.14).

    Do not call ``os.path.isdir`` on ``/private/var/mobile/Containers`` or
    ``Path.home().resolve()``: the sandbox raises ``PermissionError`` (and
    ``isdir`` then returns False), so those checks miss a real iPhone.
    """
    if sys.platform == "ios":
        return True
    if os.environ.get("FTC_DEVICE") or os.environ.get("FLET_IOS"):
        return True
    if sys.platform != "darwin":
        return False
    try:
        home = Path.home().as_posix()
    except Exception:  # noqa: BLE001
        return False
    # Symlink form ``/var/mobile/Containers/…`` or resolved
    # ``/private/var/mobile/Containers/…``.
    return "/var/mobile/Containers/" in home


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw)


def _try_mkdir(path: Path) -> Path | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".finanse_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        return None


def _android_data_dir() -> Path:
    """Writable app-private dir on Android (never bare ``/data``).

    Packaged Flet exposes ``FLET_APP_STORAGE_DATA`` (see ``StoragePaths``).
    ``Path.home()`` is sometimes just ``/data``, which is not writable and
    used to raise ``PermissionError: '/data/finanse'`` on boot.
    """
    candidates: list[Path] = []
    for key in (
        "FLET_APP_STORAGE_DATA",
        "FLET_APP_STORAGE",
        "FILESDIR",
        "ANDROID_APP_DATA",
    ):
        base = _env_path(key)
        if base is not None:
            candidates.append(base / APP_NAME)

    try:
        home = Path.home()
    except Exception:  # noqa: BLE001
        home = None
    if home is not None:
        home_s = home.as_posix().rstrip("/")
        # Real app sandboxes only — reject bare /data (Errno 13).
        if home_s not in ("", "/", "/data") and (
            "/data/user/" in home_s or "/data/data/" in home_s
        ):
            candidates.append(home / APP_NAME)
            candidates.append(home / "files" / APP_NAME)

    # Last-resort package paths used by Serious Python / Flutter.
    pkg = "com.finanse.app"
    candidates.extend(
        [
            Path(f"/data/user/0/{pkg}/files") / APP_NAME,
            Path(f"/data/data/{pkg}/files") / APP_NAME,
            Path(f"/data/user/0/{pkg}/app_flutter") / APP_NAME,
            Path(f"/data/data/{pkg}/app_flutter") / APP_NAME,
        ]
    )

    seen: set[str] = set()
    for path in candidates:
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        ok = _try_mkdir(path)
        if ok is not None:
            return ok

    raise PermissionError(
        "No writable Android data directory "
        "(set FLET_APP_STORAGE_DATA or install a packaged build)"
    )


def _default_data_dir() -> Path:
    """Resolve the application data directory under the user profile.

    On iOS the app sandbox only allows writing inside its own container:
    ``platformdirs.user_data_dir()`` would resolve to ``~/.local/share/finanse``
    whose ``.local`` segment cannot be created (``PermissionError``) — and it
    would not be backed up by iCloud anyway. Use ``Library/Application Support``
    inside the container instead.
    """
    if _is_ios():
        for key in ("FLET_APP_STORAGE_DATA", "FLET_APP_STORAGE", "FILESDIR"):
            raw = os.environ.get(key, "").strip()
            if raw:
                path = Path(raw) / APP_NAME
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    return path
                except OSError:
                    continue
        path = Path.home() / "Library" / "Application Support" / APP_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    if _is_android():
        return _android_data_dir()

    if user_data_dir is not None:
        path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    else:
        path = Path.home() / f".{APP_NAME}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(slots=True)
class NotificationSettings:
    """User-facing notification preferences."""

    enabled: bool = True
    subscription_reminders: bool = True
    debt_reminders: bool = True
    goal_milestones: bool = True
    low_balance_threshold: float | None = None


@dataclass(slots=True)
class AppConfig:
    """Runtime application settings and filesystem paths.

    Paths default to a per-user data directory (platformdirs when available,
    otherwise ``~/.finanse``).
    """

    data_dir: Path = field(default_factory=_default_data_dir)
    default_currency: str = DEFAULT_CURRENCY
    theme: str = DEFAULT_THEME
    language: str = DEFAULT_LANGUAGE
    exchange_update_interval_minutes: int = DEFAULT_EXCHANGE_UPDATE_INTERVAL_MINUTES
    notifications: NotificationSettings = field(default_factory=NotificationSettings)

    # API key placeholders (filled from env / secrets store later)
    exchange_rate_api_key: str | None = None
    crypto_api_key: str | None = None
    openai_api_key: str | None = None

    @property
    def db_path(self) -> Path:
        """SQLite database file path."""
        return self.data_dir / "finanse.db"

    @property
    def database_url(self) -> str:
        """SQLAlchemy SQLite URL for the local database."""
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def backup_dir(self) -> Path:
        """Directory for database backups."""
        path = self.data_dir / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def export_dir(self) -> Path:
        """Directory for exported reports and data dumps."""
        path = self.data_dir / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_dir(self) -> Path:
        """Directory for application log files."""
        path = self.data_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_directories(self) -> None:
        """Create data, backup, export, and log directories if missing."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def get_default_config() -> AppConfig:
    """Build a default :class:`AppConfig` with directories ensured."""
    config = AppConfig()
    config.ensure_directories()
    return config
