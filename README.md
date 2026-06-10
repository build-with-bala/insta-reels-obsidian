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

Requires Python 3.11+.

```bash
cd insta-reels-obsidian
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the example config and edit it:

```bash
cp config.example.yaml config.yaml
```

```yaml
vault_path: /Users/you/Documents/MyVault   # must already exist
llm_provider: openai                        # or anthropic
cookies_from_browser: chrome                # see "Instagram authentication"
server_port: 7890
```

Set your LLM API key as an environment variable (recommended — keep real
keys out of `config.yaml`, which is easy to commit by accident):

```bash
export INSTA_REELS_LLM_API_KEY=sk-your-key
```

The env var takes precedence over `llm_api_key` in `config.yaml`. See
`.env.example` if you prefer keeping it in a local `.env` file.

Start the server:

```bash
python -m server.main
```

The server validates the config at startup and prints an actionable error
(instead of a traceback) if `vault_path` / the API key are still
placeholders, or if the vault directory is missing or not writable.

### Instagram authentication

Instagram blocks most anonymous metadata requests, so yt-dlp needs your
Instagram login cookies. Configure **one** of these in `config.yaml`:

```yaml
# Read cookies directly from a browser you are logged into Instagram with:
cookies_from_browser: chrome     # or safari, firefox, edge, "chrome:Profile 1"

# OR point to a Netscape-format cookies file exported from your browser:
cookie_file: /path/to/instagram-cookies.txt
```

If a metadata fetch still fails, the reel is **not lost**: it is saved to
the vault immediately with a `#fetch-failed` marker and retried later (see
below).

### Failed-reel retries

Reels whose metadata fetch or tagging failed stay retryable:

- A background task retries all `fetch-failed` / `untagged` reels every
  `retry_interval_minutes` (default 10; set `0` to disable).
- `POST http://127.0.0.1:7890/retry` triggers a retry pass on demand.
- Re-sharing a failed reel in the DM chat retries it instead of being
  dropped as a duplicate.

On success the vault entry is rewritten in place with the fetched metadata
and tags.

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
| `vault_path` | (required) | Absolute path to your Obsidian vault (must exist) |
| `llm_api_key` | (required*) | OpenAI or Anthropic API key. *Prefer the `INSTA_REELS_LLM_API_KEY` env var, which overrides this field |
| `llm_provider` | `openai` | `openai` or `anthropic` |
| `default_tags` | 9 categories | Preferred tag categories for the AI |
| `server_port` | `7890` | Local server port (1024-65535) |
| `server_host` | `127.0.0.1` | Bind address. Local-only by default; `0.0.0.0` exposes it to your LAN |
| `cookies_from_browser` | (none) | Browser to read Instagram cookies from for yt-dlp (`chrome`, `safari`, `firefox`, `edge`, `chrome:Profile 1`, ...) |
| `cookie_file` | (none) | Path to a Netscape-format Instagram cookies file for yt-dlp |
| `retry_interval_minutes` | `10` | Minutes between automatic retries of failed reels (`0` disables the loop) |

Environment variables:

| Variable | Description |
|----------|-------------|
| `INSTA_REELS_LLM_API_KEY` | LLM API key; takes precedence over `llm_api_key` in `config.yaml`. The server does not load `.env` files automatically — export it in the shell that runs the server (see `.env.example`) |

## Server API

| Endpoint | Description |
|----------|-------------|
| `POST /reel` | Save a reel (`{url, timestamp, userNote?}`). Re-posting a failed reel retries it |
| `POST /retry` | Retry all `fetch-failed` / `untagged` reels now |
| `GET /status` | Health check with reel counts by status |

## Troubleshooting

#### Server refuses to start (Configuration error)

The server validates the config at startup and prints a `Configuration error:` message to stderr with a `Fix:` line. Common causes:

- **`vault_path` is still the placeholder** — edit `config.yaml` and replace `/path/to/...` with your actual Obsidian vault directory.
- **Vault path does not exist or is not a directory** — make sure the folder exists before starting the server.
- **Vault path is not writable** — adjust filesystem permissions so the user running the server can write to the vault.
- **No LLM API key configured** — set `export INSTA_REELS_LLM_API_KEY=<your key>` in the shell that runs the server, or set `llm_api_key` in `config.yaml`.
- **Invalid `llm_provider`** — must be `openai` or `anthropic`.
- **`cookie_file` path does not exist** — either export your Instagram cookies to that path (Netscape format), or switch to `cookies_from_browser`.

#### Instagram metadata fetch keeps failing (#fetch-failed)

Common causes: no cookies configured, cookies have expired or you are logged out, Instagram rate limiting.

Fixes:
- Set `cookies_from_browser` in `config.yaml` to a browser that is currently logged into Instagram (e.g. `chrome`, `safari`, `firefox`).
- Export a Netscape-format cookie file from your browser and point `cookie_file` at it.
- On macOS, yt-dlp can fail to read Chrome's cookie database while Chrome is running (SQLite lock). Quit Chrome before starting the server, or use an exported `cookie_file` instead.

Failed reels are **not lost**: they are written to the vault immediately with a `#fetch-failed` tag and automatically retried every `retry_interval_minutes` minutes. You can also trigger a retry pass on demand via `POST /retry` or the **Retry failed now** button in the extension popup.

#### Tagging fails or reels land as #untagged

Common causes: invalid API key (HTTP 401 from the LLM provider), provider rate limits (HTTP 429), or transient network errors. Untagged reels keep their fetched metadata and are re-tagged by the same retry pipeline — check the server logs for the provider error message. Once the API key or rate-limit issue is resolved, the next retry pass (automatic or manual) will tag them.

#### Extension badge meanings

| Badge | Meaning |
|-------|---------|
| Orange `!` | Capture is enabled but the local server is unreachable (checked every 60 s) |
| Red number | Count of reels queued in the browser waiting to be sent to the server |
| No badge | Healthy — nothing queued |

#### Popup queue

The popup lists reels currently queued in the browser (not yet delivered to the server) alongside the server-side counts of `fetch-failed` and `untagged` reels. The **Retry failed now** button sends a `POST /retry` to the server, triggering an immediate retry pass for all failed and untagged reels without waiting for the next automatic interval.

#### Changed the server port?

Three places must all agree:

1. `server_port` in `config.yaml`
2. The **Server URL** field in the extension popup settings
3. The `http://localhost:7890/*` entry in `extension/manifest.json` under `host_permissions`

If the manifest entry does not match the port the server is listening on, the extension's status checks and retry calls will be blocked by Chrome's host permissions.

## Running Tests

Activate the virtualenv first (dependencies including `pytest` are in `requirements.txt`):

```bash
source .venv/bin/activate
python -m pytest server/tests/ -v
```

## Tech Stack

- **Server:** Python, FastAPI, SQLite, yt-dlp
- **AI:** OpenAI GPT-4o-mini or Anthropic Claude Haiku
- **Extension:** Chrome Manifest V3, vanilla JS
- **Notes:** Obsidian-compatible Markdown with YAML frontmatter

## License

MIT — see [LICENSE](LICENSE).
