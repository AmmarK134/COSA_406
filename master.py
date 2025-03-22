from flask import Flask, render_template


app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/faq")
def faq():
    return render_template("faq.html")

if __name__ == "__main__":
    app.run(debug=True)