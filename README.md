# 1:1 Notes

A local Flask web app for managing skip-level 1:1 meetings. Runs in your browser, stores all data in a single file on your machine.

## Features

- **People** — manage your skip-level reports with name, title, and team
- **Meetings** — record agenda, notes, action items, and a 1–5 sentiment rating per meeting
- **Upcoming / Completed** — meetings split into upcoming (not yet marked done) and completed sections on both the dashboard and each person's page
- **Dashboard** — upcoming meetings and the last 5 completed meetings at a glance, plus all open action items across everyone
- **Action items** — track owner and due date; mark done from any meeting or directly from the dashboard
- **Search** — full-text search across all meeting fields (person, date, agenda, notes, action items)
- **Backup** — one-click timestamped download; choose plaintext JSON or encrypted when encryption is enabled
- **Encryption** — optional AES encryption of the data file; password is entered once at startup in the terminal
- **Light / dark mode** — toggle in the nav bar; preference is saved in the browser

## Requirements

- Python 3.10+
- Flask
- cryptography

## Setup

```bash
pip3 install -r requirements.txt
python3 app.py
```

Then open [http://localhost:5001](http://localhost:5001) in your browser.

## Data storage

All data is saved to `data/meetings.json` (or `data/meetings.enc` when encryption is enabled). Both files are excluded from git — they live only on your machine, or sync via OneDrive if you run the app from a synced folder.

## Encryption

Enable encryption from the **⚙ Settings** page. Once enabled:

- Data is stored in `data/meetings.enc` instead of `data/meetings.json`
- The app will prompt for your password in the terminal each time it starts — the password is never stored to disk
- The **↓ Backup** button offers a choice of plaintext JSON or encrypted download
- To disable, enter your current password on the Settings page — data is decrypted and saved back to `meetings.json`

> **There is no password recovery.** If you forget your password your data cannot be decrypted.

## Running on multiple machines

If you keep the project folder in OneDrive (or another sync service), the data file syncs automatically. Avoid running the app on two machines at the same time to prevent write conflicts.
