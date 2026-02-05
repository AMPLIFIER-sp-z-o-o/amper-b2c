
# 🚀 AMPER B2C – Docker Deployment Guide

This guide describes the **production-like deployment** of AMPER B2C using Docker Compose, Redis, Celery workers, and `nginx-proxy` with Let's Encrypt.

This setup is the same architecture used on our public demo.

## 🧱 Architecture

Services started by this stack:

| Service | Purpose |
|---|---|
| `b2c` | Main Django ASGI app (Gunicorn + Uvicorn worker) |
| `celery` | Background async tasks |
| `celerybeat` | Scheduled tasks |
| `redis` | Cache & Celery broker |
| `static` | Nginx serving collected static files |

The stack expects an existing **nginx-proxy** network for automatic HTTPS and domain routing.

## 📦 Requirements

You must already have running:

- Docker & Docker Compose
- `nginx-proxy` with Let's Encrypt companion
- External Docker networks:
  - `nginx-proxy`
  - `amper-b2c`

Create networks if they don't exist:

```bash
docker network create nginx-proxy
docker network create amper-b2c
```

## 📁 Directory structure

Create a directory for the deployment:

```
amper-b2c/
 ├─ docker-compose.yml
 ├─ b2c.env
 ├─ static/
 └─ redis/
```

- `static/` – will contain collected static files
- `redis/` – redis data directory

## ⚙️ Environment configuration

Copy and edit:

```
b2c.env
```

This file contains all Django, database, email, and app configuration.

## ▶️ Start the stack

```bash
docker compose up -d
```

Containers started:

- `amper-b2c-demo`
- `amper-b2c-celery`
- `amper-b2c-celerybeat`
- `amper-b2c-redis`
- `amper-b2c-static`

## 🌐 Domains & HTTPS

Domains are configured via environment variables in compose:

- `amper-b2c.ampliapps.com` → main app
- `amper-b2c-static.ampliapps.com` → static files

These are handled automatically by **nginx-proxy** and Let's Encrypt.

To use your own domain, change:

```
VIRTUAL_HOST
LETSENCRYPT_HOST
LETSENCRYPT_EMAIL
```

in the compose file.

## 🗂 Static files (important)

After first start, collect static files:

```bash
docker exec -it amper-b2c-demo python manage.py collectstatic --noinput
```

They will be served by the `static` nginx container.

## 🧠 How the app runs

Main container runs:

```
gunicorn amplifier.asgi:application -k uvicorn.workers.UvicornWorker --threads 8 --timeout 0
```

This means:

- ASGI (WebSockets ready)
- High concurrency without multiple workers
- Optimized for I/O bound e-commerce traffic

## 🧵 Celery workers

- `celery` handles async jobs (emails, integrations, background tasks)
- `celerybeat` handles scheduled jobs

Both use Redis as broker.

## 🧯 Redis configuration

Redis is configured as:

- no persistence (cache/broker only)
- LRU eviction
- 500MB memory limit

Safe for production use as cache/broker.

## 🔄 Updating to a new version

```bash
docker compose pull
docker compose up -d
```

Then run migrations:

```bash
docker exec -it amper-b2c-demo python manage.py migrate
```

## 🩺 Health check

Check logs:

```bash
docker logs -f amper-b2c-demo
docker logs -f amper-b2c-celery
```

## 🧹 Restarting services

```bash
docker compose restart
```

## 🧩 Using your own domain

Edit in compose:

```
VIRTUAL_HOST=shop.yourdomain.com
LETSENCRYPT_HOST=shop.yourdomain.com
```

No nginx config required.

## 🏁 Result

You get a fully working:

- HTTPS e-commerce app
- Background workers
- Static separation
- Production-grade ASGI stack
- Reverse proxy & certificates auto-managed

## 🤝 Need help?

AMPER B2C is MIT licensed — you can run it fully on your own.

If you want help with deployment, scaling, integrations, or production setup — contact us at **support@ampliapps.com**.
