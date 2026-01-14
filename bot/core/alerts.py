from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen


@dataclass
class TelegramConfig:
    enabled: bool
    bot_token: str
    chat_id: str


class TelegramAlerter:
    def __init__(self, config: TelegramConfig) -> None:
        self.config = config

    def send(self, message: str) -> None:
        if not self.config.enabled:
            return
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = json.dumps({"chat_id": self.config.chat_id, "text": message}).encode("utf-8")
        request = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(request) as _:
            return
