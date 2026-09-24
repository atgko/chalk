"""Sample syllabi and notes for the demo course.

Synthetic content, clearly labeled as such, shaped like the PRD's own
examples: IS 6640 (Word, 10 weeks, Fall 2026 with a Fall Break row, the
PRD section 6.2 worked example), the same course mislabeled "Spring 2026"
(the sponsor's real term-label bug, PRD section 6.1), and IS 4490
(markdown, with due dates near the November DST change).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from docx import Document

SAMPLE_NOTICE = "Sample syllabus — synthetic content for demonstrating Chalk."

_IS6640_OBJECTIVES = [
    "Understand the fundamentals of IT network infrastructure",
    "Design and document IPv4 addressing and subnetting schemes",
    "Configure and troubleshoot switches, routers, and VLANs",
    "Apply risk management and security principles to network design",
]

# (topics, assignments, note) for each of the 10 weeks, starting Aug 24, 2026.
_IS6640_WEEKS = [
    (["Course Introduction", "Network+ Mod 1: Introduction to Networking", "Network+ Mod 2: Infrastructure"],
     ["Network+ Lab A Due"], "Video Quizzes are Taken After Reading Each Chapter"),
    (["Network+ Mod 3: Addressing"], ["Network+ Lab B Due"], None),
    (["Network+ Mod 4: Protocols", "Subnetting practice"], ["Network+ Lab C Due"], None),
    (["Network+ Mod 5: Cabling"], ["Network+ Lab D Due", "Quiz 1 Due"], None),
    (["Network+ Mod 6: Wireless Networking"], ["Network+ Lab E Due"], None),
    (["Network+ Mod 7: Cloud and Virtualization"], ["Midterm Exam Due"], None),
    (["Network+ Mod 8: Subnets and VLANs"], ["Network+ Lab F Due"], None),
    (["Network+ Mod 9: Network Risk Management"], ["Network+ Lab G Due"], None),
    (["Network+ Mod 10: Security in Network Design"], ["Network+ Lab H Due", "Quiz 2 Due"], None),
    (["Final Project Presentations"], ["Final Project Due", "Final Exam Due"], None),
]

_IS6640_ASSESSMENTS = [
    ("Video Quizzes", 5), ("Labs", 25), ("Quizzes", 15), ("Midterm Exam", 20),
    ("Final Project", 20), ("Final Exam", 15),
]


def build_is6640_word_syllabus(path: Path, *, term: str = "Fall 2026", first_week: dt.date = dt.date(2026, 8, 24)) -> Path:
    document = Document()
    document.add_paragraph(SAMPLE_NOTICE).runs[0].italic = True
    for label, value in (
        ("Course", "IS 6640 Networking and Servers"),
        ("Course Number", "IS 6640"),
        ("Section", "090"),
        ("Credits", "3"),
        ("Term", term),
        ("Instructor", "Sample Instructor"),
        ("Meeting Pattern", "Online async"),
    ):
        document.add_paragraph(f"{label}: {value}")

    document.add_paragraph("Learning Objectives", style="Heading 1")
    for objective in _IS6640_OBJECTIVES:
        document.add_paragraph(objective, style="List Bullet")

    document.add_paragraph("Schedule", style="Heading 1")
    schedule = document.add_table(rows=1, cols=2)
    schedule.style = "Table Grid"
    schedule.rows[0].cells[0].text = "Week"
    schedule.rows[0].cells[1].text = "Topics / Assignments"
    for number, (topics, assignments, note) in enumerate(_IS6640_WEEKS, start=1):
        week_date = first_week + dt.timedelta(days=7 * (number - 1))
        _add_row(schedule, f"Week {number} ({week_date.month}/{week_date.day})",
                 [*topics, *assignments, *([f"Note: {note}"] if note else [])])
        if number == 7 and term == "Fall 2026":
            _add_row(schedule, "Fall Break (10/10 - 10/18)", [])

    document.add_paragraph("Grading", style="Heading 1")
    grading = document.add_table(rows=1, cols=2)
    grading.style = "Table Grid"
    grading.rows[0].cells[0].text = "Assessment"
    grading.rows[0].cells[1].text = "Weight"
    for name, weight in _IS6640_ASSESSMENTS:
        _add_row(grading, name, [f"{weight}%"])

    if term == "Fall 2026":
        document.add_paragraph("University Dates", style="Heading 1")
        dates = document.add_table(rows=1, cols=2)
        dates.style = "Table Grid"
        dates.rows[0].cells[0].text = "Event"
        dates.rows[0].cells[1].text = "Date"
        for event, when in (("Classes begin", "8/24/2026"), ("Fall Break", "10/10 - 10/18"), ("Classes end", "12/10/2026")):
            _add_row(dates, event, [when])

    document.save(str(path))
    return path


def build_is6640_term_mismatch_syllabus(path: Path) -> Path:
    """The sponsor's real bug: the term label was updated to Spring 2026
    but the schedule still starts in August."""
    return build_is6640_word_syllabus(path, term="Spring 2026")


def _add_row(table, label: str, lines: list[str]) -> None:
    cells = table.add_row().cells
    cells[0].text = label
    cells[1].text = lines[0] if lines else ""
    for line in lines[1:]:
        cells[1].add_paragraph(line)


_IS4490_TOPICS = [
    ("Course Introduction; What Counts as Emerging", "Reading 1 Due"),
    ("Machine Learning Foundations", "Reading 2 Due"),
    ("Large Language Models", "Lab 1 Due"),
    ("Prompting and Evaluation", "Lab 2 Due"),
    ("Retrieval and Grounding", "Reading 3 Due"),
    ("AI Agents", "Lab 3 Due"),
    ("Computer Vision", "Project Proposal Due"),
    ("Edge and IoT", "Lab 4 Due"),
    ("Blockchain in Practice", "Reading 4 Due"),
    ("Extended Reality", "Lab 5 Due"),
    ("Quantum Computing Basics", "Reading 5 Due"),
    ("Responsible Technology", "Lab 6 Due"),
    ("Security of Emerging Systems", "Project Draft Due"),
    ("Project Workshop", ""),
    ("Final Presentations", "Final Project Due"),
]


def build_is4490_markdown_syllabus(path: Path) -> Path:
    first_week = dt.date(2026, 8, 24)
    break_rows_before_week = {
        8: "| - | 10/10 - 10/18 | Fall Break |  |",
        14: "| - | 11/26 - 11/29 | Thanksgiving Break |  |",
    }
    rows = []
    for number, (topic, work) in enumerate(_IS4490_TOPICS, start=1):
        if number in break_rows_before_week:
            rows.append(break_rows_before_week[number])
        start = first_week + dt.timedelta(days=7 * (number - 1))
        end = start + dt.timedelta(days=6)
        rows.append(f"| {number} | {start.month}/{start.day} - {end.month}/{end.day} | {topic} | {work} |")

    content = "\n".join(
        [
            f"_{SAMPLE_NOTICE}_",
            "",
            "Course: IS 4490 Emerging Technologies",
            "Course Number: IS 4490",
            "Section: 001",
            "Credits: 3",
            "Term: Fall 2026",
            "Instructor: Sample Instructor",
            "Meeting Pattern: In-person",
            "",
            "## Learning Objectives",
            "",
            "- Explain how current emerging technologies work at a conceptual level",
            "- Evaluate the business value and risks of adopting an emerging technology",
            "- Build small prototypes that demonstrate an emerging technology",
            "",
            "## Schedule",
            "",
            "| Week | Dates | Topic | Major Work |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
            "## Grading",
            "",
            "| Assessment | Weight |",
            "| --- | --- |",
            "| Readings | 15% |",
            "| Labs | 40% |",
            "| Final Project | 45% |",
            "",
            "## University Dates",
            "",
            "| Event | Date |",
            "| --- | --- |",
            "| Classes begin | 8/24/2026 |",
            "| Fall Break | 10/10 - 10/18 |",
            "| Thanksgiving Break | 11/26 - 11/29 |",
            "| Classes end | 12/10/2026 |",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_subnetting_notes(path: Path) -> Path:
    path.write_text(
        "# Week 3 notes: subnetting (sample instructor notes)\n\n"
        "- A subnet mask splits an IPv4 address into network and host portions.\n"
        "- CIDR notation (/24, /26) counts the network bits.\n"
        "- A /26 gives 4 subnets of a /24, each with 62 usable hosts.\n"
        "- Students most often confuse the network address with the first usable host.\n"
        "- Practice: split 192.168.10.0/24 into subnets for 50, 25, and 10 hosts (VLSM).\n",
        encoding="utf-8",
    )
    return path
