from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from bot.core.types import Venue


@dataclass
class MarketClockConfig:
    allow_extended_hours: bool = False
    market_tz: str = "America/New_York"
    regular_open: time = time(9, 30)
    regular_close: time = time(16, 0)


class MarketClock:
    def __init__(self, config: MarketClockConfig) -> None:
        self.config = config
        self._tz = ZoneInfo(config.market_tz)

    def is_market_open(self, venue: Venue, now_utc: datetime) -> bool:
        if venue == Venue.CRYPTO:
            return True
        localized = now_utc.astimezone(self._tz)
        if self.config.allow_extended_hours:
            return True
        return self.config.regular_open <= localized.time() <= self.config.regular_close
