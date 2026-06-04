# 1:1 Notes

A local Flask web app for managing skip-level 1:1 meetings. Runs in your browser, stores all data in a single JSON file on your machine.

## Features

- **People** — manage your skip-level reports with name, title, and team
- **Meetings** — record agenda, notes, action items, and a 1–5 sentiment rating per meeting
- **Dashboard** — see upcoming meetings and the last 5 past meetings at a glance, plus all open action items across everyone
- **Action items** — track owner and due date, mark done from any meeting or the dashboard
- **Search** — full-text search across all meeting fields
- **Backup** — one-click download of your data as a timestamped JSON file

## Requirements

- Python 3.8+
- Flask

## Setup

```bash
pip3 install flask
python3 app.py
```

Then open [http://localhost:5001](http://localhost:5001) in your browser.

## Data storage

All data is saved to `data/meetings.json`. This file is excluded from git — it lives only on your machine (or syncs via a service like OneDrive if you run the app from a synced folder).

To back up your data at any time, click the **↓ Backup** button in the nav bar. This downloads a timestamped copy of the JSON file.

## Running on multiple machines

If you keep the project folder in OneDrive (or another sync service), `data/meetings.json` will stay in sync across machines automatically. Avoid running the app on two machines at the same time to prevent write conflicts.
