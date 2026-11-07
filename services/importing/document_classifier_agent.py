from __future__ import annotations

from services.control_testing.agents.prompt_file_agent import PromptFileAgent
from services.importing.data import DocumentClassification


class DocumentClassifierAgent(PromptFileAgent):
    """Import: is this file the control details, the test plan, or something else?

    Instructions: prompts/document_classification.md
    Output: DocumentClassification
    """

    name = "document_classification"
    output_schema = DocumentClassification
    max_tokens = 2048
