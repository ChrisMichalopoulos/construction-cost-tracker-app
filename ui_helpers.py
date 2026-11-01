"""Shared formatting and chart-color constants used across pages."""

# Categorical palette (validated set, fixed order - see dataviz skill reference)
SERIES_BLUE = "#2a78d6"
SERIES_ORANGE = "#eb6834"
SERIES_AQUA = "#1baf7a"
SERIES_YELLOW = "#eda100"
SERIES_MAGENTA = "#e87ba4"
SERIES_GREEN = "#008300"
SERIES_VIOLET = "#6250d6"
SERIES_RED = "#e34948"

CATEGORICAL = [SERIES_BLUE, SERIES_ORANGE, SERIES_AQUA, SERIES_YELLOW,
               SERIES_MAGENTA, SERIES_GREEN, SERIES_VIOLET, SERIES_RED]

# Status palette - reserved for state, never reused as a series color
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_SERIOUS = "#ec835a"
STATUS_CRITICAL = "#d03b3b"

MUTED = "#898781"
GRIDLINE = "#e1e0d9"
MUTED_FILL = "#d9d7cd"  # for "remaining budget" (neutral, not a series)

# Roles used consistently wherever these entities appear on a chart
ROLE_ACTUAL = SERIES_BLUE
ROLE_COMMITTED = SERIES_ORANGE
ROLE_REMAINING = MUTED_FILL
ROLE_OVERRUN = STATUS_CRITICAL

COST_TYPE_COLORS = {
    "Υλικά (Materials)": SERIES_BLUE,
    "Εργατικά (Labor)": SERIES_ORANGE,
    "Εξοπλισμός (Equipment)": SERIES_AQUA,
    "Άλλο (Other)": SERIES_YELLOW,
    "Unassigned": MUTED,
}


def eur(amount) -> str:
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if amount < 0 else ""
    return f"{sign}€{abs(amount):,.2f}"


def pct(numerator, denominator) -> str:
    if not denominator:
        return "-"
    return f"{(numerator / denominator) * 100:,.1f}%"
