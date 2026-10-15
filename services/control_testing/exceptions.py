from __future__ import annotations


class StageFailedError(Exception):
    """An agent failed while processing a stored case. The case's files are kept."""

    def __init__(self, case_id: str, cause: Exception) -> None:
        super().__init__(f"{case_id}: {type(cause).__name__}: {cause}")
        self.case_id = case_id
