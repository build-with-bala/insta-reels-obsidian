import asyncio
import contextlib
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from server.config import Config, ConfigError, load_config, validate_startup
from server.db import ReelDB
from server.metadata import fetch_reel_metadata, extract_reel_id
from server.tagger import auto_tag_reel
from server.vault_writer import VaultWriter

logger = logging.getLogger(__name__)

# Statuses that should be retried rather than treated as terminal.
RETRYABLE_STATUSES = {"fetch-failed", "untagged"}


class ReelRequest(BaseModel):
    url: str
    timestamp: str
    userNote: Optional[str] = None

    @field_validator("url")
    @classmethod
    def url_must_be_instagram(cls, v):
        if "instagram.com" not in v:
            raise ValueError("URL must be an Instagram link")
        return v


def create_app(config: Config = None, db_path: str = None) -> FastAPI:
    if config is None:
        config = load_config("config.yaml")
    if db_path is None:
        db_path = "reels.db"

    db = ReelDB(db_path)
    vault = VaultWriter(config.vault_path)

    cookies_from_browser = getattr(config, "cookies_from_browser", None)
    cookie_file = getattr(config, "cookie_file", None)

    retry_interval = getattr(config, "retry_interval_minutes", 0)
    retry_loop_enabled = (
        isinstance(retry_interval, (int, float))
        and not isinstance(retry_interval, bool)
        and retry_interval > 0
    )

    def _fetch_metadata_blocking(url: str):
        # Resolved at call time so tests can patch server.main.fetch_reel_metadata.
        return fetch_reel_metadata(
            url,
            cookies_from_browser=cookies_from_browser,
            cookie_file=cookie_file,
        )

    async def _fetch_metadata(url: str):
        """Run the blocking yt-dlp fetch in a thread so the loop stays free."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch_metadata_blocking, url)

    async def _tag(caption, creator):
        return await auto_tag_reel(
            caption=caption,
            creator=creator,
            provider=config.llm_provider,
            api_key=config.llm_api_key,
            default_tags=config.default_tags,
        )

    async def _retry_reel(row: dict) -> dict:
        """Re-attempt fetch and/or tagging for a stored fetch-failed or
        untagged reel. Returns a response-shaped dict."""
        reel_id = row["id"]
        old_tags = json.loads(row["tags"]) if row.get("tags") else []

        if row["status"] == "fetch-failed":
            metadata = await _fetch_metadata(row["url"])
            if metadata is None:
                return {"status": "fetch-failed", "reel_id": reel_id}
            tags = await _tag(metadata.caption, metadata.creator_username)
            new_status = "processed" if tags else "untagged"
            tags = tags or ["untagged"]
            db.update_reel_metadata(
                reel_id,
                creator_username=metadata.creator_username,
                creator_display_name=metadata.creator_display_name,
                caption=metadata.caption,
                thumbnail_url=metadata.thumbnail_url,
            )
            db.update_reel_tags(reel_id, tags, new_status)
            vault.replace_reel({
                "id": reel_id,
                "url": row["url"],
                "creator_username": metadata.creator_username,
                "creator_display_name": metadata.creator_display_name,
                "caption": metadata.caption,
                "tags": tags,
                "user_note": row.get("user_note"),
                "timestamp": row["timestamp"],
            }, old_tags=old_tags)
            return {"status": new_status, "reel_id": reel_id, "tags": tags}

        # untagged: metadata is already stored, only tagging failed.
        tags = await _tag(row.get("caption"), row.get("creator_username"))
        if not tags:
            return {"status": "untagged", "reel_id": reel_id}
        db.update_reel_tags(reel_id, tags, "processed")
        vault.replace_reel({
            "id": reel_id,
            "url": row["url"],
            "creator_username": row.get("creator_username"),
            "creator_display_name": row.get("creator_display_name"),
            "caption": row.get("caption"),
            "tags": tags,
            "user_note": row.get("user_note"),
            "timestamp": row["timestamp"],
        }, old_tags=old_tags)
        return {"status": "processed", "reel_id": reel_id, "tags": tags}

    async def _retry_pending() -> dict:
        """One retry pass over all fetch-failed / untagged reels."""
        candidates = db.get_retry_candidates()
        recovered, still_pending = 0, 0
        for row in candidates:
            try:
                result = await _retry_reel(row)
            except Exception:
                logger.exception(f"Retry failed for reel {row['id']}")
                still_pending += 1
                continue
            if result["status"] == "processed":
                recovered += 1
            else:
                still_pending += 1
        return {
            "retried": len(candidates),
            "recovered": recovered,
            "still_pending": still_pending,
        }

    async def _retry_loop():
        interval_seconds = retry_interval * 60
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                summary = await _retry_pending()
                if summary["retried"]:
                    logger.info(f"Retry pass: {summary}")
            except Exception:
                logger.exception("Retry pass crashed; will try again next cycle")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if retry_loop_enabled:
            task = asyncio.create_task(_retry_loop())
            logger.info(
                f"Retry loop enabled (every {retry_interval} minutes)"
            )
        yield
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Insta Reels to Obsidian", lifespan=lifespan)

    # Note: chrome-extension:// origins are intentionally absent. Starlette
    # matches origins exactly (no wildcards), and the MV3 extension talks to
    # the server via host_permissions, which bypasses CORS entirely.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://www.instagram.com"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/status")
    def status():
        stats = db.get_stats()
        return {
            "status": "ok",
            "vault_path": config.vault_path,
            "reel_counts": stats,
        }

    @app.post("/retry")
    async def retry_pending():
        """Re-process fetch-failed and untagged reels on demand."""
        return await _retry_pending()

    @app.post("/reel")
    async def receive_reel(req: ReelRequest):
        reel_id = extract_reel_id(req.url)
        if not reel_id:
            reel_id = req.url

        existing = db.get_reel(reel_id)
        if existing is not None:
            if existing["status"] in RETRYABLE_STATUSES:
                # Re-sharing a failed reel triggers a retry instead of
                # dead-ending as a duplicate.
                return await _retry_reel(existing)
            return {"status": "duplicate", "reel_id": reel_id}

        metadata = await _fetch_metadata(req.url)

        if metadata is None:
            try:
                db.insert_reel(
                    reel_id=reel_id,
                    url=req.url,
                    timestamp=req.timestamp,
                    user_note=req.userNote,
                    status="fetch-failed",
                    tags=["fetch-failed"],
                )
            except sqlite3.IntegrityError:
                # Lost a duplicate-check/insert race with a concurrent request.
                return {"status": "duplicate", "reel_id": reel_id}
            vault.write_reel({
                "id": reel_id,
                "url": req.url,
                "creator_username": None,
                "creator_display_name": None,
                "caption": None,
                "tags": ["fetch-failed"],
                "user_note": req.userNote,
                "timestamp": req.timestamp,
            })
            return {"status": "fetch-failed", "reel_id": reel_id}

        tags = await _tag(metadata.caption, metadata.creator_username)

        status = "processed" if tags else "untagged"
        tags = tags or ["untagged"]

        try:
            db.insert_reel(
                reel_id=metadata.reel_id,
                url=req.url,
                creator_username=metadata.creator_username,
                creator_display_name=metadata.creator_display_name,
                caption=metadata.caption,
                tags=tags,
                thumbnail_url=metadata.thumbnail_url,
                user_note=req.userNote,
                timestamp=req.timestamp,
                status=status,
            )
        except sqlite3.IntegrityError:
            # Lost a duplicate-check/insert race with a concurrent request.
            return {"status": "duplicate", "reel_id": metadata.reel_id}

        vault.write_reel({
            "id": metadata.reel_id,
            "url": req.url,
            "creator_username": metadata.creator_username,
            "creator_display_name": metadata.creator_display_name,
            "caption": metadata.caption,
            "tags": tags,
            "user_note": req.userNote,
            "timestamp": req.timestamp,
        })

        return {
            "status": status,
            "reel_id": metadata.reel_id,
            "tags": tags,
        }

    return app


def main() -> int:
    import sys

    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        cfg = load_config("config.yaml")
        validate_startup(cfg)
    except ConfigError as e:
        print(f"\nConfiguration error:\n  {e}\n", file=sys.stderr, flush=True)
        return 1

    logger.info(f"Starting server on {cfg.server_host}:{cfg.server_port}")
    logger.info(f"Vault path: {cfg.vault_path}")
    logger.info(f"LLM provider: {cfg.llm_provider}")
    if cfg.cookies_from_browser:
        logger.info(f"Instagram cookies from browser: {cfg.cookies_from_browser}")
    elif cfg.cookie_file:
        logger.info(f"Instagram cookie file: {cfg.cookie_file}")
    else:
        logger.warning(
            "No Instagram cookies configured (cookies_from_browser / "
            "cookie_file); most metadata fetches will fail. Failed reels are "
            "still saved and retried later."
        )

    application = create_app(cfg)
    uvicorn.run(application, host=cfg.server_host, port=cfg.server_port)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
