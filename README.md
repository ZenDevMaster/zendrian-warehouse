# 📦 Zendrian Warehouse

A web-based warehouse inventory management and stocktaking application built with Flask. Features include barcode scanning, inventory tracking, spot-check auditing, session management, user authentication, and administrative tools.

## Features

- **Barcode Scanning** — Scan barcodes to add, subtract, or bulk-adjust inventory quantities in real time
- **Location-Based Inventory** — Track inventory by warehouse location with per-location SKU counts
- **Session Management** — Create, manage, and close stocktake sessions with unique session codes
- **Spot-Check Auditing** — Verify completed stocktakes by selecting specific locations or a random percentage for re-counting
- **User Authentication** — Secure login with password hashing, role-based access (admin/operator)
- **Admin Panel** — Manage users, view session statistics, configure spot checks, and review audit results
- **Real-Time Feedback** — Audio cues and visual feedback for scan events (success, error, new location, delete)
- **Export Support** — Export session data for external reporting and analysis
- **Responsive Design** — Tablet-first responsive UI optimised for warehouse environments
- **Audit Trail** — Append-only scan log for complete traceability of every inventory action

## Requirements

- Python 3.10+
- pip

### Python Dependencies

| Package            | Version |
|--------------------|---------|
| Flask              | 3.1.0   |
| Flask-SQLAlchemy   | 3.1.1   |
| Flask-Login        | 0.6.3   |
| Gunicorn           | 23.0.0  |

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/ZenDevMaster/zendrian-warehouse.git
   cd zendrian-warehouse
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**

   ```bash
   python app.py
   ```

   The application will be available at `http://localhost:5000`.

## Configuration

Configuration is managed via environment variables or the [`config.py`](config.py) file.

| Variable              | Default       | Description                              |
|-----------------------|---------------|------------------------------------------|
| `SECRET_KEY`          | Auto-generated| Flask secret key for session signing     |
| `DATABASE_URL`        | SQLite (local)| Database connection URI                  |
| `MIN_SCAN_INTERVAL`   | `0.7`         | Minimum seconds between duplicate scans  |
| `DEFAULT_ADMIN_USER`  | `admin`       | Default admin username (first run only)  |
| `DEFAULT_ADMIN_PASS`  | `warehouse`   | Default admin password (first run only)  |

The SQLite database is stored at `instance/zendrian_warehouse.db` by default.

### Production Deployment

For production, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

Set `SECRET_KEY` to a strong, persistent value and change the default admin credentials immediately after first login.

## Docker Deployment

The application includes full Docker support for containerised deployment, with options for standalone use or behind a reverse proxy.

### Quick Start with Docker

Pull and run the pre-built image directly:

```bash
docker run -d \
  --name zendrian-warehouse \
  -p 8000:8000 \
  -v warehouse_data:/app/instance \
  -e SECRET_KEY=your-secret-key-here \
  ghcr.io/zendevmaster/zendrian-warehouse:latest
```

The application will be available at `http://localhost:8000`.

### Docker Compose

For a more manageable setup, use Docker Compose:

```bash
cp .env.example .env
# Edit .env with your settings
docker compose up -d
```

This handles volume mounts, environment variables, restart policies, and health checks automatically.

### Reverse Proxy Options

#### Traefik

```bash
docker compose -f docker-compose.traefik.yml up -d
```

#### Nginx

```bash
docker compose -f docker-compose.nginx.yml up -d
```

> **Note:** Edit the domain names and SSL certificate paths in the respective compose file before deploying. Refer to [`docker-compose.traefik.yml`](docker-compose.traefik.yml) and [`docker-compose.nginx.yml`](docker-compose.nginx.yml) for configuration details.

### Building Locally

To build the image from source instead of pulling from the registry:

```bash
docker build -t zendrian-warehouse .
docker run -d -p 8000:8000 -v warehouse_data:/app/instance zendrian-warehouse
```

### Environment Variables

All Docker environment variables match the application configuration described in the [Configuration](#configuration) section above. The [`.env.example`](.env.example) file contains every supported variable with inline documentation — copy it to `.env` and adjust as needed.

### Data Persistence

The `instance/` directory inside the container holds the SQLite database (`zendrian_warehouse.db`). This **must** be persisted using a Docker volume to avoid data loss when the container is recreated.

- The `docker-compose.yml` file configures a named volume (`warehouse_data`) automatically.
- When using `docker run`, pass `-v warehouse_data:/app/instance` to mount the volume.

### Database Configuration

By default, Zendrian Warehouse uses **SQLite** — no extra dependencies or services are needed. The database file is stored at `instance/zendrian_warehouse.db`.

To switch to **MariaDB/MySQL**:

1. **Install the Python driver:**

   Uncomment `PyMySQL` in [`requirements.txt`](requirements.txt), or install manually:

   ```bash
   pip install PyMySQL>=1.1.0
   ```

2. **Update `DATABASE_URL` in your `.env` file:**

   ```
   DATABASE_URL=mysql+pymysql://warehouse_user:warehouse_pass@mariadb:3306/zendrian_warehouse
   ```

3. **For Docker deployments**, use the MariaDB compose override:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.mariadb.yml up -d
   ```

   This starts a MariaDB 11 container alongside the application with persistent storage, health checks, and pre-configured credentials. Edit [`docker-compose.mariadb.yml`](docker-compose.mariadb.yml) to change the default database credentials before deploying.

> **Note:** All queries use the SQLAlchemy ORM, so both SQLite and MySQL/MariaDB are fully supported without any application code changes.

## Usage

1. **Login** with the default admin credentials (`admin` / `warehouse`)
2. **Change the default password** via the admin panel
3. **Create a stocktake session** from the dashboard
4. **Scan barcodes** — first scan sets the location, subsequent scans add SKUs
5. **Review inventory** in real time as items are scanned
6. **Close the session** when the stocktake is complete
7. **Run spot checks** from the admin panel to verify accuracy

## Project Structure

```
zendrian_warehouse/
├── app.py                  # Flask application factory
├── config.py               # Application configuration
├── models.py               # SQLAlchemy database models
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Standalone Docker Compose config
├── docker-compose.mariadb.yml  # MariaDB override config
├── docker-compose.traefik.yml  # Traefik reverse proxy config
├── docker-compose.nginx.yml    # Nginx reverse proxy config
├── .dockerignore           # Docker build exclusions
├── .env.example            # Environment variable template
├── nginx/
│   └── nginx.conf          # Nginx reverse proxy configuration
├── .github/
│   └── workflows/
│       └── docker-publish.yml  # CI/CD Docker image publishing
├── routes/                 # Flask blueprint route handlers
│   ├── admin.py            # Admin panel routes
│   ├── auth.py             # Authentication routes
│   ├── dashboard.py        # Dashboard routes
│   └── scanning.py         # Barcode scanning routes
├── services/               # Business logic services
│   ├── export_service.py   # Data export functionality
│   ├── scan_service.py     # Scan processing logic
│   ├── session_service.py  # Session management
│   └── spotcheck_service.py# Spot-check audit logic
├── static/                 # Static assets (CSS, JS, sounds)
│   ├── css/style.css
│   ├── js/
│   └── sounds/
└── templates/              # Jinja2 HTML templates
    ├── base.html
    ├── dashboard.html
    ├── login.html
    ├── scan.html
    ├── admin*.html
    └── fragments/          # HTMX partial templates
```

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

Copyright © 2026 Zendrian Inc

See the [LICENSE](LICENSE) file for the full license text.
