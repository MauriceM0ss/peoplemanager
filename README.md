# People Manager

> ⚠️ **Disclaimer:** This is a Claude Code "vibe coding" project. It was built
> iteratively with the [Claude Code](https://claude.com/claude-code) AI agent
> and is intended for personal/experimental use.

A self-hosted web app for keeping track of people. Add contacts manually, attach photos, log conversations, take notes, manage tasks per person, and organise everyone into categories — all through a PIN-protected dark-mode web interface backed by an encrypted SQLite database.

## How it works

The app is fully self-contained. There is no external data source — every person, conversation, note, and task lives in a single SQLite database on a Docker volume. You add people yourself through the web interface.

Everything you add or change (people, photos, conversations, notes, tasks, edits) is stored in the database and persists across container restarts and rebuilds.

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/)

---

## Installation

### 1. Clone or copy the `peoplemanager/` folder

The folder contains:

```
peoplemanager/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt          # runtime deps
├── requirements-dev.txt      # test deps (see Development)
├── app.py                    # entrypoint → peoplecrm package
├── SECURITY.md               # threat model + security findings
├── peoplecrm/                # application package (factory + blueprints)
├── tests/                    # pytest suite
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── person.html
│   ├── setup.html
│   ├── lock.html
│   └── reset.html
└── static/
    └── style.css
```

See [Module layout](#module-layout) for what lives inside `peoplecrm/`.

### 2. Build and start with Docker Compose

Run this from inside the `peoplemanager/` directory:

```bash
docker compose up -d --build
```

Then open **http://localhost:8081** in your browser.

That single command builds the image (Python 3.12 slim + Flask + SQLCipher for
database encryption), creates the container, and starts it in the background. All
settings — port, the data volume, and auto-restart — are declared in
`docker-compose.yml`, so you never have to remember flags.

| Setting (in `docker-compose.yml`) | Purpose |
|---|---|
| `ports: "8081:8080"` | Map container port to host — change the left number to use a different port |
| `volumes: peoplemanager-data:/data` | Named Docker volume that persists all your data |
| `restart: unless-stopped` | Auto-start after a reboot |

---

## Running

### Everyday commands

```bash
docker compose up -d --build   # build + (re)create + start; also how you apply code changes
docker compose logs -f         # follow the logs
docker compose down            # stop & remove the container (your data volume is kept)
docker compose restart         # restart without rebuilding
```

### Update after code changes

Just re-run:

```bash
docker compose up -d --build
```

`--build` rebuilds the image from the current source, so your changes appear in the
running app. Your data lives in the `peoplemanager-data` volume and is **not**
affected by rebuilds, `docker compose down`, or container removal.

### Migrating from a manual `docker run` setup

If you previously started the app with `docker run` (a hand-created container also
named `peoplemanager`), retire it once before using Compose — this removes only the
container, not your data volume:

```bash
docker stop peoplemanager && docker rm peoplemanager
docker compose up -d --build
```

The compose file pins the volume name to `peoplemanager-data`, so the new container
reuses your existing data.

<details>
<summary>Prefer plain <code>docker run</code> instead of Compose?</summary>

```bash
docker build -t peoplemanager .
docker run -d \
  --name peoplemanager \
  --restart unless-stopped \
  -p 8081:8080 \
  -v peoplemanager-data:/data \
  peoplemanager
```

To update: `docker build -t peoplemanager .`, then
`docker stop peoplemanager && docker rm peoplemanager`, then run again.
</details>

---

## Data storage

All data is stored in a single database file inside the Docker named volume:

```
peoplemanager-data/_data/people.db
```

If PIN protection is enabled the file is encrypted with SQLCipher (AES-256) and cannot be read directly with `sqlite3` — use the built-in export to get a plain copy.

### Database tables

| Table | Contents |
|---|---|
| `photos` | Uploaded profile photos (binary blobs + mimetype) |
| `meetings` | Conversation entries added via the web form |
| `notes` | Per-person free-text notes with optional dates |
| `person_overrides` | Edits to name, category, key details, and profile |
| `persons` | All people added through the web interface |
| `hidden_persons` | People removed via "Remove person" (hidden, not fully erased) |
| `categories` | All categories (seeded with 4 defaults on first run) |
| `tasks` | Per-person task list items |

### Finding the database file on disk

```bash
docker volume inspect peoplemanager-data --format '{{ .Mountpoint }}'
# e.g. /var/lib/docker/volumes/peoplemanager-data/_data
```

### Backing up

Two options, with different at-rest safety:

- **Copy the volume file** (recommended for backups) — this is the **encrypted**
  SQLCipher database; unreadable without your PIN, so it's safe to store as-is:
  ```bash
  cp "$(docker volume inspect peoplemanager-data --format '{{ .Mountpoint }}')/people.db" ~/people-backup-$(date +%F).db
  ```
- **Built-in export** (⚙ → Export, see [Export / Import](#export--import)) — a
  **plaintext** SQLite copy, convenient for moving between machines but store it
  only on trusted media.

Automate the encrypted backup with a daily cron entry, keeping 14 days:

```cron
0 2 * * *  cp "$(docker volume inspect peoplemanager-data --format '{{ .Mountpoint }}')/people.db" ~/pv-backups/people-$(date +\%F).db && find ~/pv-backups -name 'people-*.db' -mtime +14 -delete
```

### Health

The container ships a Docker `HEALTHCHECK` that polls the unauthenticated
`/healthz` endpoint; `docker ps` shows `healthy`/`unhealthy`, and
`restart: unless-stopped` plus your orchestrator can act on it. Check it with:

```bash
docker inspect --format '{{ .State.Health.Status }}' peoplemanager
```

### Inspecting the database directly

Without PIN protection:

```bash
sqlite3 $(docker volume inspect peoplemanager-data --format '{{ .Mountpoint }}')/people.db
```

With PIN protection the file is SQLCipher-encrypted. Use the web export to get a plain copy first, then inspect that file with `sqlite3`.

### Restoring a deleted person

Deleted people are added to `hidden_persons` but their data remains in the database. To restore one:

```bash
sqlite3 /path/to/people.db "DELETE FROM hidden_persons WHERE person_id = 'jane_doe';"
```

---

## Features

### People overview (home page)

- **Card grid** showing all your people
- **Search** — filters by name in real time
- **Category dropdown** — filter the grid to a single category; defaults to "Everyone"; preference is remembered in browser storage
- **Sort dropdown** — four options, preference remembered in browser storage:
  - Name A → Z *(default)*
  - Name Z → A
  - Most conversations
  - Last conversation
- **+ Person** — add a new person (opens a modal asking for name and category)
- **⚙ (top-right)** — opens the settings panel (see below)

### PIN protection

On first visit the app shows a setup page to create a PIN (4–10 characters). Once set:

- The database is encrypted with **AES-256 (SQLCipher)** using a key derived from your PIN — the `.db` file on disk is unreadable without it
- A **🔒 lock button** appears in the top-right header to lock the app immediately
- The app **auto-locks** after a configurable period of inactivity (5 / 15 / 30 / 60 minutes); default is 15 minutes
- The timeout and a PIN-change form are both in the ⚙ settings panel

#### Forgotten PIN

If you forget your PIN, click **"Forgot PIN?"** on the lock screen. Confirm by typing `RESET` — this deletes `pin.json` and `people.db` permanently and returns you to the setup page.

> Export a backup regularly via ⚙ → Export before you lose access. The export file is a plain (unencrypted) SQLite database — store it somewhere safe.

#### Emergency reset via Docker

If you cannot reach the lock screen (e.g. the container won't start), delete the files directly:

```bash
docker exec peoplemanager rm /data/pin.json /data/people.db
docker restart peoplemanager
```

---

### Settings panel (⚙)

Accessible from the cog icon in the top-right corner on every page.

#### Security (only shown when PIN is enabled)

- **Auto-lock after** — change the inactivity timeout (5 / 15 / 30 / 60 minutes)
- **Change PIN** — enter your current PIN, then choose a new one; the database is transparently re-encrypted with the new key

#### Category management

- **Add** a new category by typing a name and clicking Add or pressing Enter
- **Rename** by clicking ✏️ on a row, editing inline, then pressing Enter or ✓
- **Delete** by clicking 🗑 — people in that category are reassigned to the first remaining category
- Default categories on first run: `Friends`, `Family`, `Work`, `Other`
- Each category gets a consistent colour derived from its name

#### Export / Import

Move your data between machines or take a backup without touching Docker volumes directly.

- **Export** — downloads the full `people.db` as a plain (unencrypted) SQLite file, regardless of whether PIN protection is on; store the file securely
- **Import** — upload a previously exported `.db` file to replace the current database; the file is validated as a real SQLite database before anything is overwritten; if PIN protection is enabled the imported data is automatically re-encrypted with your current PIN; the page reloads automatically

### Person detail page

Reached by clicking any card.

#### Photo
- Click **📷 Upload photo** to attach a photo (JPEG, PNG, WebP, etc.)
- Click **✕ Remove photo** to remove it
- Without a photo, a coloured initial avatar is shown

#### Editing a person
- Click **✏️ Edit** in the sidebar to open the edit modal
- All fields are editable in one place:
  - **Name** — display name
  - **Category** — category assignment (dropdown of existing categories)
  - **Key details** — free-text/markdown notes shown in the sidebar
  - **Profile overview** — free-text/markdown profile summary shown in the sidebar
- All fields are saved simultaneously on **Save**; the sidebar updates immediately without a page reload

#### Conversations
- All logged conversations are listed, most recent first
- Click any entry to expand the full note (rendered as markdown)
- **+ Add conversation** — add a new conversation entry:
  - Pick a date (defaults to today)
  - Title auto-fills as `YYYY-MM-DD - Conversation with <Name>`
  - Write notes in markdown
  - The entry appears immediately at the top of the list
- Each entry shows a **🗑** delete button

#### Notes
- A dated free-text notepad, shown below Conversations
- Each note shows its date and a preview of the first line when collapsed
- Click any note to expand it and read the full content
- **+ Add note** — opens a form with a date picker and a plain-text area
- **✏ Edit** — inline editing within an expanded note; click Save to update in place
- **🗑** — delete a note (with confirmation)

#### Tasks
- A simple per-person to-do list, shown below Notes
- **Add** a task by typing in the input and pressing Enter or clicking Add
- **Check off** a task with the checkbox — it is crossed out, dimmed, and moved to the bottom of the list
- **Delete** a task with the ✕ button

#### Removing a person
- **🗑 Remove person** at the bottom of the sidebar removes the person from the overview
- All associated photos, conversations, notes, tasks, and overrides are deleted from the database
- The person is added to `hidden_persons` and can be restored via SQLite if needed (see [Restoring a deleted person](#restoring-a-deleted-person))

---

## Starting fresh / full reset

There are three levels of reset depending on how much you want to wipe.

### 1. Reset via the web interface (recommended)

Navigate to **/reset** in the app (or click "Forgot PIN?" on the lock screen). Type `RESET` to confirm. This deletes:
- The encrypted database (`people.db`) — all people, photos, conversations, notes, tasks
- The PIN configuration (`pin.json`)

You are redirected to the setup page to choose a new PIN and start with an empty database.

### 2. Reset via Docker exec (if the app is locked or inaccessible)

```bash
docker exec peoplemanager rm -f /data/pin.json /data/people.db
docker restart peoplemanager
```

Open the app — you will land on the setup page with a blank slate.

### 3. Full volume wipe (removes absolutely everything)

```bash
docker compose down
docker volume rm peoplemanager-data
docker compose up -d --build
```

The volume is recreated empty and you start from the setup page.

> If you have data you want to keep, use ⚙ → Export **before** any reset. The exported `.db` file can be imported again after setting a new PIN.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `/data/people.db` | Path to the SQLite/SQLCipher database file |
| `PIN_CONFIG` | `/data/pin.json` | Path to the PIN configuration file (PIN hash + salt + timeout) |
| `MAX_UPLOAD_MB` | `32` | Maximum accepted upload size (MB); larger requests are rejected with HTTP 413 |

Override by adding an `environment:` entry in `docker-compose.yml`:

```yaml
    environment:
      DB_PATH: /data/custom.db
```

Then apply it with `docker compose up -d --build`. (With a plain `docker run`, pass
`-e DB_PATH=/data/custom.db` instead.)

---

## Security

The database is encrypted at rest with **SQLCipher (AES-256)** using a key
derived from your PIN (PBKDF2-HMAC-SHA256). On top of that, the app applies:

- an **Origin/Referer check** on all state-changing requests (CSRF defence in
  depth over the `SameSite=Lax`, `HttpOnly` session cookie);
- **image upload hardening** — the served content type of photos/pictures is
  pinned to a safe raster type from the file extension (SVG and non-images are
  rejected), plus an `X-Content-Type-Options: nosniff` response header;
- an **upload size cap** (`MAX_UPLOAD_MB`, default 32 MB);
- an **escalating cooldown** after repeated failed PIN attempts.

The full threat model, findings, and operational recommendations (including the
LAN-exposure note for the default `0.0.0.0` binding) are in
**[SECURITY.md](SECURITY.md)**. If you don't need LAN access, publish the port
to localhost only — change `ports:` in `docker-compose.yml` to
`"127.0.0.1:8081:8080"`.

---

## Development

### Module layout

The implementation lives in the `peoplecrm/` package. `app.py` is a thin
entrypoint (`app = create_app()`) that also re-exports a few helpers for the
test suite.

| Module | Responsibility |
|---|---|
| `peoplecrm/__init__.py` | App factory — secret key, cookie flags, upload cap, CSRF/origin guard, security headers, blueprint registration |
| `peoplecrm/config.py` | Paths (env-resolved) and allowed-extension / image-mime constants |
| `peoplecrm/security.py` | PIN config, key derivation, unlock sessions, `require_unlock` guard |
| `peoplecrm/db.py` | Plain/SQLCipher connections, schema, plain→encrypted migration |
| `peoplecrm/helpers.py` | `normalize_id`, `human_size`, people aggregation, Jinja filters |
| `peoplecrm/routes/auth.py` | setup / lock / reset / change-PIN / timeout / unlock throttle |
| `peoplecrm/routes/pages.py` | home page, person detail, navigation tree |
| `peoplecrm/routes/records.py` | person / meeting / task / note / category CRUD |
| `peoplecrm/routes/files.py` | photo / document / picture upload–download–delete |
| `peoplecrm/routes/data.py` | encrypted export / import |

### Running the tests

The suite runs locally without Docker. Production pins `sqlcipher3==0.5.3`
(compiled against `libsqlcipher`); locally the prebuilt `sqlcipher3-binary`
wheel from `requirements-dev.txt` is a drop-in.

```bash
python -m venv venv
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest
```

The tests point `DB_PATH` / `PIN_CONFIG` at a throwaway temp directory, so they
never touch your real data volume.

---

## Troubleshooting

**No people appear on the home page**
Add someone via the **+ Person** button — the app starts empty.

**Container exits immediately**
Check logs: `docker logs peoplemanager`

**I deleted a category but people disappeared**
They were reassigned to the fallback category, not deleted. Check the other category filter options or use the search bar.

**I forgot my PIN and the "Forgot PIN?" link isn't available**
```bash
docker exec peoplemanager rm /data/pin.json /data/people.db
docker restart peoplemanager
```
This wipes the encrypted database. If you have an exported backup, import it after setting a new PIN.

**I want to wipe all data and start completely fresh**
See [Starting fresh / full reset](#starting-fresh--full-reset) above.
