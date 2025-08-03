from flask import Flask, render_template, request, redirect, session
import json
import random
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'super-secret'

# Dummy users (in real app, use a database)
users = {
    "student1": generate_password_hash("pass123")
}

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

@app.route('/exam', methods=['GET', 'POST'])
def exam():
    if 'user' not in session:
        return redirect('/')
    with open('data/question_bank.json') as f:
        all_questions = json.load(f)
    questions = random.sample(all_questions, min(5, len(all_questions)))  # Pick 5 random questions
    if request.method == 'POST':
        score = 0
        for q in questions:
            if request.form.get(q['id']) == q['answer']:
                score += 1
        return render_template('result.html', score=score, total=len(questions))
    return render_template('exam.html', questions=questions)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
