from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual en UTC (con zona horaria)."""
        ...
