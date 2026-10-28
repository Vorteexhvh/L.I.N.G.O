"""Persistent local conversation history, attachments, and daily activity for L.I.N.G.O.

No third-party dependencies; files stay on the user's computer.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

MEDIA_FORMATS = {
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"},
    "audio": {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
}
MAX_MEDIA_BYTES = {"image": 15 * 1024**2, "audio": 35 * 1024**2, "video": 150 * 1024**2}


def app_data_dir() -> Path:
    """Use the Windows user's own local profile, not the protected install directory."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_DATA_HOME")
    return Path(base) / "LINGO" if base else Path.home() / ".lingo"


class DataStore:
    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder is not None else app_data_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.media_dir = self.folder / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.folder / "history.json"
        self.data = {"version": 1, "chats": [], "activity": {"last_date": None, "current": 0, "best": 0, "days_used": 0}}
        self._load()

    def _load(self) -> None:
        if not self.json_path.exists():
            return
        try:
            loaded = json.loads(self.json_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(loaded.get("chats"), list):
                raise ValueError("Formato de histórico inválido")
            self.data["chats"] = [chat for chat in loaded["chats"] if isinstance(chat, dict) and isinstance(chat.get("messages"), list)]
            activity = loaded.get("activity")
            if isinstance(activity, dict):
                self.data["activity"].update({key: activity[key] for key in self.data["activity"] if key in activity})
        except (OSError, ValueError, TypeError):
            # Preserve a damaged file for manual recovery; never erase it silently.
            backup = self.json_path.with_name("history-corrupted-" + uuid.uuid4().hex[:8] + ".json")
            try:
                self.json_path.replace(backup)
            except OSError:
                pass

    def save(self):
        content = json.dumps(self.data, ensure_ascii=False, indent=2)
        name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.folder, suffix=".tmp", delete=False) as handle:
                name = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.json_path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def chats(self) -> list[dict]:
        return sorted(self.data["chats"], key=lambda c: c.get("updated_at", ""), reverse=True)

    def get(self, chat_id: str) -> dict | None:
        return next((c for c in self.data["chats"] if c.get("id") == chat_id), None)

    def new_chat(self) -> dict:
        now = datetime.now().isoformat(timespec="seconds")
        chat = {"id": uuid.uuid4().hex, "title": "Nova conversa", "created_at": now,
                "updated_at": now, "messages": []}
        self.data["chats"].append(chat)
        self.save()
        return chat

    def add_message(self, chat_id: str, role: str, content: str, attachments: list[dict] | None = None, *, context: bool = True) -> dict:
        chat = self.get(chat_id)
        if chat is None:
            raise ValueError("Conversa não encontrada")
        msg = {"role": role, "content": content, "created_at": datetime.now().isoformat(timespec="seconds"),
               "attachments": list(attachments or []), "context": bool(context)}
        chat["messages"].append(msg)
        if chat["title"] == "Nova conversa" and role == "user":
            chat["title"] = (content.strip() or "Arquivos compartilhados").replace("\n", " ")[:43]
        chat["updated_at"] = msg["created_at"]
        self.save()
        return msg

    def remove_chat(self, chat_id: str):
        chat = self.get(chat_id)
        if chat is None:
            return
        # Each attachment is a private copied file; deleting the chat deletes its copies.
        for message in chat["messages"]:
            for item in message.get("attachments", []):
                self.remove_media(item.get("path", ""))
        self.data["chats"].remove(chat)
        self.save()

    def export_chat_text(self, chat_id: str, destination: str | Path) -> Path:
        """Write a readable copy of one conversation without changing its local history."""
        chat = self.get(chat_id)
        if chat is None:
            raise ValueError("Conversa não encontrada")
        lines = [f"L.I.N.G.O. — {chat.get('title', 'Conversa')}",
                 f"Criada em: {chat.get('created_at', '')}", ""]
        labels = {"user": "Você", "assistant": "L.I.N.G.O.", "error": "Erro"}
        for message in chat["messages"]:
            label = labels.get(message.get("role"), "L.I.N.G.O.")
            lines.append(f"[{message.get('created_at', '')}] {label}")
            if message.get("content"):
                lines.append(str(message["content"]))
            for item in message.get("attachments", []):
                lines.append(f"Anexo ({item.get('kind', 'arquivo')}): {item.get('name', 'Arquivo')}")
            lines.append("")
        target = Path(destination)
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    def add_media(self, src: str | Path) -> dict:
        source = Path(src).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError("O anexo selecionado não é um arquivo")
        suffix = source.suffix.lower()
        kind = next((category for category, suffixes in MEDIA_FORMATS.items() if suffix in suffixes), None)
        if kind is None:
            raise ValueError(f"Formato não suportado: {suffix or '(sem extensão)'}")
        size = source.stat().st_size
        if not size:
            raise ValueError("Arquivo vazio")
        if size > MAX_MEDIA_BYTES[kind]:
            raise ValueError(f"Arquivo muito grande. Limite para {kind}: {MAX_MEDIA_BYTES[kind] // (1024**2)} MB")
        dest = self.media_dir / f"{uuid.uuid4().hex}{suffix}"
        shutil.copy2(source, dest)
        return {"id": uuid.uuid4().hex, "name": source.name, "kind": kind,
                "size": size, "path": str(dest)}

    def remove_media(self, path: str):
        try:
            candidate = Path(path).resolve(strict=True)
            if candidate.parent == self.media_dir.resolve() and candidate.is_file():
                candidate.unlink()
        except (OSError, ValueError):
            pass

    def record_daily_use(self, today: date | None = None) -> dict:
        today = today or date.today()
        tracker = self.data["activity"]
        stamp = today.isoformat()
        last = tracker.get("last_date")
        if last == stamp or (last and last > stamp):
            return tracker
        tracker["current"] = int(tracker.get("current") or 0) + 1 if last == (today - timedelta(days=1)).isoformat() else 1
        tracker["best"] = max(int(tracker.get("best") or 0), tracker["current"])
        tracker["days_used"] = int(tracker.get("days_used") or 0) + 1
        tracker["last_date"] = stamp
        self.save()
        return tracker
