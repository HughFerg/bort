# Docker Setup for Bort Search

## Quick Start

### Build and run with Docker Compose (recommended):
```bash
docker-compose up --build
```

Then visit: http://localhost:8000

### Or use Docker directly:
```bash
# Build the image
docker build -t bort-search .

# Run the container
docker run -p 8000:8000 -v $(pwd)/data:/app/data bort-search
```

## How It Works

- **Port 8000**: Web server (search UI + API)
- **Volume mount**: `./data` directory is mounted so the database and frames persist
- **Frontend**: Included in the image

## Stopping

```bash
# Docker Compose
docker-compose down

# Docker
docker stop <container-id>
```

## Rebuilding

```bash
# Rebuild after code changes
docker-compose up --build
```

## Environment Configuration

Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
# Edit .env with your settings
```

Available options:
- `DATABASE_PATH` - Path to LanceDB database
- `FRAMES_PATH` - Directory containing frame images
- `PORT` - Server port (default: 8000)
- `ALLOWED_ORIGINS` - CORS origins (use * for development)
- `ADMIN_PASSWORD` - Optional password for delete operations
- `IMAGE_CDN_URL` - Optional CDN URL for frames

## Production Notes

For production deployment:
1. Copy `.env.example` to `.env` and configure
2. Set `ADMIN_PASSWORD` for delete endpoint security
3. Use a reverse proxy (nginx/Caddy) for HTTPS
4. Set up proper volume backups
5. Configure restart policies
6. Consider using an external CDN for frame images

## Data Persistence

The `data/` directory is mounted as a volume, so:
- Database changes persist across container restarts
- Frames are accessible to the container
- No need to rebuild when data changes

## Troubleshooting

**"Address already in use"**: Another service is using port 8000
```bash
# Change port in docker-compose.yml:
ports:
  - "8080:8000"  # Use 8080 instead
```

**"Cannot connect to Docker daemon"**: Start Docker Desktop

**Slow startup**: First run downloads models (~1-2 minutes), subsequent runs are faster
