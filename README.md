# Thiel T-Notes calendar

Generates a reviewable staff newsletter calendar from https://www.thiel.edu/calendar. No API key or paid service is required.

## Run it

1. Open **Actions → Build T-Notes calendar → Run workflow**.
2. Leave the start date blank for today in Pennsylvania, or enter `YYYY-MM-DD`.
3. Choose the number of days (default 10), then click **Run workflow**.
4. Open the completed run to see the calendar in its summary. Download the **t-notes-calendar** artifact for the files.
5. Review `review.md`, then copy `t-notes-calendar.md` into T-Notes. Links appear as plain labels in newsletter copy; their URLs are in the review file and `events.json`.

## Formatting

Each entry has a bold title, AP-style date and starting time, italic location and concise description. Titles are preserved with minor cleanup. Noon, month abbreviations, Biweekly, Pa., Washington & Jefferson, HMSC, Bly Hall and Stamm Hall are normalized. Soccer and football locations use Stoeber Field at Alumni Stadium. Recognized home athletics entries use “Thiel hosts [opponent] in [sport].” All calendar categories are included, sorted by date and time.

## Review limitations

This first version uses deterministic text extraction rather than a language model. Non-athletics descriptions require editorial review for AP style, voice and relevance. It takes the first source sentence; direct invitations or long sentences receive a neutral placeholder and a review warning. The full source description is retained for review. It does not reliably identify every joke or filler phrase. Missing data is labeled, never guessed. The output includes every date of a multi-day event shown on the daily calendar; remove repeated entries if desired. A failed detail request fails the run and preserves partial output for review. There is no automatic publication or weekly schedule.

## Local use

Python 3.12: `pip install -r requirements.txt`, then `python calendar_builder.py --start 2026-10-07 --days 10`.

Tests: `python -m unittest discover -s tests -v`.
