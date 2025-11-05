import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.config import Config, load_config
from server.db import ReelDB
from server.metadata import fetch_reel_metadata, extract_reel_id
from server.tagger import auto_tag_reel
from server.vault_writer import VaultWriter

logger = logging.getLogger(__name__)


class ReelRequest(BaseModel):
    url: str
    timestamp: str
    userNote: Optional[str] = None


def create_app(config: Config = None, db_path: str = None) -> FastAPI:
    app = FastAPI(title="Insta Reels to Obsidian")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://www.instagram.com", "chrome-extension://*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    if config is None:
        config = load_config("config.yaml")
    if db_path is None:
        db_path = "reels.db"

    db = ReelDB(db_path)
    vault = VaultWriter(config.vault_path)

    @app.get("/status")
    def status():
        return {"status": "ok", "vault_path": config.vault_path}

    @app.post("/reel")
    async def receive_reel(req: ReelRequest):
        reel_id = extract_reel_id(req.url)
        if not reel_id:
            reel_id = req.url

        if db.reel_exists(reel_id):
            return {"status": "duplicate", "reel_id": reel_id}

        metadata = fetch_reel_metadata(req.url)

        if metadata is None:
            db.insert_reel(
                reel_id=reel_id,
                url=req.url,
                timestamp=req.timestamp,
                user_note=req.userNote,
                status="fetch-failed",
                tags=["fetch-failed"],
            )
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

        tags = await auto_tag_reel(
            caption=metadata.caption,
            creator=metadata.creator_username,
            provider=config.llm_provider,
            api_key=config.llm_api_key,
            default_tags=config.default_tags,
        )

        status = "processed" if tags else "untagged"
        tags = tags or ["untagged"]

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


if __name__ == "__main__":
    import uvicorn
    cfg = load_config("config.yaml")
    application = create_app(cfg)
    uvicorn.run(application, host="0.0.0.0", port=cfg.server_port)
