"""Provider tests with the network call replaced, using each SDK's real types."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from services.ai.attachments import Document
from services.ai.providers.base import ProviderRequest
from services.control_testing.data import TestStepList

REQUEST = ProviderRequest(
    agent="test_steps",
    instructions="System prompt",
    prompt="Produce the test steps.",
    attachments=[Document(data=b"%PDF-1.4", title="Control details: cd.pdf")],
    model="some-model",
    max_tokens=1000,
    temperature=0,
    output_schema=TestStepList,
)
ANSWER = '{"steps": []}'


class GeminiProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        from google.genai import types

        from services.ai.providers.gemini import GeminiProvider

        self.types = types
        with mock.patch("google.genai.Client"):
            self.provider = GeminiProvider(project="p", location="europe-west4")

    def answer(self, finish_reason):
        types = self.types
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(role="model", parts=[types.Part(text=ANSWER)]),
                    finish_reason=finish_reason,
                )
            ],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5
            ),
            model_version="gemini-2.5-pro-001",
        )

    def test_sends_documents_schema_and_limits(self) -> None:
        generate = self.provider.client.models.generate_content
        generate.return_value = self.answer(self.types.FinishReason.STOP)

        response = self.provider.prompt(REQUEST)

        call = generate.call_args.kwargs
        self.assertEqual(call["model"], "some-model")
        parts = call["contents"][0].parts
        self.assertEqual(parts[0].text, "Document: Control details: cd.pdf")
        self.assertEqual(parts[1].inline_data.mime_type, "application/pdf")
        self.assertEqual(parts[-1].text, "Produce the test steps.")
        self.assertEqual(call["config"].max_output_tokens, 1000)
        self.assertEqual(call["config"].response_mime_type, "application/json")
        self.assertEqual(call["config"].system_instruction, "System prompt")

        self.assertEqual(response.text, ANSWER)
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (10, 5))
        self.assertFalse(response.truncated)

    def test_reports_truncation(self) -> None:
        self.provider.client.models.generate_content.return_value = self.answer(
            self.types.FinishReason.MAX_TOKENS
        )
        self.assertTrue(self.provider.prompt(REQUEST).truncated)


class AnthropicProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        from services.ai.providers.anthropic import AnthropicProvider

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            self.provider = AnthropicProvider(platform="api", project="", region="")

    def answer(self, stop_reason: str):
        from anthropic.types import Message

        return Message.model_validate(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [{"type": "text", "text": ANSWER}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )

    def stream_returning(self, message):
        stream = mock.MagicMock()
        stream.__enter__.return_value.get_final_message.return_value = message
        return mock.patch.object(self.provider.client.messages, "stream", return_value=stream)

    def test_sends_documents_schema_and_limits(self) -> None:
        with self.stream_returning(self.answer("end_turn")) as stream:
            response = self.provider.prompt(REQUEST)

        call = stream.call_args.kwargs
        self.assertEqual(call["model"], "some-model")
        self.assertEqual(call["max_tokens"], 1000)
        self.assertEqual(call["system"], "System prompt")
        content = call["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "document")
        self.assertEqual(content[0]["title"], "Control details: cd.pdf")
        self.assertEqual(content[-1], {"type": "text", "text": "Produce the test steps."})
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")

        self.assertEqual(response.text, ANSWER)
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (10, 5))
        self.assertFalse(response.truncated)

    def test_reports_truncation(self) -> None:
        with self.stream_returning(self.answer("max_tokens")):
            self.assertTrue(self.provider.prompt(REQUEST).truncated)


if __name__ == "__main__":
    unittest.main()
