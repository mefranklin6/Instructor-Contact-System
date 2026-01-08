# Instructor-Contact-System

TDx Project 409007

## Setup

1. Make a branch of the project

2. Make sure Rancher Desktop is installed and running (not Docker Desktop)

3. Clone the branch

4. Make a file called `.env` in the root of this repository. Copy the `env.example` contents into it and change the settings.

5. Make your feature in it's own file and as modular as possible.  Ex: /src/data_loader/data_loader.py with class DataLoader.

## Do

- Make sure you don't commit any secrets
- Develop with the goal of this being open-source
- Send pull requests for review before merge into main
- Add logging
- Add methods that can be used across modules to /src/utils

```python
import logging as log
log.warning("This is a warning")
log.debug("This is for traces")
```

## Style

- Black Formatter to run *on save*
- iSort import formatter. (some style will be overwritten by black)
- PEP 8
- Type Annotations

## Run

In a terminal:

```powershell
cd <to your cloned the repo>
docker compose up -d
```

In a browser: go to `127.0.0.1:8080`
