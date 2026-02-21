#!/usr/bin/env python3
"""
Generate correlated demo data for ONE "current" term (based on today's date):
- exactly N rooms (default 10)
- each room gets MIN..MAX classes total
- outputs:
  out/instructors.json
  out/classes.csv

Use:
python generate_demo_data.py --rooms 10 --classes-per-room-min 3 --classes-per-room-max 6 --seed 42
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
import random
from typing import Dict, List


@dataclass(frozen=True)
class Course:
    course_id: str
    subject: str
    number: int
    title: str
    units: int
    component: str
    college_id: str
    college: str
    dept_id: str
    dept_sdesc: str


@dataclass(frozen=True)
class Room:
    building: str
    room: str


@dataclass(frozen=True)
class MeetingPattern:
    days: str
    start_time: str
    end_time: str


@dataclass(frozen=True)
class TermInfo:
    term: int
    start_date: date
    end_date: date
    label: str  # e.g., "Spring 2026"


# ---- templates ----

SUBJECTS = ["ABUS", "AGRI", "ECON", "MGMT", "FIN", "MKTG", "STAT"]
COMPONENTS = ["LEC", "LAB", "SEM"]
COLLEGES = [
    ("10", "AGR", "132-AGRI", "AGRI"),
    ("20", "BBS", "210-BUS", "BUSN"),
    ("30", "SCI", "310-MATH", "MATH"),
]

ROOM_POOL = [
    Room("PLMS", "106"),
    Room("PLMS", "201"),
    Room("PLMS", "329"),
    Room("OCNL", "254"),
    Room("THMA", "106"),
    Room("ARTS", "120"),
    Room("SAGE", "112"),
    Room("SAGE", "220"),
    Room("HOLT", "101"),
    Room("HOLT", "205"),
    Room("WREC", "12"),
    Room("KNDL", "301"),
    Room("AYRS", "140"),
    Room("AYRS", "142"),
]

MEETING_PATTERNS = [
    MeetingPattern("MWF", "9:00", "9:50"),
    MeetingPattern("MWF", "10:00", "10:50"),
    MeetingPattern("MWF", "11:00", "11:50"),
    MeetingPattern("TR", "9:30", "10:45"),
    MeetingPattern("TR", "11:00", "12:15"),
    MeetingPattern("TR", "12:30", "13:45"),
    MeetingPattern("TR", "14:00", "15:15"),
]

CLASS_HEADERS = [
    "TERM",
    "COURSE_ID",
    "CLASS_SUBJECT",
    "CLASS_NUMBER",
    "CLASS_SECTION",
    "ASSOCIATED_CLASS_NUMBER",
    "CLASS_TITLE",
    "UNITS_COURSE_MAXIMUM",
    "COMPONENT",
    "CLASS_START_DATE",
    "CLASS_END_DATE",
    "START_TIME1",
    "END_TIME1",
    "DAYS1",
    "INSTRUCTOR1_EMPLID",
    "ENROLLED_TOTAL",
    "ENROLLMENT_MAX",
    "BUILDING",
    "ROOM",
    "COLLEGE_ID",
    "COLLEGE",
    "DEPARTMENT_ID",
    "DEPARTMENT_SDESC",
]


# ---- helpers ----


def make_employee_id(existing: set[str], rng: random.Random) -> str:
    while True:
        eid = f"{rng.randint(0, 999_999_999):09d}"
        if eid not in existing:
            existing.add(eid)
            return eid


def generate_courses(n_courses: int, rng: random.Random) -> list[Course]:
    used: set[str] = set()
    courses: list[Course] = []

    def new_course_id() -> str:
        while True:
            cid = f"{rng.randint(1, 999999):06d}"
            if cid not in used:
                used.add(cid)
                return cid

    titles = [
        "Intro to Ag Business/Economics",
        "Principles of Management",
        "Applied Statistics",
        "Microeconomics",
        "Marketing Fundamentals",
        "Finance Basics",
        "Operations & Supply Chains",
        "Project Management",
        "Business Law",
    ]

    for _ in range(n_courses):
        subject = rng.choice(SUBJECTS)
        number = rng.choice([101, 110, 201, 210, 250, 301, 320])
        units = rng.choice([1, 3, 4])
        component = rng.choices(COMPONENTS, weights=[0.75, 0.2, 0.05])[0]
        college_id, college, dept_id, dept_sdesc = rng.choice(COLLEGES)

        courses.append(
            Course(
                course_id=new_course_id(),
                subject=subject,
                number=number,
                title=rng.choice(titles),
                units=units,
                component=component,
                college_id=college_id,
                college=college,
                dept_id=dept_id,
                dept_sdesc=dept_sdesc,
            )
        )
    return courses


def assign_section_and_associated(idx: int) -> tuple[str, int]:
    section = f"{(idx % 99) + 1:02d}"
    assoc = (idx % 6) + 1
    return section, assoc


def pick_enrollment(rng: random.Random) -> tuple[int, int]:
    cap = rng.choice([20, 25, 30, 35, 40, 50, 60])
    enrolled = rng.randint(max(0, cap - rng.randint(0, 15)), cap)
    return enrolled, cap


def timeslot_key(p: MeetingPattern) -> tuple[str, str, str]:
    return (p.days, p.start_time, p.end_time)


def current_term_info(today: date) -> TermInfo:
    """
    Pick a realistic "current semester" based on today's date.
    (You can tweak these ranges if your campus differs.)
    """
    y = today.year

    # crude but realistic US-style buckets
    if 1 <= today.month <= 5:
        label = f"Spring {y}"
        start = date(y, 1, 20)
        end = start + timedelta(days=16 * 7 - 3)
        term_code = int(f"{str(y)[-2:]}22")  # e.g., 2026 -> "2622"
    elif 8 <= today.month <= 12:
        label = f"Fall {y}"
        start = date(y, 8, 20)
        end = start + timedelta(days=16 * 7 - 3)
        term_code = int(f"{str(y)[-2:]}28")  # e.g., "2628"
    else:
        label = f"Summer {y}"
        start = date(y, 6, 1)
        end = start + timedelta(days=10 * 7 - 3)
        term_code = int(f"{str(y)[-2:]}24")  # e.g., "2624" (placeholder)

    return TermInfo(term=term_code, start_date=start, end_date=end, label=label)


def build_class_rows(
    term: TermInfo,
    courses: list[Course],
    instructor_ids: list[str],
    rooms: list[Room],
    classes_per_room_min: int,
    classes_per_room_max: int,
    rng: random.Random,
) -> list[dict[str, str]]:
    """
    One term only.
    Avoid time collisions within the term for:
      - room
      - instructor
    """
    rows: list[dict[str, str]] = []
    used_room_slots: set[tuple[str, str, str, str, str]] = set()  # (bldg, room, days, start, end)
    used_instr_slots: set[tuple[str, str, str, str]] = set()  # (emplid, days, start, end)

    per_room_counts = {room: rng.randint(classes_per_room_min, classes_per_room_max) for room in rooms}

    row_idx = 0
    for room, count in per_room_counts.items():
        for _ in range(count):
            course = rng.choice(courses)
            instructor = rng.choice(instructor_ids)

            tries = 0
            while True:
                tries += 1
                if tries > 2000:
                    raise RuntimeError("Scheduling stuck. Add more meeting patterns or more instructors.")

                pattern = rng.choice(MEETING_PATTERNS)
                days, start_t, end_t = timeslot_key(pattern)

                room_slot = (room.building, room.room, days, start_t, end_t)
                instr_slot = (instructor, days, start_t, end_t)

                if room_slot in used_room_slots:
                    continue
                if instr_slot in used_instr_slots:
                    instructor = rng.choice(instructor_ids)
                    continue

                used_room_slots.add(room_slot)
                used_instr_slots.add(instr_slot)
                break

            section, assoc = assign_section_and_associated(row_idx)
            enrolled, cap = pick_enrollment(rng)

            rows.append(
                {
                    "TERM": str(term.term),
                    "COURSE_ID": course.course_id,
                    "CLASS_SUBJECT": course.subject,
                    "CLASS_NUMBER": str(course.number),
                    "CLASS_SECTION": section,
                    "ASSOCIATED_CLASS_NUMBER": str(assoc),
                    "CLASS_TITLE": course.title,
                    "UNITS_COURSE_MAXIMUM": str(course.units),
                    "COMPONENT": course.component,
                    "CLASS_START_DATE": term.start_date.strftime("%d-%b-%y"),
                    "CLASS_END_DATE": term.end_date.strftime("%d-%b-%y"),
                    "START_TIME1": pattern.start_time,
                    "END_TIME1": pattern.end_time,
                    "DAYS1": pattern.days,
                    "INSTRUCTOR1_EMPLID": instructor,
                    "ENROLLED_TOTAL": str(enrolled),
                    "ENROLLMENT_MAX": str(cap),
                    "BUILDING": room.building,
                    "ROOM": room.room,
                    "COLLEGE_ID": course.college_id,
                    "COLLEGE": course.college,
                    "DEPARTMENT_ID": course.dept_id,
                    "DEPARTMENT_SDESC": course.dept_sdesc,
                }
            )
            row_idx += 1

    return rows


def write_instructors_json(path: str, instructor_map: dict[str, str]) -> None:
    data = [{"EmployeeID": eid, "EmailAddress": email} for eid, email in instructor_map.items()]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def write_classes_csv(path: str, rows: List[Dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CLASS_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="./out")
    ap.add_argument("--seed", type=int, default=42)

    ap.add_argument("--rooms", type=int, default=10)
    ap.add_argument("--classes-per-room-min", type=int, default=3)
    ap.add_argument("--classes-per-room-max", type=int, default=8)

    ap.add_argument("--courses", type=int, default=12)
    ap.add_argument("--instructors", type=int, default=20)

    ap.add_argument("--email-domain", default="csuchico.edu")
    ap.add_argument("--email-prefix", default="a")  # a1@, a2@, ...

    args = ap.parse_args()
    rng = random.Random(args.seed)

    if args.rooms > len(ROOM_POOL):
        raise SystemExit(
            f"Requested {args.rooms} rooms but ROOM_POOL only has {len(ROOM_POOL)}. Add more rooms."
        )
    if args.classes_per_room_max < args.classes_per_room_min or args.classes_per_room_min < 1:
        raise SystemExit("Invalid classes-per-room min/max.")

    os.makedirs(args.outdir, exist_ok=True)

    # Choose "current" term based on today's date
    today = date.today()
    term = current_term_info(today)

    # Pick exactly N rooms
    rooms = rng.sample(ROOM_POOL, k=args.rooms)

    # Instructors (correlated to classes.csv)
    existing_ids: set[str] = set()
    instructor_ids: list[str] = []
    instructor_map: dict[str, str] = {}
    for i in range(1, args.instructors + 1):
        eid = make_employee_id(existing_ids, rng)
        email = f"{args.email_prefix}{i}@{args.email_domain}"
        instructor_ids.append(eid)
        instructor_map[eid] = email

    courses = generate_courses(args.courses, rng)
    rows = build_class_rows(
        term=term,
        courses=courses,
        instructor_ids=instructor_ids,
        rooms=rooms,
        classes_per_room_min=args.classes_per_room_min,
        classes_per_room_max=args.classes_per_room_max,
        rng=rng,
    )

    write_instructors_json(os.path.join(args.outdir, "instructors.json"), instructor_map)
    write_classes_csv(os.path.join(args.outdir, "classes.csv"), rows)

    print(f"Term: {term.label} (TERM={term.term})")
    print(
        f"Rooms: {len(rooms)} | Total classes: {len(rows)} (range {args.rooms * args.classes_per_room_min}..{args.rooms * args.classes_per_room_max})"
    )
    print(f"Wrote: {os.path.join(args.outdir, 'instructors.json')}")
    print(f"Wrote: {os.path.join(args.outdir, 'classes.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
