import json

import httpx

from app.a2a.models import A2AClientJSONError, AgentCard
from app.config.settings import settings


class A2ACardResolver:
    def __init__(
        self,
        base_url: str,
        agent_card_path: str = "/.well-known/agent.json",
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_card_path = agent_card_path.lstrip("/")
        self.api_key = (
            settings.a2a_api_key
            if api_key is None
            else api_key
        )

    def get_agent_card(self) -> AgentCard:
        timeout = httpx.Timeout(
            settings.a2a_remote_request_timeout_seconds,
            connect=settings.a2a_remote_connect_timeout_seconds,
        )
        with httpx.Client(timeout=timeout) as client:
            headers = (
                {"Authorization": f"Bearer {self.api_key}"}
                if self.api_key
                else {}
            )
            response = client.get(
                self.base_url + "/" + self.agent_card_path,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            try:
                return AgentCard(**response.json())
            except json.JSONDecodeError as e:
                raise A2AClientJSONError(str(e)) from e