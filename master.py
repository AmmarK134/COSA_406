import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash



app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cosa.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit
db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

USER_ROLES = ['student', 'coordinator', 'employer', 'admin']

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    student_id = db.Column(db.String(50))
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    two_factor_code = db.Column(db.String(6))
    two_factor_expires = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(50), default='submitted')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

class JobPosting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)
    pdf_filename = db.Column(db.String(200))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    editable = db.Column(db.Boolean, default=True)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pdf_filename = db.Column(db.String(200))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Interview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coordinator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


    
    
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register/<role>', methods=['GET', 'POST'])
def register(role):
    if role not in USER_ROLES:
        flash("Invalid role specified.")
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        name = request.form.get('name', '')
        student_id_val = request.form.get('student_id', None) if role == 'student' else None
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("User with that username or email already exists.")
            return redirect(url_for('register', role=role))
        user = User(username=username, email=email, name=name, role=role, student_id=student_id_val)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please login.")
        return redirect(url_for('login'))
    return render_template('register.html', role=role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username']
        password = request.form['password']
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()
        if user and user.check_password(password):
            code = 'test'
            user.two_factor_code = code
            user.two_factor_expires = datetime.utcnow() + timedelta(minutes=5)
            db.session.commit()
            session['temp_user_id'] = user.id
            flash("Verification code sent (simulation).")
            return redirect(url_for('two_factor'))
        else:
            flash("Invalid credentials. Please try again.")
    return render_template('login.html')

@app.route('/two_factor', methods=['GET', 'POST'])
def two_factor():
    if 'temp_user_id' not in session:
        flash("Session expired. Please login again.")
        return redirect(url_for('login'))
    user = User.query.get(session['temp_user_id'])
    if request.method == 'POST':
        code = request.form['code']
        if user.two_factor_code == code and datetime.utcnow() < user.two_factor_expires:
            session.pop('temp_user_id', None)
            session['user_id'] = user.id
            session['role'] = user.role
            session['username'] = user.username
            flash("Two-factor authentication successful.")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid or expired verification code.")
            return redirect(url_for('login'))
    return render_template('2fa.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Please login first.")
        return redirect(url_for('login'))
    role = session.get('role')
    if role == 'student':
        return redirect(url_for('student_dashboard'))
    elif role == 'coordinator':
        return redirect(url_for('coordinator_dashboard'))
    elif role == 'employer':
        return redirect(url_for('employer_dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        flash("Invalid user role.")
        return redirect(url_for('index'))

@app.route('/dashboard/student')
def student_dashboard():
    return render_template("student_dashboard.html")

@app.route('/upload_report')
def upload_report():
    return render_template('upload_report.html')

@app.route('/dashboard/coordinator')
def coordinator_dashboard():
    applications = Application.query.all()
    return render_template('coordinator_dashboard.html', applications=applications)

@app.route('/dashboard/employer')
def employer_dashboard():
    job_postings = JobPosting.query.filter_by(employer_id=session.get('user_id')).all()
    return render_template('employer_dashboard.html', job_postings=job_postings)
@app.route('/add_job')
def add_job():
    return render_template('add_job.html')
@app.route('/dashboard/admin')
def admin_dashboard():
    users = User.query.all()
    return render_template('admin_dashboard.html', users=users)


@app.route('/faq')
def faq():
    return render_template('faq.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
