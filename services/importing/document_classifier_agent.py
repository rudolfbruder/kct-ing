from __future__ import annotations

from services.control_testing.agents.prompt_file_agent import PromptFileAgent
from services.importing.data import DocumentChoice


class DocumentClassifierAgent(PromptFileAgent):
    """Import: which one of the uploaded files is the control details, and which the test plan?

    There is always exactly one of each; every other file is evidence.
    Instructions: prompts/document_classification.md
    Output: DocumentChoice
    """

    name = "document_classification"
    output_schema = DocumentChoice
    max_tokens = 2048
