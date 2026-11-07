"""POST /ask: one question to the configured provider, to check it works."""
from __future__ import annotations

from pydantic import BaseModel

from services.playground.ask_service import AskResult, AskService


class AskRequest(BaseModel):
    question: str = "What is 5+2?"


class AskController:
    def __init__(self, service: AskService) -> None:
        self.service = service

    def store(self, payload: AskRequest) -> AskResult:
        return self.service.ask(payload.question)
