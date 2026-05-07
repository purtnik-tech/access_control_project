from typing import Protocol


class OCRProtocol(Protocol):

    def recognize(self, value) -> str | None:
        ...