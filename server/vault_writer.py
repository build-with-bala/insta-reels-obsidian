import os
import re
import tempfile
import shutil
from pathlib import Path


class VaultWriter:
    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self.base_dir = Path(vault_path) / "Instagram Reels"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "Daily").mkdir(exist_ok=True)
        (self.base_dir / "Tags").mkdir(exist_ok=True)

    def format_entry(self, reel: dict) -> str:
        creator = reel.get("creator_username") or "unknown"
        url = reel["url"]
        ts = reel["timestamp"]
        date_str = ts[:10] + " " + ts[11:16] if len(ts) >= 16 else ts
        caption = reel.get("caption") or ""
        tags = reel.get("tags") or []
        user_note = reel.get("user_note") or ""

        tag_str = " ".join(f"#{t}" for t in tags) if tags else "none"

        lines = [
            f"### [Reel by @{creator}]({url})",
            f"- **Date:** {date_str}",
            f"- **Caption:** \"{caption}\"",
            f"- **Tags:** {tag_str}",
        ]
        if user_note:
            lines.append(f"- **Note:** {user_note}")
        lines.append("")
        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    def write_reel(self, reel: dict):
        entry = self.format_entry(reel)
        self._write_log(entry)
        self._write_daily(reel["timestamp"], entry)
        self._write_tags(reel.get("tags") or [], entry)

    def replace_reel(self, reel: dict, old_tags: list[str] | None = None):
        """Rewrite a reel's vault entries after a successful retry.

        Removes any existing blocks for this reel URL from Log.md, the
        reel's Daily note, and the old tag files (e.g. fetch-failed /
        untagged), then writes the updated entry as usual.
        """
        url = reel["url"]
        self._remove_entry(self.base_dir / "Log.md", url)
        date = reel["timestamp"][:10]
        self._remove_entry(self.base_dir / "Daily" / f"{date}.md", url)
        for tag in old_tags or []:
            tag_clean = tag.lower().replace(" ", "-")
            self._remove_entry(self.base_dir / "Tags" / f"{tag_clean}.md", url)
        self.write_reel(reel)

    def _remove_entry(self, path: Path, url: str):
        """Remove every entry block referencing `url` from a vault file."""
        if not path.exists():
            return
        content = path.read_text()
        pattern = re.compile(
            r"### \[Reel by @[^\]]*\]\(" + re.escape(url) + r"\).*?---\n\n?",
            re.DOTALL,
        )
        new_content = pattern.sub("", content)
        if new_content != content:
            self._atomic_write(path, new_content)

    def _write_log(self, entry: str):
        log_path = self.base_dir / "Log.md"
        if log_path.exists():
            existing = log_path.read_text()
            content = entry + existing
        else:
            content = "# Instagram Reels Log\n\n" + entry
        self._atomic_write(log_path, content)

    def _write_daily(self, timestamp: str, entry: str):
        date = timestamp[:10]
        daily_path = self.base_dir / "Daily" / f"{date}.md"
        if daily_path.exists():
            existing = daily_path.read_text()
            content = existing + entry
        else:
            frontmatter = f"---\ntype: instagram-reel-daily\ndate: {date}\n---\n\n"
            content = frontmatter + entry
        self._atomic_write(daily_path, content)

    def _write_tags(self, tags: list[str], entry: str):
        for tag in tags:
            tag_clean = tag.lower().replace(" ", "-")
            tag_path = self.base_dir / "Tags" / f"{tag_clean}.md"
            if tag_path.exists():
                existing = tag_path.read_text()
                content = existing + entry
            else:
                frontmatter = (
                    f"---\ntype: instagram-reel-tag\ntag: {tag_clean}\n---\n\n"
                )
                content = frontmatter + entry
            self._atomic_write(tag_path, content)

    def _atomic_write(self, target: Path, content: str):
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=target.parent, suffix=".tmp", prefix=".vault_"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(content)
            shutil.move(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
