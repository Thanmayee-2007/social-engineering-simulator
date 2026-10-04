from flask import Flask, Response, jsonify, render_template_string, render_template, request, url_for, redirect
import random
import csv
import io
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse 

app = Flask(__name__)
DATABASE_FILE = Path(__file__).with_name("training_events.db")

SCENARIOS = {
    "banking": ("Banking alert", "bank", "Use your trusted bank bookmark or official app instead of an email link."),
    "social": ("Social account alert", "social", "Verify unexpected account warnings through the official app or site."),
    "corporate": ("Corporate email alert", "mail", "Confirm unusual requests through a trusted internal channel."),
    "cloud": ("Cloud service alert", "mail", "Inspect the destination domain before following unexpected links."),
    "photos": ("Photo-sharing alert", "photos", "Open unexpected photo-sharing notifications from a trusted bookmark instead of the message link."),
    "streaming": ("Streaming account alert", "streaming", "Treat payment or membership warnings as suspicious until verified in the official app."),
    "payments": ("Payment service alert", "payments", "Confirm payment requests using a known, trusted service address."),
    "community": ("Community forum alert", "community", "Verify account warnings through the official community site, not a message link."),
}
TRAINING_MODULES = {
    "phishing": ("🎣", "Phishing Emails", "Fraudulent emails try to rush you into revealing information or money.", ["Unexpected urgency", "Mismatched sender or destination", "Requests for passwords or payment"], "Pause, verify the sender through a known channel, and report the message."),
    "spam": ("📨", "Spam Mails", "Unsolicited bulk messages can carry scams, unwanted ads, or malicious links.", ["Unfamiliar sender", "Too-good-to-be-true offer", "Unexpected attachments"], "Use the spam controls and do not open suspicious attachments."),
    "hijacking": ("🕵️", "Account Hijacking", "An attacker may try to take over an account and lock you out.", ["Unexpected password-reset notices", "New-device alerts you did not trigger", "Changed recovery details"], "Use unique passwords, MFA, and contact support through the official site."),
    "spoofing": ("🎭", "Email Spoofing", "A forged From address may be designed to look like someone you trust.", ["Display name differs from email address", "Reply-to mismatch", "Unusual tone or request"], "Inspect the complete sender address and verify unusual requests separately."),
    "stalking": ("🔒", "Online Stalking", "Oversharing can expose personal routines and make targeted scams more convincing.", ["Requests for private details", "Repeated unwanted contact", "Impersonated social accounts"], "Review privacy settings, limit public details, and preserve evidence before reporting."),
}
INBOX_MAILS = [
    ("Bank Alert", "Account temporarily suspended", "We detected unusual activity...", "9:03 AM", True),
    ("FedEx Delivery", "Your package could not be delivered", "We attempted delivery today...", "8:55 AM", True),
    ("IT Helpdesk", "Password expires in 24 hours", "Your corporate password will expire...", "Yesterday", True),
    ("HR Payroll", "Updated direct deposit form required", "Please review and confirm...", "Yesterday", True),
    ("Amazon Rewards", "You've won a $500 gift card", "Congratulations! You've been selected...", "2 days ago", False),
    ("Voicemail System", "New voicemail received (0:42)", "You have one new voicemail...", "2 days ago", True),
    ("Cloud Storage", "Shared file requires immediate review", "A colleague shared a confidential document...", "3 days ago", True),
    ("Benefits Team", "Open enrollment confirmation needed", "Review your benefits choices before the deadline...", "3 days ago", True),
    ("Security Operations", "MFA enrollment reminder", "Confirm your multi-factor setup through the portal...", "4 days ago", False),
    ("Conference Team", "Your event registration receipt", "Your attendance confirmation is ready...", "5 days ago", False),
]
INBOX_MAILS = [
    ("Bank Alert", "Account temporarily suspended", "We detected unusual activity...", "9:03 AM", True),
    # ... your existing 10 rows stay exactly as-is ...
]

MAIL_TEMPLATES = {
    "banking": {
        "senders": ["Bank Alert", "Account Security", "Northstar Banking"],
        "subjects": ["Account temporarily suspended", "Unusual sign-in attempt detected", "Your card has been locked"],
        "previews": ["We detected unusual activity on your account...", "A new device tried to access your account...", "Your card was declined due to suspicious activity..."],
        "is_phishing": True,
    },
    "delivery": {
        "senders": ["FedEx Delivery", "UPS Notification", "DHL Express"],
        "subjects": ["Your package could not be delivered", "Delivery attempt failed - action required", "Customs fee required for your shipment"],
        "previews": ["We attempted delivery today but require updated address...", "Your parcel is on hold pending confirmation...", "A small fee is required to release your package..."],
        "is_phishing": True,
    },
    "it": {
        "senders": ["IT Helpdesk", "System Admin", "Security Operations"],
        "subjects": ["Password expires in 24 hours", "Mailbox storage almost full", "Suspicious login blocked"],
        "previews": ["Your corporate password will expire today...", "Your mailbox is at 98% capacity, action needed...", "We blocked a login attempt from an unrecognized device..."],
        "is_phishing": True,
    },
    "rewards": {
        "senders": ["Amazon Rewards", "Prize Center", "Loyalty Program"],
        "subjects": ["You've won a $500 gift card", "Claim your exclusive reward", "Survey reward pending"],
        "previews": ["Congratulations! You've been randomly selected...", "Complete this short survey to claim your prize...", "Your reward points are about to expire..."],
        "is_phishing": True,
    },
    "legit": {
        "senders": ["Conference Team", "Benefits Team", "Security Operations"],
        "subjects": ["Your event registration receipt", "Open enrollment confirmation needed", "MFA enrollment reminder"],
        "previews": ["Your attendance confirmation is ready...", "Review your benefits choices before the deadline...", "Confirm your multi-factor setup through the official portal..."],
        "is_phishing": False,
    },
}
TIME_LABELS = ["9:03 AM", "8:55 AM", "Yesterday", "2 days ago", "3 days ago", "4 days ago", "5 days ago"]

def generate_fake_mails(count=10, phishing_ratio=0.7, seed=None):
    """Randomized training inbox mails: (sender, subject, preview, time, is_phishing)."""
    rng = random.Random(seed)
    phishing_cats = [k for k, v in MAIL_TEMPLATES.items() if v["is_phishing"]]
    legit_cats = [k for k, v in MAIL_TEMPLATES.items() if not v["is_phishing"]]
    mails = []
    for _ in range(count):
        is_phish = rng.random() < phishing_ratio
        cat = rng.choice(phishing_cats if is_phish else legit_cats)
        t = MAIL_TEMPLATES[cat]
        mails.append((rng.choice(t["senders"]), rng.choice(t["subjects"]), rng.choice(t["previews"]), rng.choice(TIME_LABELS), t["is_phishing"]))
    return mails

DEMO_RECIPIENTS = ("sagalaraji123@gmail.com", "contact2ms.raji@gmail.com")
SAMPLE_STATS = {"sent": 100, "clicked": 45, "submitted": 12, "success_rate": 12}
RECIPIENTS = [
    "contact2ms.raji@gmail.com",
    "sagalaraji123@gmail.com",
    "alex.training@example.invalid",
    "casey.training@example.invalid",
    "riley.training@example.invalid",
]


BASE_STYLE = """
*{.home-background{
    min-height:100vh;
    background:
        radial-gradient(circle at 15% 25%, rgba(0,217,255,.18), transparent 30%),
        radial-gradient(circle at 85% 75%, rgba(100,50,255,.20), transparent 30%),
        linear-gradient(135deg,#020617,#07152d,#030712);
}
box-sizing:border-box}body{margin:0;background:#081225;color:#ecf3ff;font:15px/1.5 system-ui,Segoe UI,sans-serif}.shell{max-width:1180px;margin:auto;padding:34px 24px 58px}.nav{display:flex;justify-content:space-between;gap:16px;align-items:center;border-bottom:1px solid #263956;padding-bottom:22px}.brand{font-weight:800;letter-spacing:.6px}.brand b{color:#36ddb6}.nav a,.button{color:#e9f2ff;text-decoration:none;border:1px solid #36506f;border-radius:8px;padding:9px 13px;background:#10203a;font:inherit;cursor:pointer}.button.primary{background:#26bd9d;color:#041d1b;border-color:#26bd9d}.hero{margin:32px 0 22px}.hero h1{font-size:clamp(32px,6vw,56px);line-height:1.05;margin:10px 0}.muted{color:#a9bddb}.notice{border:1px solid #5a4b1e;background:#282312;color:#f2d67b;padding:11px 13px;border-radius:8px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card,.panel{background:#0e1c33;border:1px solid #233754;border-radius:12px;padding:18px}.metric small{color:#a8bbd6;text-transform:uppercase;letter-spacing:.8px}.metric strong{display:block;font-size:34px;margin-top:5px;color:#3cddb9}.metric:nth-child(2) strong{color:#74abff}.metric:nth-child(3) strong{color:#f2bb65}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.panel h2{margin:0 0 7px}.panel p{color:#aabbd5}.funnel div{background:#123a42;color:#bff9eb;border-radius:6px;padding:10px;margin:10px auto;text-align:center}.funnel div:nth-child(2){width:75%;background:#203d65}.funnel div:nth-child(3){width:48%;background:#533f1e}.funnel div:nth-child(4){width:28%;background:#5a2635}.form-row{display:flex;gap:10px}.form-row input{flex:1}.input,select,input{width:100%;background:#071124;color:#eff5ff;border:1px solid #395273;border-radius:7px;padding:10px;font:inherit}.finding{margin-top:9px;padding:10px;border-left:4px solid #5c9ced;background:#102540;border-radius:5px}.finding.high{border-color:#ed667a;background:#3b1925}.finding.medium{border-color:#e8b750;background:#3d3017}.finding.low{border-color:#49cd9f;background:#11352b}.login-card{width:min(440px,92vw);margin:9vh auto;background:#fff;color:#182237;padding:32px;border-radius:14px}.login-card .training{margin:-32px -32px 25px;background:#083d42;color:#c9fff3;padding:10px;text-align:center;font-size:11px;font-weight:800}.login-card input{color:#162235;background:#fff;border-color:#cbd6e3;margin:6px 0 12px}.login-card button{width:100%}.bank{border-top:5px solid #075a70}.mail{border-top:5px solid #2769bd}.social{border-top:5px solid #4666a7}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:10px;text-align:left;border-bottom:1px solid #243957}th{color:#9eb3d2}@media(max-width:700px){.metrics,.grid{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}.form-row{display:block}.form-row .button{margin-top:9px;width:100%}}@media(max-width:420px){.metrics{grid-template-columns:1fr}}
 .service-name{font-weight:800;font-size:24px;letter-spacing:-.7px;margin-bottom:10px}.photos{border-top:5px solid #b83ca5}.photos .service-name{color:#a62791}.streaming{border-top:5px solid #c93446}.streaming .service-name{color:#b02030}.payments{border-top:5px solid #08778a}.payments .service-name{color:#046476}.community{border-top:5px solid #e87927}.community .service-name{color:#bf5915}.module-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}.module-card{position:relative;display:block;min-height:210px;padding:28px 30px;border:1px solid #263956;border-radius:18px;background:#09142a;color:#edf4ff;text-decoration:none}.module-card:hover{border-color:#37ddb7;background:#0d1c37}.module-card h2{margin:19px 0 8px;font-size:23px}.module-card p{margin:0;color:#9eb7dc;font-size:17px}.module-icon{display:block;font-size:36px}.module-arrow{position:absolute;right:30px;top:28px;font-size:28px;color:#7c9bc4}.lesson-panel{max-width:780px;margin:38px auto}.lesson-panel h1{font-size:42px;margin:12px 0}.lesson-panel li{margin:9px 0;color:#c1d0e8}.inbox-panel{background:#0b1730;border:1px solid #263956;border-radius:14px;overflow:hidden}.inbox-toolbar{display:flex;justify-content:space-between;gap:10px;padding:15px 18px;color:#adc0db;border-bottom:1px solid #263956}.mail-row{border-bottom:1px solid #20334f}.mail-row:last-child{border:0}.mail-row summary{display:flex;align-items:center;gap:13px;padding:14px 18px;cursor:pointer;list-style:none}.mail-row summary::-webkit-details-marker{display:none}.mail-row:hover summary{background:#10203c}.mail-avatar{width:35px;height:35px;display:grid;place-items:center;border-radius:50%;background:#254a70;color:#d6ecff;font-weight:800}.mail-copy{display:grid;gap:1px;flex:1;min-width:0}.mail-copy strong{font-weight:600}.mail-copy small,.mail-time{color:#a0b5d4}.mail-time{white-space:nowrap}.phish-badge,.review-badge{font-size:11px;border-radius:99px;padding:3px 7px;background:#522535;color:#ffc4cd}.review-badge{background:#3f3516;color:#f7df94}.mail-detail{padding:2px 66px 18px;color:#bacbe2}.mail-detail .button{margin:13px 4px 4px 0}.action-feedback{display:block;color:#58d5b1;margin-top:5px}@media(max-width:700px){.module-grid{grid-template-columns:1fr}.module-card{min-height:175px}.inbox-toolbar{display:block}.mail-row summary{align-items:flex-start}.mail-time{display:none}.mail-detail{padding-left:18px}.mail-copy small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
 .service-name{font-weight:800;font-size:24px;letter-spacing:-.7px;margin-bottom:10px}.photos{border-top:5px solid #b83ca5}.photos .service-name{color:#a62791}.streaming{border-top:5px solid #c93446}.streaming .service-name{color:#b02030}.payments{border-top:5px solid #08778a}.payments .service-name{color:#046476}.community{border-top:5px solid #e87927}.community .service-name{color:#bf5915}.module-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}.module-card{position:relative;display:block;min-height:210px;padding:28px 30px;border:1px solid #263956;border-radius:18px;background:#09142a;color:#edf4ff;text-decoration:none}.module-card:hover{border-color:#37ddb7;background:#0d1c37}.module-card h2{margin:19px 0 8px;font-size:23px}.module-card p{margin:0;color:#9eb7dc;font-size:17px}.module-icon{display:block;font-size:36px}.module-arrow{position:absolute;right:30px;top:28px;font-size:28px;color:#7c9bc4}.lesson-panel{max-width:780px;margin:38px auto}.lesson-panel h1{font-size:42px;margin:12px 0}.lesson-panel li{margin:9px 0;color:#c1d0e8}.mailspace{display:grid;grid-template-columns:180px 1fr;gap:16px}.inbox-sidebar{display:grid;align-content:start;gap:12px;color:#aec0d8}.inbox-sidebar span{padding:7px 10px}.inbox-sidebar small{margin-top:12px}.compose-button{text-align:center}.inbox-panel{background:#0b1730;border:1px solid #263956;border-radius:14px;overflow:hidden}.inbox-toolbar{display:flex;justify-content:space-between;gap:10px;padding:15px 18px;color:#adc0db;border-bottom:1px solid #263956}.mail-row{border-bottom:1px solid #20334f}.mail-row:last-child{border:0}.mail-row summary{display:flex;align-items:center;gap:13px;padding:14px 18px;cursor:pointer;list-style:none}.mail-row summary::-webkit-details-marker{display:none}.mail-row:hover summary{background:#10203c}.mail-avatar{width:35px;height:35px;display:grid;place-items:center;border-radius:50%;background:#254a70;color:#d6ecff;font-weight:800}.mail-copy{display:grid;gap:1px;flex:1;min-width:0}.mail-copy strong{font-weight:600}.mail-copy small,.mail-time{color:#a0b5d4}.mail-time{white-space:nowrap}.phish-badge,.review-badge{font-size:11px;border-radius:99px;padding:3px 7px;background:#522535;color:#ffc4cd}.review-badge{background:#3f3516;color:#f7df94}.mail-detail{padding:2px 66px 18px;color:#bacbe2}.mail-detail .button{margin:13px 4px 4px 0}.action-feedback{display:block;color:#58d5b1;margin-top:5px}.compose-box{max-width:600px;margin:18px 0 0 196px;background:#0e1c33;border:1px solid #2a4162;border-radius:12px;padding:20px}.compose-box label{display:block;margin:12px 0 4px;color:#b5c7e2}@media(max-width:700px){.module-grid{grid-template-columns:1fr}.module-card{min-height:175px}.mailspace{grid-template-columns:1fr}.inbox-sidebar{grid-template-columns:1fr 1fr}.inbox-toolbar{display:block}.mail-row summary{align-items:flex-start}.mail-time{display:none}.mail-detail{padding-left:18px}.mail-copy small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.compose-box{margin-left:0}}
 .start-btn{display:inline-block;margin-top:16px;font-size:16px;padding:12px 20px}
 .start-btn{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    gap:10px;
    width:max-content;
    margin-top:20px;
    padding:14px 24px;
    font-size:16px;
    font-weight:800;
    letter-spacing:.3px;
    border-radius:10px;
    background:linear-gradient(135deg,#00d9ff,#087ff5);
    color:#00101d;
    border:1px solid #00d9ff;
    box-shadow:0 0 20px rgba(0,217,255,.25);
    transition:all .25s ease;
}

.start-btn:hover{
    transform:translateY(-3px);
    box-shadow:
        0 0 20px rgba(0,217,255,.45),
        0 8px 30px rgba(0,130,255,.2);
}

.start-btn:active{
    transform:translateY(0);
}
.compose-modal{
    display:none;
    position:fixed;
    inset:0;
    background:rgba(0,0,0,.75);
    z-index:1000;
    align-items:center;
    justify-content:center;
    padding:20px;
}

.compose-modal.open{
    display:flex;
}

.compose-sheet{
    width:min(550px,95vw);
    background:#0e1c33;
    border:1px solid #2d4668;
    border-radius:16px;
    padding:24px;
    box-shadow:0 20px 60px rgba(0,0,0,.5);
}

.compose-sheet h2{
    margin:0;
}

.compose-sheet label{
    display:block;
    margin-top:16px;
    margin-bottom:6px;
    color:#b8c9e2;
}

.compose-actions{
    display:flex;
    gap:10px;
    margin-top:20px;
}

.compose-fab{
    color:#e9f2ff;
    background:#10203a;
    border:1px solid #36506f;
    border-radius:8px;
    padding:9px 13px;
    cursor:pointer;
}

.compose-close{
    margin-left:auto;
    background:transparent;
    border:0;
    color:#fff;
    font-size:20px;
    cursor:pointer;
}
"""

def connection():
    db = sqlite3.connect(DATABASE_FILE)
    db.row_factory = sqlite3.Row
    return db

def initialize_database():
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS training_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, participant TEXT NOT NULL,
            event_type TEXT NOT NULL, scenario TEXT NOT NULL, created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL)""")
        for email in RECIPIENTS:
            db.execute("INSERT OR IGNORE INTO recipients(email) VALUES(?)", (email,))

def get_recipients():
    with connection() as db:
        return [r["email"] for r in db.execute("SELECT email FROM recipients ORDER BY id").fetchall()]

def add_recipient(email):
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO recipients(email) VALUES(?)", (email.strip(),))

def record_event(participant, event_type, scenario):
    ...  # your existing function stays where it is, unchanged

def record_event(participant, event_type, scenario):
    with connection() as db:
        db.execute("INSERT INTO training_events(participant,event_type,scenario,created_at) VALUES(?,?,?,?)",
                   ((participant or "anonymous-training-user").strip()[:80], event_type, scenario,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")))

def stats():
    with connection() as db:
        rows = db.execute("SELECT event_type,COUNT(*) count FROM training_events GROUP BY event_type").fetchall()
    counts = {row["event_type"]: row["count"] for row in rows}
    sent = counts.get("Training email assigned (simulation)", 0)
    clicked = counts.get("Training link opened", 0)
    submitted = counts.get("Simulated submission redirected", 0)
    return {"sent": sent, "clicked": clicked, "submitted": submitted,
            "success_rate": round(submitted / sent * 100, 1) if sent else 0}

def inspect(value):
    text = (value or "").strip().lower()
    candidate = re.search(r"https?://[^\s<>'\"]+|\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>'\"]*)?", text)
    host = urlparse((candidate.group(0) if candidate else text) if "://" in (candidate.group(0) if candidate else text) else "https://" + (candidate.group(0) if candidate else text)).hostname or ""
    findings = []
    if host in {"bit.ly", "tinyurl.com", "t.co", "is.gd", "ow.ly"}: findings.append(("medium", "Shortened URL", "The visible link may conceal its final destination."))
    if host.endswith((".top", ".xyz", ".zip", ".click")): findings.append(("medium", "Unusual domain ending", "Confirm the organization through a trusted bookmark or official app."))
    if any(x in host for x in ("paypa1", "micr0soft", "g00gle", "faceb00k", "arnazon")): findings.append(("high", "Possible lookalike domain", "The domain resembles a familiar brand but has a misleading spelling."))
    if any(x in text for x in ("login", "sign in", "password", "credential", "verify account")): findings.append(("high", "Potential fake login form", "Unexpected password prompts should be verified in a separately opened trusted service."))
    return findings or [("low", "No common pattern matched", "Continue checking sender context, domain spelling, and unexpected urgency.")]
@app.get("/project-info")
def project_info():
    return render_template("project_info.html")


@app.get("/")
def home():
    key = request.args.get("scenario", "banking")
    title, style, lesson = SCENARIOS.get(key, SCENARIOS["banking"])
    record_event(request.args.get("participant"), "Training link opened", title)
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class="shell home-background"><nav class=nav><div class=brand>SECURITY <b>AWARENESS</b></div><span><a href="{{ url_for("home") }}">Home</a><a href="{{ url_for("project_info") }}">Project Info</a><a href='{{ url_for("trainings") }}'>Trainings</a> <a href='{{ url_for("inbox") }}'>Inbox</a> <a href='{{ url_for("dashboard") }}'>Dashboard</a></span></nav><section class=hero><div class=notice>AUTHORIZED LOCAL EDUCATION SIMULATION · NO REAL EMAILS</div><h1>Social Engineering Simulator</h1><a class="button primary start-btn"
   href="{{ url_for('trainings') }}">
    Start Simulation →
</a><p class=muted>{{ lesson }}</p></section><section class=grid><article class=panel><h2>{{ title }}</h2><p>Use a generic, realistic training page design to practice spotting suspicious requests.</p><a class='button primary' href='{{ url_for("training_page",scenario=key) }}'>Open training example</a></article><article class=panel><h2>Anti-phishing detection</h2><p>Check a sample URL or page description before opening it.</p><form action='{{ url_for("detect") }}' method=get><input name=value placeholder='https://bit.ly/account-verify'><button class='button primary'>Analyze safely</button></form></article></section><p class=muted>Choose lesson: {% for k,v in scenarios.items() %}<a href='{{ url_for("home",scenario=k) }}'>{{ v[0] }}</a>{% if not loop.last %} · {% endif %}{% endfor %}</p></main>""", css=BASE_STYLE, key=key, lesson=lesson, scenarios=SCENARIOS)
   
@app.get("/inbox")
def inbox():
    seed = request.args.get("seed", type=int)
    mails = generate_fake_mails(count=10, seed=seed)
    return render_template_string("""
    <!doctype html>
    <style>{{ css }}</style>
    <main class="shell"><nav class=nav>
    <div class="brand">Spamming <b>Mails</b> Simulator</div><span><a href='{{ url_for("trainings") }}'>Trainings</a> <a href='{{ url_for("home") }}'>Home</a></span>
    </nav><section class=hero><h1>Spam-mail training inbox</h1><p class=muted>Sample messages only. Opening a row shows safety guidance; this simulator never opens external links.</p></section>

    <section class='inbox-panel'>
      <div class=inbox-toolbar>
        <b>Inbox · {{ mails|length }} training messages</b>
        <span>Practice: identify, report, delete</span>
        <button class=compose-fab type=button onclick="document.getElementById('compose-modal').classList.add('open')">✎ Compose</button>
      </div>
      {% for sender,subject,preview,time,is_phishing in mails %}<details class='mail-row {% if is_phishing %}suspicious{% endif %}'><summary><span class=mail-avatar>{{ sender[0] }}</span><span class=mail-copy><b>{{ sender }}</b><strong>{{ subject }}</strong><small>{{ preview }}</small></span><span class=mail-time>{{ time }}</span>{% if is_phishing %}<span class=phish-badge>Suspicious</span>{% else %}<span class=review-badge>Review</span>{% endif %}</summary><div class=mail-detail>{% if is_phishing %}<b>Training indicator:</b> This message uses urgency, account pressure, delivery/payment language, or an unexpected request. Do not click links or attachments. {% else %}<b>Training reminder:</b> "Too-good-to-be-true" offers still need independent verification. {% endif %}<div><button class='button primary' type=button onclick="this.closest('details').querySelector('.action-feedback').textContent='Reported to the simulated security team.'">Report safely</button> <button class=button type=button onclick="this.closest('details').querySelector('.action-feedback').textContent='Deleted from the simulated inbox.'">Delete</button></div><small class=action-feedback aria-live=polite></small></div></details>{% endfor %}
    </section>

    <div class=compose-modal id=compose-modal>
      <div class=compose-sheet>
        <div style="display:flex;align-items:center">
          <h2>New training simulation</h2>
          <button class=compose-close type=button onclick="document.getElementById('compose-modal').classList.remove('open')">✕</button>
        </div>
        <p class=muted style="margin:4px 0 0">This records an authorized local assignment only. It cannot send email or contact real recipients.</p>
        <form method=post action='{{ url_for("compose_simulation") }}'>
          <label>Pre-approved demo recipient</label>
          <select name=recipient required>
            {% for r in recipients %}<option value='{{ r }}'>{{ r }}</option>{% endfor %}
          </select>
          <label>Training scenario</label>
          <select name=scenario required>
            {% for key,item in scenarios.items() %}<option value='{{ item[0] }}'>{{ item[0] }}</option>{% endfor %}
          </select>
          <div class=compose-actions>
            <button class='button primary' type=submit>Record simulated assignment</button>
            <button class=button type=button onclick="document.getElementById('compose-modal').classList.remove('open')">Cancel</button>
          </div>
        </form>
      </div>
    </div>
    </main>
   """, css=BASE_STYLE, mails=mails, recipients=get_recipients(), scenarios=SCENARIOS)

@app.post("/inbox/compose-simulation")
def compose_simulation():
    recipient = request.form.get("recipient", "").strip()
    scenario = request.form.get("scenario").strip()
    if recipient not in RECIPIENTS:
        return "Recipient must be selected from the approved list.", 400
    scenario = request.form.get("scenario", "General")
    record_event(recipient, "Training email assigned (simulation)", scenario)
    return render_template_string("""
    <!doctype html>
    <style>{{ css }}</style>
    <main class='login-card'>
    <div class=training>SIMULATION RECORDED</div>
    <h1>Training assignment recorded.</h1>
    <p>No email was sent or delivered. This assignment was only logged for your local dashboard.</p>
    <a class='button primary' href='{{ url_for("inbox") }}'>Return to inbox</a>
    </main>""", css=BASE_STYLE,recipient =recipient)

@app.post("/inbox/add-recipient")
def add_recipient_route():
    email = request.form.get("email", "").strip()
    if email:
        add_recipient(email)
    return redirect(url_for("inbox"))

@app.get("/trainings")
def trainings():
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class=shell><nav class=nav><div class=brand>SECURITY <b>AWARENESS</b> LAB</div><span><a href='{{ url_for("dashboard") }}'>Dashboard</a> <a href='{{ url_for("home") }}'>Home</a></span></nav><section class=hero><h1>Security Awareness Trainings</h1><p class=muted>Short modules covering common social-engineering threats.</p></section><section class='module-grid'>{% for key,module in modules.items() %}<a class=module-card href='{{ url_for("training_module",key=key) }}'><span class=module-icon>{{ module[0] }}</span><span class=module-arrow>→</span><h2>{{ module[1] }}</h2><p>{{ module[2] }}</p></a>{% endfor %}</section></main>""", css=BASE_STYLE, modules=TRAINING_MODULES)
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class=shell><nav class=nav><div class=brand>SECURITY <b>AWARENESS</b> LAB</div><span><a href='{{ url_for("trainings") }}'>Trainings</a> <a href='{{ url_for("home") }}'>Home</a></span></nav><section class=hero><h1>Spam-mail training inbox</h1><p class=muted>Sample messages only. Opening a row shows safety guidance; this simulator never opens external links.</p></section><section class='inbox-panel'><div class=inbox-toolbar><b>Inbox · {{ mails|length }} training messages</b><span>Practice: identify, report, delete</span></div>{% for sender,subject,preview,time,is_phishing in mails %}<details class='mail-row {% if is_phishing %}suspicious{% endif %}'><summary><span class=mail-avatar>{{ sender[0] }}</span><span class=mail-copy><b>{{ sender }}</b><strong>{{ subject }}</strong><small>{{ preview }}</small></span><span class=mail-time>{{ time }}</span>{% if is_phishing %}<span class=phish-badge>Suspicious</span>{% else %}<span class=review-badge>Review</span>{% endif %}</summary><div class=mail-detail>{% if is_phishing %}<b>Training indicator:</b> This message uses urgency, account pressure, delivery/payment language, or an unexpected request. Do not click links or attachments. {% else %}<b>Training reminder:</b> “Too-good-to-be-true” offers still need independent verification. {% endif %}<div><button class='button primary' type=button onclick="this.closest('details').querySelector('.action-feedback').textContent='Reported to the simulated security team.'">Report safely</button> <button class=button type=button onclick="this.closest('details').querySelector('.action-feedback').textContent='Deleted from the simulated inbox.'">Delete</button></div><small class=action-feedback aria-live=polite></small></div></details>{% endfor %}</section></main>""", css=BASE_STYLE, mails=INBOX_MAILS)
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class=shell><nav class=nav><div class=brand>SECURITY <b>AWARENESS</b> LAB</div><span><a href='{{ url_for("trainings") }}'>Trainings</a> <a href='{{ url_for("home") }}'>Home</a></span></nav><section class=hero><h1>MailSpace training inbox</h1><p class=muted>Sample messages only. Opening a row shows safety guidance; this simulator never opens external links.</p></section><section class='mailspace'><aside class=inbox-sidebar><button class='button primary compose-button' type=button onclick="document.getElementById('compose-box').hidden=false">✎ Compose simulation</button><b>Inbox</b><span>Starred</span><span>Sent (simulated)</span><span>Reported</span><small>Local training mailbox</small></aside><section class='inbox-panel'><div class=inbox-toolbar><b>Inbox · {{ mails|length }} training messages</b><span>Practice: identify, report, delete</span></div>{% for sender,subject,preview,time,is_phishing in mails %}<details class='mail-row {% if is_phishing %}suspicious{% endif %}'><summary><span class=mail-avatar>{{ sender[0] }}</span><span class=mail-copy><b>{{ sender }}</b><strong>{{ subject }}</strong><small>{{ preview }}</small></span><span class=mail-time>{{ time }}</span>{% if is_phishing %}<span class=phish-badge>Suspicious</span>{% else %}<span class=review-badge>Review</span>{% endif %}</summary><div class=mail-detail>{% if is_phishing %}<b>Training indicator:</b> This message uses urgency, account pressure, delivery/payment language, or an unexpected request. Do not click links or attachments. {% else %}<b>Training reminder:</b> “Too-good-to-be-true” offers still need independent verification. {% endif %}<div><button class='button primary' type=button onclick="this.closest('details').querySelector('.action-feedback').textContent='Reported to the simulated security team.'">Report safely</button> <button class=button type=button onclick="this.closest('details').querySelector('.action-feedback').textContent='Deleted from the simulated inbox.'">Delete</button></div><small class=action-feedback aria-live=polite></small></div></details>{% endfor %}</section></section><section class=compose-box id=compose-box hidden><h2>Compose training simulation</h2><p class=muted>This records an authorized local assignment only. It cannot send email or contact recipients.</p><form method=post action='{{ url_for("compose_simulation") }}'><label>Pre-approved demo recipient</label><select name=recipient>{% for recipient in recipients %}<option>{{ recipient }}</option>{% endfor %}</select><label>Training scenario</label><select name=scenario>{% for key,item in scenarios.items() %}<option>{{ item[0] }}</option>{% endfor %}</select><button class='button primary'>Record simulated assignment</button> <button class=button type=button onclick="this.closest('.compose-box').hidden=true">Cancel</button></form></section></main>""", css=BASE_STYLE, mails=INBOX_MAILS, recipients=DEMO_RECIPIENTS, scenarios=SCENARIOS)

@app.get("/trainings/<key>")
def training_module(key):
    module = TRAINING_MODULES.get(key)
    if not module:
        return "Training module not found", 404
    icon, title, description, red_flags, guidance = module
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class=shell><nav class=nav><div class=brand>SECURITY <b>AWARENESS</b> LAB</div><a href='{{ url_for("trainings") }}'>← All trainings</a></nav><section class='panel lesson-panel'><div class=module-icon>{{ icon }}</div><h1>{{ title }}</h1><p>{{ description }}</p><h2>Red flags to recognize</h2><ul>{% for flag in red_flags %}<li>{{ flag }}</li>{% endfor %}</ul><h2>How to protect yourself</h2><p>{{ guidance }}</p><a class='button primary' href='{{ url_for("detect") }}'>Try the safe detector</a></section></main>""", css=BASE_STYLE, title=title, description=description, red_flags=red_flags, guidance=guidance, icon=icon)

@app.get("/training")
def training_page():
    key = request.args.get("scenario", "banking")
    title, style, _ = SCENARIOS.get(key, SCENARIOS["banking"])
    service_names = {"photos": "PhotoShare", "streaming": "StreamPlus", "payments": "PayCenter", "community": "CommunityHub", "mail": "MailSpace", "social": "SocialCircle", "bank": "Northstar Online Banking"}
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class='login-card {{ style }}'><div class=training>AUTHORIZED AWARENESS SIMULATION · NO CREDENTIALS COLLECTED</div><div class=service-name>{{ service_name }}</div><h1>{{ title }}</h1><p>This generic practice page represents a familiar category, not a real service.</p><form method=post action='{{ url_for("awareness_redirect") }}'><input type=hidden name=scenario value='{{ title }}'><label>Training account ID</label><input value='training@example.invalid' disabled><label>Demo response</label><input type=password placeholder='Any input is ignored' autocomplete=off><button class='button primary'>Continue to awareness feedback</button></form><p class=muted>Passwords are never collected, transmitted, or stored.</p></main>""", css=BASE_STYLE, title=title, style=style, service_name=service_names[style])

@app.post("/awareness-redirect")
def awareness_redirect():
    scenario = request.form.get("scenario", "General")
    record_event(request.form.get("participant"), "Simulated submission redirected", scenario)
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class='login-card'><div class=training>EDUCATIONAL SIMULATION</div><h1>This was a phishing awareness simulation.</h1><p>No credentials were collected, transmitted, or stored.</p><ul><li>Never enter credentials on suspicious links.</li><li>Always verify the sender before clicking links.</li><li>Use a trusted bookmark or official app for important accounts.</li></ul><a class='button primary' href='{{ url_for("home") }}'>Return to training</a></main>""", css=BASE_STYLE)

@app.get("/detect")
def detect():
    value = request.args.get("value", "")
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class=shell><nav class=nav><div class=brand>ANTI-PHISHING <b>DETECTION</b></div><a href='{{ url_for("home") }}'>Training home</a></nav><section class=hero><h1>Defensive indicator review</h1><p class=muted>Local analysis only — this page does not open or contact the supplied destination.</p></section><form class=form-row><input name=value value='{{ value }}' placeholder='URL or page description'><button class='button primary'>Analyze safely</button></form>{% for severity,title,detail in findings %}<div class='finding {{ severity }}'><b>{{ title }}</b><br>{{ detail }}</div>{% endfor %}</main>""", css=BASE_STYLE, value=value, findings=inspect(value) if value else [])

@app.post("/campaign-assigned")
def campaign_assigned():
    scenario = request.form.get("scenario", "General")
    record_event(request.form.get("participant"), "Training email assigned (simulation)", scenario)
    return "<p>Safe local campaign assignment recorded. No email was sent.</p><p><a href='/dashboard'>View dashboard</a></p>"

@app.get("/dashboard")
def dashboard():
    actual = stats()
    display = actual if actual["sent"] else SAMPLE_STATS
    with connection() as db:
        events = db.execute("SELECT * FROM training_events ORDER BY id DESC LIMIT 25").fetchall()
    return render_template_string("""<!doctype html><style>{{ css }}</style><main class=shell><nav class=nav><div class=brand>SECURITY <b>AWARENESS</b> LAB</div><a href='{{ url_for("home") }}'>Training home</a></nav><section class=hero><h1>Campaign statistics</h1><p class=muted>{% if actual.sent %}Live local simulation data.{% else %}Sample training baseline; real events replace it automatically.{% endif %}</p></section><section class=metrics>{% for label,value in [('Emails Sent',display.sent),('Links Clicked',display.clicked),('Credentials Submitted',display.submitted),('Success Rate',display.success_rate|string + '%')] %}<article class='card metric'><small>{{ label }}</small><strong>{{ value }}</strong></article>{% endfor %}</section><section class=grid><article class=panel><h2>Learning funnel</h2><div class=funnel><div>{{ display.sent }} emails sent</div><div>{{ display.clicked }} links clicked</div><div>{{ display.submitted }} simulated submissions</div></div><p class=muted>“Credentials submitted” is a simulated awareness event only; input is ignored.</p></article><article class=panel><h2>Record a local campaign</h2><form method=post action='{{ url_for("campaign_assigned") }}'><input name=participant required placeholder='Authorized participant ID'><select name=scenario>{% for key,item in scenarios.items() %}<option>{{ item[0] }}</option>{% endfor %}</select><button class='button primary'>Record assignment</button></form><p><a href='{{ url_for("report_csv") }}'>Download CSV report</a> · <a href='{{ url_for("report_text") }}'>Download text report</a></p></article></section><section class='panel' style='margin-top:16px'><h2>Recent activity</h2><table><tr><th>Participant</th><th>Scenario</th><th>Event</th><th>Time</th></tr>{% for e in events %}<tr><td>{{ e.participant }}</td><td>{{ e.scenario }}</td><td>{{ e.event_type }}</td><td>{{ e.created_at }}</td></tr>{% else %}<tr><td colspan=4>No events yet.</td></tr>{% endfor %}</table></section></main>""", css=BASE_STYLE, actual=actual, display=display, events=events, scenarios=SCENARIOS)

@app.get("/reports.csv")
def report_csv():
    data = stats(); out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["Emails Sent", "Links Clicked", "Simulated Submissions", "Success Rate"])
    writer.writerow([data["sent"], data["clicked"], data["submitted"], f'{data["success_rate"]}%'])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=awareness-report.csv"})

@app.get("/reports.txt")
def report_text():
    """Plain-text summary for an authorized training exercise; never includes form content."""
    data = stats()
    report = "\n".join((
        "Phishing Simulation Report",
        "---------------------------",
        f"Emails Sent: {data['sent']}",
        f"Users Clicked: {data['clicked']}",
        f"Simulated Submissions: {data['submitted']}",
        f"Success Rate: {data['success_rate']}%",
        "",
        "Note: Simulated submissions are awareness events only. No credentials or form values were collected.",
    ))
    return Response(report, mimetype="text/plain", headers={"Content-Disposition": "attachment; filename=phishing-simulation-report.txt"})

initialize_database()
if __name__ == "__main__": app.run(host="127.0.0.1", port=5050, debug=True)
