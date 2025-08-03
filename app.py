from flask import Flask, render_template, request, redirect, session
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import check_password_hash, generate_password_hash
import random

app = Flask(__name__)
app.secret_key = 'super-secret'

# Dummy users (replace with real user DB if needed)
users = {
    "student1": generate_password_hash("pass123")
}

# Initialize Firebase Admin SDK
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        pword = request.form['password']
        if uname in users and check_password_hash(users[uname], pword):
            session['user'] = uname
            return redirect('/exam')
        return render_template('login.html', error="Invalid login")
    return render_template('login.html')

@app.route("/exam", methods=["GET", "POST"])
def exam():
    if 'user' not in session:
        return redirect('/')

    questions_ref = db.collection("question_bank").stream()
    all_questions = [q.to_dict() for q in questions_ref]
    selected_questions = random.sample(all_questions, min(5, len(all_questions)))

    if request.method == "POST":
        score = 0
        for q in selected_questions:
            user_answer = request.form.get(q['id'])
            if user_answer == q['answer']:
                score += 1
        return render_template("result.html", score=score, total=len(selected_questions))

    return render_template("exam.html", questions=selected_questions)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == "__main__":
    app.run(debug=True)
