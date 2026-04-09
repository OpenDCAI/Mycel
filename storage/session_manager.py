"""Session management for agent thread persistence"""

import json
from pathlib import Path

from storage.providers.sqlite.checkpoint_repo import SQLiteCheckpointRepo
from storage.providers.sqlite.file_operation_repo import SQLiteFileOperationRepo
from storage.runtime import build_storage_container, uses_supabase_storage


class SessionManager:
    """管理 session 状态"""

    def __init__(self, session_dir: Path | None = None):
        if session_dir is None:
            session_dir = Path.home() / ".leon"
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / "session.json"
        self.db_path = self.session_dir / "leon.db"

    def save_session(self, thread_id: str, workspace: str | None = None) -> None:
        """保存 session 状态"""
        data = self._load_data()
        data["last_thread_id"] = thread_id

        threads = data.get("threads", [])
        if thread_id not in threads:
            threads.insert(0, thread_id)
            threads = threads[:20]
            data["threads"] = threads

        if workspace:
            data["last_workspace"] = workspace

        self.session_file.write_text(json.dumps(data, indent=2))

    def get_last_thread_id(self) -> str | None:
        """获取最后使用的 thread_id"""
        data = self._load_data()
        return data.get("last_thread_id")

    def get_threads(self) -> list[str]:
        """获取所有 thread_id 列表"""
        data = self._load_data()
        return data.get("threads", [])

    def delete_thread(self, thread_id: str) -> bool:
        """删除一个 thread 及其所有数据"""
        data = self._load_data()
        threads = data.get("threads", [])
        if thread_id in threads:
            threads.remove(thread_id)
            data["threads"] = threads
            if data.get("last_thread_id") == thread_id:
                data["last_thread_id"] = threads[0] if threads else None
            self.session_file.write_text(json.dumps(data, indent=2))

        if uses_supabase_storage():
            try:
                container = build_storage_container()

                repo = container.checkpoint_repo()
                try:
                    repo.delete_thread_data(thread_id)
                finally:
                    repo.close()

                file_repo = container.file_operation_repo()
                try:
                    file_repo.delete_thread_operations(thread_id)
                finally:
                    file_repo.close()
                return True
            except Exception as e:
                print(f"[SessionManager] Error deleting thread from storage container: {e}")
                return False

        if self.db_path.exists():
            try:
                repo = SQLiteCheckpointRepo(db_path=self.db_path)
                try:
                    repo.delete_thread_data(thread_id)
                finally:
                    repo.close()

                file_repo = SQLiteFileOperationRepo(db_path=self.db_path)
                try:
                    file_repo.delete_thread_operations(thread_id)
                finally:
                    file_repo.close()
                return True
            except Exception as e:
                print(f"[SessionManager] Error deleting thread from DB: {e}")
                return False
        return True

    def _load_data(self) -> dict:
        """加载 session 数据"""
        if not self.session_file.exists():
            return {}
        try:
            return json.loads(self.session_file.read_text())
        except Exception:
            return {}
