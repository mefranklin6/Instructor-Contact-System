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

- **Zoom CSV**: The CSV Users Report from Zoom Admin center

- **Active Directory API**: Live queries AD for the ID to Email keys. Note: Is not compatible with running in Docker. Must run on a domain-joined workstation with proper privileges and RSAT.

- Future: Zoom API, ldap3 AD querying

### Supported Locations (for now, Chico only and fully optional)

- Sharepoint CSV export of the Supported Locations page

### Docker Runtime

- Linux, or Windows through Rancher Desktop

## Setup

1. Make sure Docker Engine is installed and running. (If using Windows, suggest installing Rancher Desktop)

2. Clone the project locally

3. Make a file called `.env` in the root of the repository. Copy the `env.example` contents into it and change the settings as needed.

4. Make a file called `messages.py` in the root of the repository. Copy the `messages.py.example` contents into it and change the settings as needed.

5. Configure your Employee ID to Email mapping method:
   - **Option A: Zoom CSV** - Set `ID_TO_EMAIL_MODULE=zoom_csv` and provide the Zoom users CSV file path
   - **Option B: Active Directory LDAP** - Set `ID_TO_EMAIL_MODULE=ad_api` (not Docker compatible)

6. `cd` to your repository root and run `docker compose up`.
      Alternatively, you can run locally if you have Python installed.

      ```pwsh
      pip install requirements.txt
      ./main.py
      ```

The webserver will be at `http://<your_address_or_localhost>:8080`

## Environmental Variables and Configuration

Details about the .env file

```bash
# ---- SMTP Configuration ----
SMTP_HOST= # your email / exchange server
SMTP_PORT= # default: 587
SMTP_FROM= # email addr you are sending from
SMTP_USERNAME= # optional
SMTP_PASSWORD= # optional

# ---- Logging ----
LOGGING_LEVEL= # See python logging documentation for levels

# ---- Developer Settings ----
DEV_MODE= # If True, no emails will actually be sent, but they will be logged

# ---- Supported Locations Module ----
SUPPORTED_LOCATIONS_MODE= # Options are: Chico
SUPPORTED_LOCATIONS_FILE_PATH= # if in mode Chico, the CSV path from SL Sharepoint export

# ---- ID to Email Module ----
ID_TO_EMAIL_MODULE= # Options: zoom_csv or ad_api
ZOOM_CSV_PATH= # If above is zoom_csv, path to the users export 

# ---- Schedule Data Module ----
SCHEDULE_MODULE= # Options are fl_csv for the FacilitiesLink ingest report
FL_FILE_PATH= # If above is 'fl_csv', the path to the CSV

```

## Contributing

1. Make a branch of the project under your own Github account

2. Follow the 'Setup' steps documented above, but clone your own branch

3. Make your feature in its' own file and as modular as possible.  Ex: /src/data_loader.py with class DataLoader.

4. Send a pull request when ready

### Do

- Make sure you don't commit any secrets or campus-specific data
- Add logging
- Add methods that can be used across modules to /src/utils

```python
import logging as log
log.warning("This is a warning")
log.debug("This is for traces")
```

### Style

- Ruff linter and formatter
- PEP 8
- Type Annotations

### Run

```powershell
cd <to your cloned the repo>
docker compose down --rmi local --remove-orphans; docker compose up --build --force-recreate --renew-anon-volumes
```

In a browser: go to `127.0.0.1:8080`

## Maintenance

### Zoom Users file

Zoom Admin -> User Management -> Users -> Export -> All users in the table

### Chico Supported Locations (Chico only)

Go to the supported locations intranet page: Export -> Export to CSV
