from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from config.paths import REPO_ROOT

ROOT = REPO_ROOT


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    paper: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip() and self.secret_key.strip())


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    paper_raw = os.getenv("ALPACA_PAPER", "true").strip().lower()
    return Settings(
        api_key=os.getenv("ALPACA_API_KEY", "").strip(),
        secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
        paper=paper_raw in {"1", "true", "yes", "y"},
    )
