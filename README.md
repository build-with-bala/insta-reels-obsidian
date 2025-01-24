# Insta Reels to Obsidian

Capture Instagram reels from DM chats and save them as searchable, tagged notes in your Obsidian vault.

## How It Works

1. Share reels in a specific Instagram DM chat (on web)
2. Chrome extension detects the reel link
3. Local server fetches metadata and auto-tags with AI
4. Markdown notes appear in your Obsidian vault

## Architecture

```
Instagram Web DM → Chrome Extension (detect) → Local Server (metadata + AI tags) → Obsidian Vault
```

## Setup

### 1. Server

```bash
cd insta-reels-obsidian
pip install -r requirements.txt
```

Edit `config.yaml`:

```yaml
vault_path: /path/to/your/obsidian/vault
llm_api_key: your-api-key
llm_provider: openai  # or anthropic
server_port: 7890
```

Start the server:

```bash
python -m server.main
```

### 2. Chrome Extension

1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `extension/` folder
4. Click the extension icon and configure:
   - Set your target chat name
   - Toggle on

### 3. Usage

Share reels to your designated DM chat on Instagram web. Notes will appear in your Obsidian vault under `Instagram Reels/`.

## Vault Structure

```
Instagram Reels/
  Log.md              # all reels, newest first
  Daily/
    2025-11-10.md     # grouped by date
  Tags/
    recipe.md         # grouped by AI-generated tags
    travel.md
```

Each reel entry includes:
- Creator name and link to reel
- Date captured
- Caption text
- Auto-generated tags
- Your notes (if any)

## Auto-Tagging

The server uses an LLM (OpenAI or Anthropic) to automatically categorize reels into tags like `recipe`, `travel`, `fitness`, `funny`, etc. You can customize the default tag categories in `config.yaml`.

## Offline Support

If the local server is not running when you share a reel, the extension queues it locally and retries every 30 seconds until the server is available.

## Configuration

| Field | Default | Description |
|-------|---------|-------------|
| `vault_path` | (required) | Absolute path to your Obsidian vault |
| `llm_api_key` | (required) | OpenAI or Anthropic API key |
| `llm_provider` | `openai` | `openai` or `anthropic` |
| `default_tags` | 9 categories | Preferred tag categories for the AI |
| `server_port` | `7890` | Local server port (1024-65535) |

## Running Tests

```bash
python -m pytest server/tests/ -v
```

## Tech Stack

- **Server:** Python, FastAPI, SQLite, yt-dlp
- **AI:** OpenAI GPT-4o-mini or Anthropic Claude Haiku
- **Extension:** Chrome Manifest V3, vanilla JS
- **Notes:** Obsidian-compatible Markdown with YAML frontmatter

## License

MIT
