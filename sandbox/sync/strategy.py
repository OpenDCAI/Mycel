from abc import ABC, abstractmethod
from pathlib import Path

class SyncStrategy(ABC):
    @abstractmethod
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        pass

    @abstractmethod
    def download(self, thread_id: str, session_id: str, provider):
        pass

class NoOpStrategy(SyncStrategy):
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        pass

    def download(self, thread_id: str, session_id: str, provider):
        pass
