from __future__ import annotations


class ProgressGateway:
    def report(self, message: str) -> None:
        print(message, flush=True)


__all__ = ["ProgressGateway"]
