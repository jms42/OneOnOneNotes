import json
import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "meetings.json")


def load_data():
    if not os.path.exists(DATA_FILE):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        return {"people": [], "meetings": []}
    with open(DATA_FILE) as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def new_id():
    return str(uuid.uuid4())


def now():
    return datetime.now().isoformat()


@app.route("/")
def index():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    upcoming = sorted(
        [m for m in data["meetings"] if m["date"] >= today],
        key=lambda m: m["date"],
    )
    past = sorted(
        [m for m in data["meetings"] if m["date"] < today],
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
    today = datetime.now().strftime("%Y-%m-%d")
    all_meetings = [m for m in data["meetings"] if m["person_id"] == person_id]
    upcoming = sorted([m for m in all_meetings if m["date"] >= today], key=lambda m: m["date"])
    past = sorted([m for m in all_meetings if m["date"] < today], key=lambda m: m["date"], reverse=True)
    return render_template("person.html", person=person, upcoming=upcoming, past=past)


@app.route("/people/<person_id>/delete", methods=["POST"])
def delete_person(person_id):
    data = load_data()
    data["people"] = [p for p in data["people"] if p["id"] != person_id]
    save_data(data)
    return redirect(url_for("people"))


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
    return render_template(
        "meeting_form.html",
        people=data["people"],
        person_id=person_id,
        meeting=None,
        today=today,
    )


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
        data["meetings"] = [updated if m["id"] == meeting_id else m for m in data["meetings"]]
        save_data(data)
        return redirect(url_for("view_meeting", meeting_id=meeting_id))
    return render_template(
        "meeting_form.html",
        people=data["people"],
        person_id=meeting["person_id"],
        meeting=meeting,
        today=meeting["date"],
    )


@app.route("/meetings/<meeting_id>/delete", methods=["POST"])
def delete_meeting(meeting_id):
    data = load_data()
    person_id = next((m["person_id"] for m in data["meetings"] if m["id"] == meeting_id), None)
    data["meetings"] = [m for m in data["meetings"] if m["id"] != meeting_id]
    save_data(data)
    if person_id:
        return redirect(url_for("person_detail", person_id=person_id))
    return redirect(url_for("index"))


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


def _meeting_from_form(form, existing_id=None, created_at=None):
    action_descs = form.getlist("action_desc[]")
    action_owners = form.getlist("action_owner[]")
    action_dues = form.getlist("action_due[]")
    action_ids = form.getlist("action_id[]")
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
                *[a.get("owner", "") for a in m.get("action_items", [])],
            ]).lower()
            if ql in haystack:
                results.append(m)
        results.sort(key=lambda m: m["date"], reverse=True)
    return render_template("search.html", query=q, results=results, people_map=people_map)


@app.route("/backup")
def backup():
    filename = f"meetings-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return send_file(DATA_FILE, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
