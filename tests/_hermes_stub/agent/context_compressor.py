"""Just enough of Hermes' ContextCompressor to be a base class for the tests."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class ContextCompressor:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.model = kwargs.get("model", "")
        self.context_length = kwargs.get("context_length", 0) or 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        self.last_prompt_tokens = int(usage.get("prompt_tokens") or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens") or 0)
        self.last_total_tokens = int(usage.get("total_tokens") or 0)

    def update_model(self, *args: Any, **kwargs: Any) -> None:
        self.context_length = int(kwargs.get("context_length") or self.context_length or 0)

    def bind_session_state(self, session_db: Any = None, session_id: Optional[str] = None, **_: Any) -> None:
        self._session_id = session_id
