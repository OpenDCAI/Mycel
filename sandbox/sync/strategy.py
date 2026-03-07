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

class FullSyncStrategy(SyncStrategy):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        workspace = self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return

        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(workspace)
                remote_path = f"/workspace/files/{relative}"
                content = file_path.read_text()
                provider.write_file(session_id, remote_path, content)

    def download(self, thread_id: str, session_id: str, provider):
        workspace = self.workspace_root / thread_id / "files"
        workspace.mkdir(parents=True, exist_ok=True)

        def download_recursive(remote_path: str, local_path: Path):
            items = provider.list_dir(session_id, remote_path)
            for item in items:
                remote_item = f"{remote_path}/{item['name']}".replace("//", "/")
                local_item = local_path / item["name"]
                if item["type"] == "directory":
                    local_item.mkdir(parents=True, exist_ok=True)
                    download_recursive(remote_item, local_item)
                else:
                    content = provider.read_file(session_id, remote_item)
                    local_item.write_text(content)

        download_recursive("/workspace/files", workspace)
