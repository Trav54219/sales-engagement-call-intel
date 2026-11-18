"""Example sequence used by the CLI and README (fictional copy)."""
from datetime import date

from .calendar import SendWindow
from .sequence import Sequence, Step, Variant

def demo_sequence() -> Sequence:
    return Sequence(
        name="Demo outbound",
        window=SendWindow(),
        holidays=frozenset({date(2026, 11, 26)}),
        steps=(
            Step("intro", 0, (
                Variant("A", "Quick question on forecasting", "Hi {{first_name}}, how do you build your forecast today?"),
                Variant("B", "Forecast spreadsheets", "Hi {{first_name}}, are forecasts still spreadsheet-based?"))),
            Step("bump", 2, (Variant("A", "Re: Quick question on forecasting", "Floating this back up."),)),
            Step("value", 3, (
                Variant("A", "A 2-minute idea", "One way teams cut the Friday export."),
                Variant("B", "Idea for your Friday export", "Teams often replace the manual export with a live view."))),
            Step("breakup", 4, (Variant("A", "Close the loop?", "Should I close this out?"),)),
        ),
    )
