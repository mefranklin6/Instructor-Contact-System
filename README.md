# Instructor-Contact-System

An automated instructor lookup and contact system designed to support higher education classroom technology teams.

## Overview

![picture of start of semester interface](/images/start_of_semester.png)
This system enables technicians to quickly identify and contact instructors based on where and when they teach.

The system is designed to ensure reliable classroom environments by making it easier to communicate proactively and reactively with instructors across campus.

## Background

For many years, Chico State Classroom Technology Services conducted early-semester outreach by manually emailing instructors to confirm that classroom technology was functioning as expected and to encourage early reporting of issues. As the campus grew, this approach became difficult to sustain due to:

- An increased number of classrooms  
- More complex scheduling  
- Reduced availability of student worker hours  

This system automates that process while expanding its capabilities.

## Core Capabilities

### Two-Way Communication Model

The system supports communication in two directions:

1. **Room → Instructors**  
   Contact all instructors scheduled to teach in a specific classroom or group of classrooms within a defined time window.
![rooms per instructor interface](/images/by_instructor.png)

2. **Instructor → Rooms**  
   Identify all rooms an instructor is scheduled to teach in and tailor communication accordingly.
![instructor to room interface](/images/by_classroom.png)

## Features

- Location- and time-driven instructor lookup  
- Integration with multiple systems and data sources
- Automatic instructor ID to email address resolution  
- User-authored email templates with dynamic variable injection
- Controlled "wave" sending to manage response volume for campus-wide scenarios
- All contact recorded through a persistent Docker volume (or on-disk volume if running Python)
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

## System Requirements

This system can run in either Docker or Python.

### Docker (recommended)

- Docker Engine installed and running. If using Windows, we suggest Rancher Desktop on WSL.

### Python

- Python 3.14+
- Pip

## Data Source Requirements

This system is designed to be modular and uses plugins for interacting with specific data sources, such as calendars. It was built with Chico State's tech stack first. In a perfect world, all data would be gathered by API calls, but that is not Chico's current reality. In order to use different systems and data sources, additional plugins can be written. As of today, the following plugins are included:

### Calendar Data (required)

Plugins:

- The CSV that is exported from PeopleSoft and ingested by MetaBIM Facilities Link

### Employee ID to Email key (required if not in calendar data)

If using FacilitiesLink import file, you will only find Employee ID's there and need this module to map ID's to emails.

Plugins:

- **Zoom CSV**: The CSV Users Report from Zoom Admin center

- **Active Directory API**: Live queries AD for the ID to Email keys. Note: Is not compatible with running in Docker. Must run on a domain-joined workstation with proper privileges and RSAT.

- **Active Directory JSON**: Use a script to generate an AD report. The system will use the saved file as the data source. If running in docker, you'll need to run the [script](scripts/query_ad.ps1) on a Windows workstation first.

### Supported Locations (for now, Chico only and fully optional)

Plugins:

- Sharepoint CSV export of the Chico CTS Supported Locations page

#### Note that any plugins that rely on files instead of API calls raise Runtime Errors if the files are older than one month

## Configuration (.env)

See [env.example](env.example) for a starting point.

### Key settings

- **DEV_MODE**
  - `True`: emails are not sent. For testing only.
  - `False`: real emails are sent.

- **SUPPORTED_LOCATIONS_MODE**
  - `none` (no filtering)
  - `chico` (only for use at Chico State)

- **ID_TO_EMAIL_MODULE** (required)
  - `zoom_csv`
  - `ad_api`  (**not supported in Docker**)
  - `ad_json`

- **SCHEDULE_MODULE** (required)
  - `fl_csv`: FacilitiesLink CSV Import File

### File-path settings (used depending on modes)

- `SUPPORTED_LOCATIONS_FILE_PATH` (required when `SUPPORTED_LOCATIONS_MODE=chico`): This is the Chico Supported Locations Sharepoint CSV. Chico Only.
- `ZOOM_CSV_PATH` (required when `ID_TO_EMAIL_MODULE=zoom_csv`). This can be exported by a Zoom Admin under Admin -> User Management -> Users -> Export All users in the table.
- `FL_FILE_PATH` (required when `SCHEDULE_MODULE=fl_csv`). This is the data that gets exported from PeopleSoft to MetaBIM FacilitiesLink.

## Run it

1. Clone this repo
2. Create `.env` in the repo root (copy from [env.example](env.example). See below for details).
3. Create `messages.py` in the repo root (copy from [messages.py.example](messages.py.example)).
4. Optional: Put any data source files in the root of your repo (calendar CSV data, etc)

### Option 1: Docker (recommended)

```powershell
docker compose up --build
```

### Option 2: Local Python

1. Create `.env` in the repo root (copy from [env.example](env.example). See below for details).
2. Create `messages.py` in the repo root (copy from [messages.py.example](messages.py.example)).

3. ```powershell
    pip install -r requirements.txt
    pip install python-dotenv
    python main.py
    ```

App will be available at `http://localhost:8080`.

## Contributing: Requirements

- Ruff formatter and linter
- PEP 8

## Contributing: Adding a new bundled plugin

Bundled plugins are plain Python modules under the optional [`plugins/`](plugins/__init__.py) package. They are loaded by key strings from environment-driven settings (see [`src.core.settings.Settings`](src/core/settings.py)) via the factory layer in [`src.core.system_plugins`](src/core/system_plugins.py).

### 1) Implement the plugin in `plugins/`

Create a new module file under [`plugins/`](plugins/__init__.py) (for example `plugins/my_new_plugin.py`). The system expects different interfaces depending on what you’re extending:

- **Supported locations** (optional, but can limit the scope of the tool to only places you support): factory is [`core.system_plugins.create_supported_locations`](src/core/system_plugins.py).  
  Return value should be `list[tuple[str, str]]` (e.g. `[("SCI","110"), ...]`) or `None`.

- **ID → email matcher** (used when `ID_TO_EMAIL_MODULE=...`): factory is [`core.system_plugins.create_id_matcher`](src/core/system_plugins.py).  
  The created object must implement `match_id_to_email(emp_id: str) -> str` (see examples in [`plugins.id_matcher_from_zoom_users_csv.Matcher`](plugins/id_matcher_from_zoom_users_csv.py), [`plugins.id_matcher_from_ad_json.Matcher`](plugins/id_matcher_from_ad_json.py)).

- **Schedule loader** (required): factory is [`core.system_plugins.create_schedule_loader`](src/core/system_plugins.py).  
  The created object must implement:
  - `semester_data(date: datetime) -> pd.DataFrame | None`
  - `range_data(start_date: datetime, end_date: datetime) -> pd.DataFrame`  
  (see [`plugins.fl_data_loader.DataLoader`](plugins/fl_data_loader.py)).

### 2) Wire the key into the factory layer

Add a new branch in the appropriate factory in [`src/core/system_plugins.py`](src/core/system_plugins.py). Factories import plugins using `_bundled_import("module_name")`, which resolves to `plugins.<module_name>`.

If your plugin depends on an input file, enforce the “freshness” rule using [`src.utils.file_is_stale`](src/utils.py) (current behavior: file-based sources raise `RuntimeError` if older than one month; see [`tests/stale_file_test.py`](tests/stale_file_test.py)).

### 3) Add any new configuration settings

If your plugin needs additional env vars / settings, extend [`src.core.settings.Settings`](src/core/settings.py) and update:

- [`env.example`](env.example)
- this README’s configuration section (as needed)

### 4) Add tests

Add tests under [`tests/`](tests/) covering:

- Factory wiring (see [`tests/plugin_system_test.py`](tests/plugin_system_test.py))
- Stale-file behavior for file-backed plugins (see [`tests/stale_file_test.py`](tests/stale_file_test.py))
- Any loader-specific behavior (see [`tests/fl_data_loader_cleaning_test.py`](tests/fl_data_loader_cleaning_test.py), [`tests/fl_date_range_filtering_test.py`](tests/fl_date_range_filtering_test.py))

### 5) Run lint and tests

```powershell
ruff format .
ruff check .
pytest -q
```

## Notes / gotchas

- `ad_api` runs PowerShell AD queries and is blocked in Docker by design (see [`src.plugins.system_plugins.create_id_matcher`](src/plugins/system_plugins.py)).

- Stick with one deployment method.  If you mix local Python and Docker, you will have two different 'contact history' logs. In start-of-semester mode, that means instructors could be contacted multiple times.
