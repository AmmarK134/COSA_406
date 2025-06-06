import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pyotp
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)
app.config["SECRET_KEY"] = "your_secret_key_here"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cosa.db"
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


USER_ROLES = ["student", "coordinator", "employer", "admin"]


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    student_id = db.Column(db.String(50))
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    two_factor_secret = db.Column(db.String(32))
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_initiated = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_two_factor_secret(self):
        if not self.two_factor_secret:
            self.two_factor_secret = pyotp.random_base32()
        return self.two_factor_secret

    def get_two_factor_uri(self):
        if not self.two_factor_secret:
            self.generate_two_factor_secret()
        totp = pyotp.TOTP(self.two_factor_secret)
        return totp.provisioning_uri(self.email, issuer_name="COSA")

    def verify_two_factor(self, code):
        if not self.two_factor_secret:
            return False
        totp = pyotp.TOTP(self.two_factor_secret)
        return totp.verify(code)


class JobPosting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    job_type = db.Column(db.String(50), nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pdf_filename = db.Column(db.String(200))
    report_type = db.Column(db.String(50), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class CoopApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    student_number = db.Column(db.String(50), unique=True, nullable=False)
    student_year = db.Column(db.Integer, nullable=False)
    linkedin = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default="Under Review")

    def update_status(self, new_status):
        self.status = new_status
        db.session.commit()


if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in USER_ROLES:
        flash("Invalid role specified.")
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        name = request.form.get("name", "")
        student_id_val = (
            request.form.get("student_id", None) if role == "student" else None
        )
        password = request.form["password"]
        enable_2fa = request.form.get("enable_2fa") == "on"
        if User.query.filter(
            (User.username == username) | (User.email == email)
        ).first():
            flash("User with that username or email already exists.")
            return redirect(url_for("register", role=role))
        user = User(
            username=username,
            email=email,
            name=name,
            role=role,
            student_id=student_id_val,
        )
        user.set_password(password)
        user.two_factor_enabled = enable_2fa
        if enable_2fa:
            user.generate_two_factor_secret()
            user.two_factor_initiated = False
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please login.")
        return redirect(url_for("login"))
    return render_template("register.html", role=role)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form["username"]
        password = request.form["password"]
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash(
                    "Your account has been deactivated. Please contact an administrator."
                )
                return redirect(url_for("login"))

            session["temp_user_id"] = user.id
            if not user.two_factor_enabled:
                session.pop("temp_user_id", None)
                session["user_id"] = user.id
                session["role"] = user.role
                session["username"] = user.username
                flash("Login successful.")
                return redirect(url_for("dashboard"))
            return redirect(url_for("two_factor"))
        else:
            flash("Invalid credentials. Please try again.")
    return render_template("login.html")


@app.route("/two_factor", methods=["GET", "POST"])
def two_factor():
    if "temp_user_id" not in session:
        flash("Session expired. Please login again.")
        return redirect(url_for("login"))

    user = User.query.get(session["temp_user_id"])
    if not user:
        flash("User not found.")
        return redirect(url_for("login"))

    if not user.two_factor_enabled:
        session.pop("temp_user_id", None)
        session["user_id"] = user.id
        session["role"] = user.role
        session["username"] = user.username
        flash("Two-factor authentication is disabled. Logged in without verification.")
        return redirect(url_for("dashboard"))

    if not user.two_factor_initiated:

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(user.get_two_factor_uri())
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        qr_code = base64.b64encode(buffered.getvalue()).decode()

        if request.method == "POST":
            code = request.form.get("code")
            if user.verify_two_factor(code):
                user.two_factor_initiated = True
                db.session.commit()
                session.pop("temp_user_id", None)
                session["user_id"] = user.id
                session["role"] = user.role
                session["username"] = user.username
                flash("Two-factor authentication setup and verification successful.")
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid verification code. Please try again.")
        return render_template("2fa.html", qr_code=qr_code, setup_mode=True)

    if request.method == "POST":
        code = request.form.get("code")
        if user.verify_two_factor(code):
            session.pop("temp_user_id", None)
            session["user_id"] = user.id
            session["role"] = user.role
            session["username"] = user.username
            flash("Two-factor authentication successful.")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid verification code.")
            return redirect(url_for("two_factor"))

    return render_template("2fa.html", setup_mode=False)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("index"))


def check_active_user():
    if "user_id" not in session:
        return False
    user = User.query.get(session["user_id"])
    if not user or not user.is_active:
        session.clear()
        flash("Your account has been deactivated. Please contact an administrator.")
        return False
    return True


@app.before_request
def check_user_status():
    if request.endpoint and request.endpoint != "static":
        excluded_routes = ["login", "logout", "index", "register"]
        if request.endpoint not in excluded_routes and "user_id" in session:
            if not check_active_user():
                return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not check_active_user():
        return redirect(url_for("login"))

    role = session.get("role")
    if role == "student":
        return redirect(url_for("student_dashboard"))
    elif role == "coordinator":
        return redirect(url_for("coordinator_dashboard"))
    elif role == "employer":
        return redirect(url_for("employer_dashboard"))
    elif role == "admin":
        return redirect(url_for("admin_dashboard"))
    else:
        flash("Invalid user role.")
        return redirect(url_for("index"))


@app.route("/dashboard/student")
def student_dashboard():
    return render_template("student_dashboard.html")


@app.route("/dashboard/coordinator")
def coordinator_dashboard():
    return render_template("coordinator_dashboard.html")


@app.route("/dashboard/employer")
def employer_dashboard():
    job_postings = JobPosting.query.filter_by(employer_id=session.get("user_id")).all()
    return render_template("employer_dashboard.html", job_postings=job_postings)


@app.route("/dashboard/admin")
def admin_dashboard():
    users = User.query.all()
    return render_template("admin_dashboard.html", users=users)


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/manage_user", methods=["GET", "POST"])
def manage_user():
    if not check_active_user():
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        flash("Access denied.")
        return redirect(url_for("login"))
    if request.method == "POST":
        user_id = request.form.get("user_id")
        action = request.form.get("action")
        user = User.query.get(user_id)
        if action == "delete" and user:
            db.session.delete(user)
            db.session.commit()
            flash("User deleted successfully.")
        elif action == "edit" and user:
            user.role = request.form.get("role")
            db.session.commit()
            flash("User role updated successfully.")
    users = User.query.all()
    return render_template("manage_user.html", users=users)


@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if not check_active_user():
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        flash("Access denied.")
        return redirect(url_for("login"))

    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "activate":
            user.is_active = True
            flash(f"User {user.username} has been activated.")
        elif action == "deactivate":
            user.is_active = False
            flash(f"User {user.username} has been deactivated.")
        elif action == "edit":
            user.role = request.form.get("role")
            user.name = request.form.get("name")
            user.email = request.form.get("email")
            flash(f"User {user.username} has been updated.")

        db.session.commit()
        return redirect(url_for("manage_user"))

    return render_template("edit_user.html", user=user)


@app.route("/add_job", methods=["GET", "POST"])
def add_job():
    if "user_id" not in session or session.get("role") != "employer":
        flash("Access denied.")
        return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form.get("job_title")
        description = request.form.get("job_description")
        location = request.form.get("job_location")
        job_type = request.form.get("job_type")
        deadline_str = request.form.get("application_deadline")
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
        except ValueError:
            flash("Invalid deadline format. Please use YYYY-MM-DD.")
            return redirect(request.url)
        job = JobPosting(
            employer_id=session["user_id"],
            title=title,
            description=description,
            location=location,
            job_type=job_type,
            deadline=deadline,
        )
        db.session.add(job)
        db.session.commit()
        flash("Job posting added successfully.")
        return redirect(url_for("employer_dashboard"))
    return render_template("add_job.html")


@app.route("/upload_report", methods=["GET", "POST"])
def upload_report():
    if not check_active_user():
        return redirect(url_for("login"))

    if session.get("role") != "student":
        flash("Access denied.")
        return redirect(url_for("login"))

    if request.method == "POST":
        if "file" not in request.files:
            flash("No file found.")
            return redirect(request.url)

        file = request.files["file"]
        report_type = request.form.get("reportType")

        if file.filename == "":
            flash("No file selected.")
            return redirect(request.url)

        if not report_type:
            flash("Please select a report type.")
            return redirect(request.url)

        if file and file.filename.lower().endswith(".pdf"):
            try:
                ext = file.filename.rsplit(".", 1)[1].lower()
                unique_filename = (
                    f"{session['user_id']}_{datetime.utcnow().timestamp()}.{ext}"
                )
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

                file.save(filepath)
                report = Report(
                    student_id=session["user_id"],
                    pdf_filename=unique_filename,
                    report_type=report_type,
                )
                db.session.add(report)
                db.session.commit()
                flash("Work term report uploaded successfully.")
                return redirect(url_for("student_dashboard"))
            except Exception as e:
                flash(f"Error uploading file: {str(e)}")
                return redirect(request.url)
        else:
            flash("Only PDF files are allowed for reports.")
            return redirect(request.url)

    return render_template("upload_report.html")


@app.route("/document_portal", methods=["GET", "POST"])
def document_portal():
    if "user_id" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))
    if request.method == "POST":
        if "document" not in request.files:
            flash("No file part.")
            return redirect(request.url)
        file = request.files["document"]
        if file.filename == "":
            flash("No file selected.")
            return redirect(request.url)
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            unique_filename = (
                f"{session['user_id']}_{datetime.utcnow().timestamp()}.{ext}"
            )
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(filepath)
            flash("Document uploaded successfully.")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid file type.")
            return redirect(request.url)
    return render_template("document_portal.html")


@app.route("/application_status", methods=["GET"])
def application_status():
    if "user_id" not in session or session.get("role") != "student":
        flash("Access denied.")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user or not user.name:
        flash("No student name found for the logged-in user.")
        return redirect(url_for("dashboard"))

    application = CoopApplication.query.filter_by(full_name=user.name).first()
    if not application:
        flash("No application found.")
        return redirect(url_for("dashboard"))

    return render_template("application_status.html", application=application)


@app.route("/submit_application", methods=["GET", "POST"])
def submit_application():
    if "user_id" not in session or session.get("role") != "student":
        flash("Access denied.")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    full_name = user.name if user else ""

    if request.method == "POST":
        fullname = request.form.get("fullname")
        address_line1 = request.form.get("addressline1")
        address_line2 = request.form.get("addressline2")
        dob_str = request.form.get("dob")
        student_num = request.form.get("studentnum")
        student_year = request.form.get("level")
        linkedin = request.form.get("linkedin")

        if not all(
            [
                fullname,
                address_line1,
                address_line2,
                dob_str,
                student_num,
                student_year,
                linkedin,
            ]
        ):
            flash("Please fill in all required fields.")
            return render_template(
                "submit_application.html", form=request.form, full_name=full_name
            )

        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.")
            return render_template(
                "submit_application.html", form=request.form, full_name=full_name
            )

        application = CoopApplication(
            full_name=fullname,
            address="{} {}".format(address_line1, address_line2),
            dob=dob,
            student_number=student_num,
            student_year=student_year,
            linkedin=linkedin,
            status="Under Review",
        )
        db.session.add(application)
        db.session.commit()
        flash("Application submitted successfully.")
        return redirect(url_for("dashboard"))

    return render_template("submit_application.html", form={}, full_name=full_name)


@app.route("/application_review", methods=["GET", "POST"])
def application_review():
    if "user_id" not in session or session.get("role") != "coordinator":
        flash("Access denied.")
        return redirect(url_for("login"))

    applications = CoopApplication.query.all()

    if request.method == "POST":
        search_name = request.form.get("name")
        search_email = request.form.get("email")
        search_id = request.form.get("id")

        if search_name:
            applications = [
                app
                for app in applications
                if search_name.lower() in app.full_name.lower()
            ]
        if search_email:
            applications = [
                app
                for app in applications
                if search_email.lower() in app.linkedin.lower()
            ]
        if search_id:
            applications = [
                app for app in applications if search_id == app.student_number
            ]

    return render_template("application_review.html", applications=applications)


@app.route("/accept_application/<int:app_id>", methods=["POST"])
def accept_application(app_id):
    if "user_id" not in session or session.get("role") != "coordinator":
        flash("Access denied.")
        return redirect(url_for("login"))

    application = CoopApplication.query.get(app_id)
    if not application:
        flash("Application not found.")
        return redirect(url_for("application_review"))

    application.status = "Accepted"
    db.session.commit()
    flash(f"Application for {application.full_name} has been accepted.")
    return redirect(url_for("application_review"))

@app.route("/reject_application/<int:app_id>", methods=["POST"])
def reject_application(app_id):
    if "user_id" not in session or session.get("role") != "coordinator":
        flash("Access denied.")
        return redirect(url_for("login"))

    application = CoopApplication.query.get(app_id)
    if not application:
        flash("Application not found.")
        return redirect(url_for("application_review"))

    application.status = "Rejected"
    db.session.commit()
    flash(f"Application for {application.full_name} has been rejected.")
    return redirect(url_for("application_review"))

@app.route("/view_reminders", methods=["GET"])
def view_reminders():
    if "user_id" not in session or session.get("role") != "student":
        flash("Access denied.")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user:
        flash("User not found.")
        return redirect(url_for("dashboard"))


    reminders = []

    if not reminders:
        flash("No reminders found.")
        return redirect(url_for("dashboard"))

    return render_template("view_reminders.html", reminders=reminders)


if __name__ == "__main__":
    RESET_DB = 0  # Set to 1 to reset the database, keep as 0 to keep data
    with app.app_context():
        if RESET_DB:
            db.drop_all()
            db.create_all()

            default_password = "password"

            default_users = [
                ("student", "student", "student@example.com", "Student Name"),
                (
                    "coordinator",
                    "coordinator",
                    "coordinator@example.com",
                    "Coordinator Name",
                ),
                ("employer", "employer", "employer@example.com", "Employer Name"),
                ("admin", "admin", "admin@example.com", "Admin Name"),
            ]

            for role, username, email, name in default_users:
                user = User(role=role, username=username, email=email, name=name)
                user.set_password(default_password)
                user.two_factor_enabled = False
                db.session.add(user)

            db.session.commit()

    app.run(debug=True)
