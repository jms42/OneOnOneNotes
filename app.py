import base64
import getpass
import io
import json
import os
import sys
import uuid
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import Flask, render_template, request, redirect, url_for, send_file

app = Flask(__name__)

DATA_FILE      = os.path.join(os.path.dirname(__file__), "data", "meetings.json")
ENC_FILE       = os.path.join(os.path.dirname(__file__), "data", "meetings.enc")
SETTINGS_FILE  = os.path.join(os.path.dirname(__file__), "data", "settings.json")
SECRET_KEY_FILE = os.path.join(os.path.dirname(__file__), "data", ".secret_key")

# Generate and persist a secret key so sessions are stable across restarts
os.makedirs(os.path.dirname(SECRET_KEY_FILE), exist_ok=True)
if not os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, "wb") as _f:
        _f.write(os.urandom(32))
with open(SECRET_KEY_FILE, "rb") as _f:
    app.secret_key = _f.read()

# Password held in memory for the lifetime of the process
_password: str | None = None


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {"encryption_enabled": False}
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def save_settings(settings: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def verify_password(password: str, settings: dict) -> bool:
    try:
        salt  = base64.b64decode(settings["verifier_salt"])
        token = base64.b64decode(settings["verifier_token"])
        return Fernet(_derive_key(password, salt)).decrypt(token) == b"1on1notes"
    except Exception:
        return False


def encrypt_bytes(data: bytes, password: str) -> bytes:
    salt = os.urandom(16)
    token = Fernet(_derive_key(password, salt)).encrypt(data)
    return salt + token


def decrypt_bytes(raw: bytes, password: str) -> bytes:
    return Fernet(_derive_key(password, raw[:16])).decrypt(raw[16:])


def _make_verifier(password: str) -> dict:
    salt = os.urandom(16)
    token = Fernet(_derive_key(password, salt)).encrypt(b"1on1notes")
    return {
        "verifier_salt":  base64.b64encode(salt).decode(),
        "verifier_token": base64.b64encode(token).decode(),
    }


# ---------------------------------------------------------------------------
# Data load / save  (transparent encryption)
# ---------------------------------------------------------------------------

def load_data() -> dict:
    settings = load_settings()
    if settings.get("encryption_enabled"):
        if not os.path.exists(ENC_FILE):
            os.makedirs(os.path.dirname(ENC_FILE), exist_ok=True)
            return {"people": [], "meetings": []}
        with open(ENC_FILE, "rb") as f:
            raw = f.read()
        return json.loads(decrypt_bytes(raw, _password))
    else:
        if not os.path.exists(DATA_FILE):
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            return {"people": [], "meetings": []}
        with open(DATA_FILE) as f:
            return json.load(f)


def save_data(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if load_settings().get("encryption_enabled"):
        with open(ENC_FILE, "wb") as f:
            f.write(encrypt_bytes(json.dumps(data).encode(), _password))
    else:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def new_id() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# Routes — dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    data = load_data()
    upcoming = sorted(
        [m for m in data["meetings"] if not m.get("completed", False)],
        key=lambda m: m["date"],
    )
    past = sorted(
        [m for m in data["meetings"] if m.get("completed", False)],
        key=lambda m: m["date"],
        reverse=True,
    )[:5]
    people_map = {p["id"]: p for p in data["people"]}
    open_actions = []
    for m in data["meetings"]:
        for a in m.get("action_items", []):
            if not a.get("completed"):
                open_actions.append({
                    **a,
                    "meeting_id": m["id"],
                    "meeting_date": m["date"],
                    "person": people_map.get(m["person_id"], {}).get("name", "Unknown"),
                })
    open_actions.sort(key=lambda a: a.get("due_date") or "9999")
    return render_template(
        "index.html",
        upcoming=upcoming,
        past=past,
        people_map=people_map,
        open_actions=open_actions[:10],
    )


# ---------------------------------------------------------------------------
# Routes — people
# ---------------------------------------------------------------------------

@app.route("/people")
def people():
    data = load_data()
    meeting_counts = {}
    for m in data["meetings"]:
        meeting_counts[m["person_id"]] = meeting_counts.get(m["person_id"], 0) + 1
    return render_template("people.html", people=data["people"], meeting_counts=meeting_counts)


@app.route("/people/add", methods=["POST"])
def add_person():
    data = load_data()
    person = {
        "id": new_id(),
        "name": request.form["name"].strip(),
        "title": request.form.get("title", "").strip(),
        "team": request.form.get("team", "").strip(),
        "created_at": now(),
    }
    data["people"].append(person)
    save_data(data)
    return redirect(url_for("people"))


@app.route("/people/<person_id>")
def person_detail(person_id):
    data = load_data()
    person = next((p for p in data["people"] if p["id"] == person_id), None)
    if not person:
        return redirect(url_for("people"))
    all_meetings = [m for m in data["meetings"] if m["person_id"] == person_id]
    upcoming = sorted([m for m in all_meetings if not m.get("completed", False)], key=lambda m: m["date"])
    past     = sorted([m for m in all_meetings if m.get("completed", False)],     key=lambda m: m["date"], reverse=True)
    return render_template("person.html", person=person, upcoming=upcoming, past=past)


@app.route("/people/<person_id>/delete", methods=["POST"])
def delete_person(person_id):
    data = load_data()
    data["people"] = [p for p in data["people"] if p["id"] != person_id]
    save_data(data)
    return redirect(url_for("people"))


# ---------------------------------------------------------------------------
# Routes — meetings
# ---------------------------------------------------------------------------

@app.route("/meetings/new", methods=["GET", "POST"])
def new_meeting():
    data = load_data()
    if request.method == "POST":
        meeting = _meeting_from_form(request.form)
        data["meetings"].append(meeting)
        save_data(data)
        return redirect(url_for("view_meeting", meeting_id=meeting["id"]))
    person_id = request.args.get("person_id", "")
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("meeting_form.html", people=data["people"], person_id=person_id, meeting=None, today=today)


@app.route("/meetings/<meeting_id>")
def view_meeting(meeting_id):
    data = load_data()
    meeting = next((m for m in data["meetings"] if m["id"] == meeting_id), None)
    if not meeting:
        return redirect(url_for("index"))
    person = next((p for p in data["people"] if p["id"] == meeting["person_id"]), None)
    return render_template("meeting.html", meeting=meeting, person=person)


@app.route("/meetings/<meeting_id>/edit", methods=["GET", "POST"])
def edit_meeting(meeting_id):
    data = load_data()
    meeting = next((m for m in data["meetings"] if m["id"] == meeting_id), None)
    if not meeting:
        return redirect(url_for("index"))
    if request.method == "POST":
        updated = _meeting_from_form(request.form, existing_id=meeting_id, created_at=meeting["created_at"])
        updated["completed"] = meeting.get("completed", False)
        data["meetings"] = [updated if m["id"] == meeting_id else m for m in data["meetings"]]
        save_data(data)
        return redirect(url_for("view_meeting", meeting_id=meeting_id))
    return render_template("meeting_form.html", people=data["people"], person_id=meeting["person_id"], meeting=meeting, today=meeting["date"])


@app.route("/meetings/<meeting_id>/delete", methods=["POST"])
def delete_meeting(meeting_id):
    data = load_data()
    person_id = next((m["person_id"] for m in data["meetings"] if m["id"] == meeting_id), None)
    data["meetings"] = [m for m in data["meetings"] if m["id"] != meeting_id]
    save_data(data)
    if person_id:
        return redirect(url_for("person_detail", person_id=person_id))
    return redirect(url_for("index"))


@app.route("/meetings/<meeting_id>/toggle-complete", methods=["POST"])
def toggle_complete(meeting_id):
    data = load_data()
    for m in data["meetings"]:
        if m["id"] == meeting_id:
            m["completed"] = not m.get("completed", False)
            break
    save_data(data)
    return redirect(request.referrer or url_for("view_meeting", meeting_id=meeting_id))


@app.route("/meetings/<meeting_id>/actions/<action_id>/toggle", methods=["POST"])
def toggle_action(meeting_id, action_id):
    data = load_data()
    for m in data["meetings"]:
        if m["id"] == meeting_id:
            for a in m.get("action_items", []):
                if a["id"] == action_id:
                    a["completed"] = not a["completed"]
                    break
    save_data(data)
    return redirect(request.referrer or url_for("view_meeting", meeting_id=meeting_id))


def _meeting_from_form(form, existing_id=None, created_at=None) -> dict:
    action_descs     = form.getlist("action_desc[]")
    action_owners    = form.getlist("action_owner[]")
    action_dues      = form.getlist("action_due[]")
    action_ids       = form.getlist("action_id[]")
    action_completeds = set(form.getlist("action_completed[]"))

    action_items = []
    for i, (desc, owner, due) in enumerate(zip(action_descs, action_owners, action_dues)):
        if not desc.strip():
            continue
        action_id = action_ids[i] if i < len(action_ids) and action_ids[i] else new_id()
        action_items.append({
            "id": action_id,
            "description": desc.strip(),
            "owner": owner.strip(),
            "due_date": due,
            "completed": action_id in action_completeds,
        })

    return {
        "id": existing_id or new_id(),
        "person_id": form["person_id"],
        "date": form["date"],
        "agenda": form.get("agenda", ""),
        "notes": form.get("notes", ""),
        "action_items": action_items,
        "sentiment": int(form.get("sentiment", 3)),
        "created_at": created_at or now(),
        "updated_at": now(),
    }


# ---------------------------------------------------------------------------
# Routes — search
# ---------------------------------------------------------------------------

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    data = load_data()
    people_map = {p["id"]: p for p in data["people"]}
    results = []
    if q:
        ql = q.lower()
        for m in data["meetings"]:
            person = people_map.get(m["person_id"], {})
            haystack = " ".join([
                m.get("date", ""),
                m.get("agenda", ""),
                m.get("notes", ""),
                person.get("name", ""),
                person.get("title", ""),
                person.get("team", ""),
                *[a.get("description", "") for a in m.get("action_items", [])],
                *[a.get("owner", "")        for a in m.get("action_items", [])],
            ]).lower()
            if ql in haystack:
                results.append(m)
        results.sort(key=lambda m: m["date"], reverse=True)
    return render_template("search.html", query=q, results=results, people_map=people_map)


# ---------------------------------------------------------------------------
# Routes — backup
# ---------------------------------------------------------------------------

@app.route("/backup")
def backup():
    if not load_settings().get("encryption_enabled"):
        if not os.path.exists(DATA_FILE):
            return redirect(url_for("index"))
        filename = f"meetings-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        return send_file(DATA_FILE, as_attachment=True, download_name=filename)
    return render_template("backup_options.html")


@app.route("/backup/plaintext")
def backup_plaintext():
    buf = io.BytesIO(json.dumps(load_data(), indent=2).encode())
    filename = f"meetings-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/json")


@app.route("/backup/encrypted")
def backup_encrypted():
    raw = encrypt_bytes(json.dumps(load_data()).encode(), _password)
    buf = io.BytesIO(raw)
    filename = f"meetings-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.enc"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/octet-stream")


# ---------------------------------------------------------------------------
# Routes — settings
# ---------------------------------------------------------------------------

@app.route("/settings")
def settings_page():
    msg = request.args.get("msg", "")
    return render_template("settings.html", settings=load_settings(), msg=msg)


@app.route("/settings/enable-encryption", methods=["POST"])
def enable_encryption():
    global _password
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if not password:
        return render_template("settings.html", settings=load_settings(), error="Password cannot be empty.")
    if password != confirm:
        return render_template("settings.html", settings=load_settings(), error="Passwords do not match.")

    data = load_data()

    new_settings = {"encryption_enabled": True, **_make_verifier(password)}
    save_settings(new_settings)
    _password = password

    with open(ENC_FILE, "wb") as f:
        f.write(encrypt_bytes(json.dumps(data).encode(), _password))

    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)

    return redirect(url_for("settings_page", msg="encryption_enabled"))


@app.route("/settings/disable-encryption", methods=["POST"])
def disable_encryption():
    global _password
    settings = load_settings()
    password = request.form.get("password", "")

    if not verify_password(password, settings):
        return render_template("settings.html", settings=settings, error="Incorrect password.")

    data = load_data()
    _password = None
    save_settings({"encryption_enabled": False})

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    if os.path.exists(ENC_FILE):
        os.remove(ENC_FILE)

    return redirect(url_for("settings_page", msg="encryption_disabled"))


# ---------------------------------------------------------------------------
# Entry point — prompts for password at CLI if encryption is enabled
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    settings = load_settings()
    if settings.get("encryption_enabled"):
        for attempt in range(3):
            pwd = getpass.getpass("Enter encryption password: ")
            if verify_password(pwd, settings):
                _password = pwd
                print("Password accepted.")
                break
            remaining = 2 - attempt
            print(f"Incorrect password.{f'  {remaining} attempt(s) remaining.' if remaining else ''}")
        else:
            print("Too many failed attempts. Exiting.")
            sys.exit(1)
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="127.0.0.1", port=5001, use_reloader=False)
