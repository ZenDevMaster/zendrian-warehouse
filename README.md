# 📦 Zendrian Warehouse

A web-based warehouse stocktaking application built with Flask. Features barcode scanning, location-based inventory tracking, spot-check auditing, session management, user authentication, and admin tools.

Designed to allow rapid and continuous stock counting with a barcode scanner. Consider connecting a bluetooth scanner to your tablet for rapid stock counts. Assumes that your stock locations contain two dots (i.e. A.1.1 aisle–bay–level style codes) for parsing. In the current version of Zendrian Warehouse, this isn't configurable. As is always the case in warehouses, barcode everything for speed.

## Features

- **Barcode Scanning** — Add, subtract, or bulk-adjust inventory quantities in real time
- **Location-Based Inventory** — Track inventory by warehouse location with per-location SKU counts
- **Session Management** — Create, manage, and close stocktake sessions with unique session codes
- **Spot-Check Auditing** — Verify stocktakes by selecting specific locations or a random percentage for re-counting
- **User Authentication** — Secure login with password hashing and role-based access (admin/operator)
- **Admin Panel** — Manage users, view statistics, configure spot checks, and review audit results
- **Real-Time Feedback** — Audio cues and visual feedback for scan events
- **Export Support** — Export session data for external reporting
- **Responsive Design** — Tablet-first UI optimised for warehouse environments
- **Audit Trail** — Append-only scan log for complete traceability

## Screenshots

### Dashboard
![Dashboard — User view showing active scanning sessions](docs/screenshots/dashboard.png)

### Scanning
![Scanning screen with location A.1.1 selected](docs/screenshots/scanning.png)

![Scanning screen after scanning 5 SKUs](docs/screenshots/scanning_with_skus.png)

### Admin Panel
![Admin dashboard — summary cards, spot checks table, and all sessions](docs/screenshots/admin_dashboard.png)

![Admin user management screen](docs/screenshots/admin_users.png)

![Admin spot check configuration](docs/screenshots/admin_spotcheck.png)

## Requirements

- Python 3.10+
- pip

| Package          | Version |
|------------------|---------|
| Flask            | 3.1.0   |
| Flask-SQLAlchemy | 3.1.1   |
| Flask-Login      | 0.6.3   |
| Gunicorn         | 23.0.0  |

## Installation

```bash
git clone https://github.com/ZenDevMaster/zendrian-warehouse.git
cd zendrian-warehouse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

> **Development server runs on port 5000:** `http://localhost:5000`
>
> For production, use Gunicorn (port 8000) or Docker — see below.

## Configuration

Configuration is managed via environment variables or [`config.py`](config.py). See [`.env.example`](.env.example) for all supported variables with inline documentation.

| Variable             | Default        | Description                             |
|----------------------|----------------|-----------------------------------------|
| `SECRET_KEY`         | Auto-generated | Flask secret key for session signing    |
| `DATABASE_URL`       | SQLite (local) | Database connection URI                 |
| `MIN_SCAN_INTERVAL`  | `0.7`          | Minimum seconds between duplicate scans |
| `DEFAULT_ADMIN_USER` | `admin`        | Default admin username (first run only) |
| `DEFAULT_ADMIN_PASS` | `warehouse`    | Default admin password (first run only) |
| `STOCKTAKE_READ_API_TOKEN` | Disabled | Bearer token for read-only inventory API |

The SQLite database is stored at `instance/zendrian_warehouse.db` by default.

### Read-only API

Set `STOCKTAKE_READ_API_TOKEN` in the production environment. The API exposes
existing session and inventory records only; it has no write routes and does
not download or replace the database.

```bash
curl -fsS -H "Authorization: Bearer $STOCKTAKE_READ_API_TOKEN" \
  "https://WAREHOUSE_HOST/api/v1/sessions?owner=niel&closed_only=true&limit=10"

curl -fsS -H "Authorization: Bearer $STOCKTAKE_READ_API_TOKEN" \
  "https://WAREHOUSE_HOST/api/v1/inventory/latest?owner=niel&closed_only=true"

curl -fsS -H "Authorization: Bearer $STOCKTAKE_READ_API_TOKEN" \
  "https://WAREHOUSE_HOST/api/v1/inventory/by-date?owner=niel&closed_only=true&date=2026-08-10"

curl -fsS -H "Authorization: Bearer $STOCKTAKE_READ_API_TOKEN" \
  "https://WAREHOUSE_HOST/api/v1/sessions/SESSION_ID/inventory"
```

The latest endpoint returns both location-level rows and aggregated SKU totals.
Use `inventory/by-date` for Niel's weekly count because one count may be split
across multiple sessions on the same day.
Omit `closed_only=true` only when an in-progress Monday count is intentionally
needed. Use `since=YYYY-MM-DDTHH:MM:SS` to constrain session history.

### Production (Gunicorn)

```bash
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

> Set `SECRET_KEY` to a strong, persistent value and change the default admin credentials after first login.

## Docker Deployment

### Ports

| Method | Port | URL |
|--------|------|-----|
| `python app.py` (dev) | **5000** | `http://localhost:5000` |
| Docker / Gunicorn (prod) | **8000** | `http://localhost:8000` |

### Quick Start

```bash
docker run -d \
  --name zendrian-warehouse \
  -p 8000:8000 \
  -v warehouse_data:/app/instance \
  -e SECRET_KEY=your-secret-key-here \
  ghcr.io/zendevmaster/zendrian-warehouse:latest
```

### Docker Compose

```bash
cd /opt
git clone https://github.com/ZenDevMaster/zendrian-warehouse.git
cd zendrian-warehouse
cp .env.example .env    # edit .env with your settings
docker compose up -d
http://localhost:8000 # replace localhost with your IP if remote
```

### Build from Source

```bash
docker build -t zendrian-warehouse .
docker run -d -p 8000:8000 -v warehouse_data:/app/instance zendrian-warehouse
```

### Reverse Proxy

```bash
# Traefik
docker compose -f docker-compose.traefik.yml up -d

# Nginx
docker compose -f docker-compose.nginx.yml up -d
```

> Edit domain names and SSL paths in [`docker-compose.traefik.yml`](docker-compose.traefik.yml) or [`docker-compose.nginx.yml`](docker-compose.nginx.yml) before deploying.

### Data Persistence

The `instance/` directory holds the SQLite database and **must** be persisted with a Docker volume (`-v warehouse_data:/app/instance`). The compose files configure this automatically.

### MariaDB (Optional)

To switch from SQLite to MariaDB/MySQL:

1. Install the driver: uncomment `PyMySQL` in [`requirements.txt`](requirements.txt) or run `pip install PyMySQL>=1.1.0`
2. Set `DATABASE_URL` in `.env`:
   ```
   DATABASE_URL=mysql+pymysql://warehouse_user:warehouse_pass@mariadb:3306/zendrian_warehouse
   ```
3. Use the MariaDB compose override:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up -d
   ```

> All queries use SQLAlchemy ORM — both SQLite and MySQL/MariaDB work without code changes. Edit [`docker-compose.mariadb.yml`](docker-compose.mariadb.yml) to change default credentials.

## Usage

1. **Login** with default credentials (`admin` / `warehouse`)
2. **Change the default password** via the admin panel
3. **Create a stocktake session** from the dashboard
4. **Scan barcodes** — first scan sets the location, subsequent scans add SKUs
5. **Review inventory** in real time as items are scanned
6. **Close the session** when complete
7. **Run spot checks** from the admin panel to verify accuracy

## Project Structure

```
├── app.py                      # Flask application factory
├── config.py                   # Application configuration
├── models.py                   # SQLAlchemy database models
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container image definition
├── docker-compose*.yml         # Docker Compose configs (standalone, MariaDB, Traefik, Nginx)
├── .env.example                # Environment variable template
├── nginx/nginx.conf            # Nginx reverse proxy configuration
├── routes/                     # Flask blueprint route handlers
│   ├── admin.py, auth.py, dashboard.py, scanning.py
├── services/                   # Business logic
│   ├── export_service.py, scan_service.py, session_service.py, spotcheck_service.py
├── static/                     # CSS, JS, audio assets
├── templates/                  # Jinja2 HTML templates
│   └── fragments/              # HTMX partial templates
└── docs/screenshots/           # Application screenshots
```

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

Copyright © 2026 Zendrian Inc — see [LICENSE](LICENSE) for full text.
