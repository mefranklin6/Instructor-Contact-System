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

- The CSV that is exported from PeopleSoft and ingested by MetaBIM Facilities Link

### Employee ID to Email key (required)

- The CSV Users Report from Zoom Admin center
- Future: Zoom API

### Supported Locations (for now, Chico only and fully optional)

- Sharepoint CSV export of the Supported Locations page

### Docker Runtime

- Linux, or Windows through Rancher Desktop

## Setup

1. Make sure Docker Engine is installed and running. (If using Windows, suggest installing Rancher Desktop)

2. Clone the project locally

3. Make a file called `.env` in the root of the repository. Copy the `env.example` contents into it and change the settings as needed.

4. Make a file called `messages.py` in the root of the repository. Copy the `messages.py.example` contents into it and change the settings as needed.

5. `cd` to your repository root and run `docker compose up`

6. The webserver is at `http://<your_address_or_localhost>:8080`

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
