# Instructor-Contact-System

An automated, location and time-driven email system developed by Chico State to support efficient communication with instructors about classroom technology and facilities.

## Overview

This system enables technicians to quickly identify and contact instructors based on where and when they teach.

The system is designed to ensure reliable classroom environments by making it easier to communicate proactively and reactively with instructors across campus.

## Background

For many years, Chico State CTS conducted early-semester outreach by manually emailing instructors to confirm that classroom technology was functioning as expected and to encourage early reporting of issues. As the campus grew, this approach became difficult to sustain due to:

- An increased number of classrooms  
- More complex scheduling  
- Reduced availability of student worker hours  

This system automates that process while expanding its capabilities.

## Core Capabilities

### Two-Way Communication Model

The system supports communication in two directions:

1. **Room → Instructors**  
   Contact all instructors scheduled to teach in a specific classroom or group of classrooms within a defined time window.

2. **Instructor → Rooms**  
   Identify all rooms an instructor is scheduled to teach in and tailor communication accordingly.

## Features

- Location- and time-driven instructor lookup  
- Integration with class scheduling data  
- Automatic instructor ID to email address resolution  
- User-authored email templates with dynamic variable injection
- Controlled "wave" sending to manage response volume for campus-wide scenarios
- All contact recorded through a persistent Docker volume
- Test mode with server diagnostics
- GUI is built using flet, so it is multi-platform and even works on mobile

## Primary Use Cases

- Early-semester outreach to confirm classroom readiness  
- Notifying instructors of power outages or facilities issues  
- Communicating equipment replacements or room configuration changes  
- Sending targeted updates to all users of a specific space  
- Providing instructors with a consolidated list of the rooms they teach in  
- Distributing classroom-related surveys or feedback requests

## Goals

- Improve operational efficiency  
- Reduce manual administrative coordination  
- Enable faster issue response  
- Provide scalable communication tools as campus grows  
- Support reliable teaching and learning environments  

## Requirements

This system is designed to be modular, but was built with Chico State's tech stack first. In a perfect world, all data would be gathered by API calls, but that is not our current reality. In order to use different systems and data sources, additional modules will need to be written. As of today, the following data sources are supported:

### Calendar Data (required)

Options:

- The CSV that is exported from PeopleSoft and ingested by MetaBIM Facilities Link

### Employee ID to Email key (required)

Options:

- **Zoom CSV** (bundled plugin): The CSV Users Report from Zoom Admin center

- **Active Directory API** (bundled plugin): Live queries AD for the ID to Email keys. Note: Is not compatible with running in Docker. Must run on a domain-joined workstation with proper privileges and RSAT.

- **Active Directory JSON** (bundled plugin): Use a script to generate an AD report. The system will use the saved file as the data source.

### Supported Locations (for now, Chico only and fully optional)

- Sharepoint CSV export of the Supported Locations page (bundled plugin)

## Run it

### Option 1: Docker (recommended)

1. Create `.env` in the repo root (copy from [env.example](env.example)).
2. Create `messages.py` in the repo root (copy from [messages.py.example](messages.py.example)).
3. Run:

```powershell
docker compose up --build
```

App will be available at `http://localhost:8080`.

### Option 2: Local (Python)

```powershell
pip install -r requirements.txt
pip install python-dotenv
python main.py
```

---

## Configuration (.env)

See [env.example](env.example) for a starting point.

### Key settings

- **DEV_MODE**
  - `True`: emails are not sent; actions are logged instead.
  - `False`: real emails are sent.

- **SUPPORTED_LOCATIONS_MODE**
  - `none` (no filtering)
  - `chico` (bundled parser)

- **ID_TO_EMAIL_MODULE** (required)
  - `zoom_csv` (bundled)
  - `ad_api` (bundled; **not supported in Docker**)
  - `ad_json` (bundled)

- **SCHEDULE_MODULE** (required)
  - `fl_csv` (bundled)

### File-path settings (used depending on modes)

- `SUPPORTED_LOCATIONS_FILE_PATH` (required when `SUPPORTED_LOCATIONS_MODE=chico`)
- `ZOOM_CSV_PATH` (required when `ID_TO_EMAIL_MODULE=zoom_csv`)
- `FL_FILE_PATH` (required when `SCHEDULE_MODULE=fl_csv`)

---

## Contributing: Adding a new bundled plugin

1. Add your implementation under [plugins/](plugins/__init__.py).
2. Add a new key branch in [src/plugins/system_plugins.py](src/plugins/system_plugins.py).
3. Add tests under [tests/](tests/).
4. Open a PR.

---

## Bundled plugins included in this repo

These keys are wired in [`src.plugins.system_plugins`](src/plugins/system_plugins.py):

### Supported locations

- `chico` → [plugins/chico_supported_location_parser.py](plugins/chico_supported_location_parser.py)

### ID→Email matchers

- `zoom_csv` → [plugins/id_matcher_from_zoom_users.py](plugins/id_matcher_from_zoom_users.py)
- `ad_api` → [plugins/id_matcher_from_ad_api.py](plugins/id_matcher_from_ad_api.py) (**not Docker compatible**)
- `ad_json` → [plugins/id_matcher_from_ad_json.py](plugins/id_matcher_from_ad_json.py)

### Schedule loader

- `fl_csv` → [plugins/fl_data_loader.py](plugins/fl_data_loader.py)

---

## Lint + tests

```powershell
ruff format .
ruff check .
pytest -q
```

---

## Notes / gotchas

- `ad_api` runs PowerShell AD queries and is blocked in Docker by design (see [`src.plugins.system_plugins.create_id_matcher`](src/plugins/system_plugins.py)).

- Stick with one deployment method.  If you mix local Python and Docker, you will have two different 'contact history' logs. In start-of-semester mode, that means instructors could be contacted multiple times.
