from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from bot.core.types import AccountSummary, Position


@dataclass
class PortfolioSnapshot:
    account: AccountSummary
    positions: List[Position]

    def positions_by_symbol(self) -> Dict[str, Position]:
        return {position.symbol: position for position in self.positions}
