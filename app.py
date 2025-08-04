from flask import Flask, render_template, request, redirect, session, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import generate_password_hash, check_password_hash
import random, os, io
from fpdf import FPDF
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret")

# Firebase setup
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Sample users
users = {
    "admin": generate_password_hash("adminpass"),
    "student1": generate_password_hash("pass123"),
    "student2": generate_password_hash("pass456")
}

# -------------------- Login -------------------- #
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        pword = request.form['password']
        if uname in users and check_password_hash(users[uname], pword):
            session['user'] = uname
            session['is_admin'] = (uname == 'admin')
            return redirect('/admin' if uname == 'admin' else '/exam')
        return render_template('login.html', error="اسم المستخدم أو كلمة المرور غير صحيحة")
    return render_template('login.html')


# -------------------- Exam -------------------- #
@app.route('/exam')
def exam():
    if 'user' not in session or session.get('is_admin'):
        return redirect('/')

    # Pull all questions
    all_questions = []
    for doc in db.collection("question_bank").stream():
        data = doc.to_dict()
        data['id'] = doc.id
        all_questions.append(data)

    grouped = {'1': [], '2': [], '3': []}
    for q in all_questions:
        cat = str(q.get('category'))
        if cat in grouped:
            grouped[cat].append(q)

    selected = []
    per_category = 10
    selected_ids = []
    for cat in grouped:
        sample = random.sample(grouped[cat], min(per_category, len(grouped[cat])))
        selected.extend(sample)
        selected_ids.extend([q['id'] for q in sample])

    session['exam_question_ids'] = selected_ids  # ✅ Only store IDs
    return render_template('exam.html', questions=selected)



# -------------------- Submit -------------------- #
@app.route('/submit', methods=['POST'])
def submit():
    if 'user' not in session or session.get('is_admin'):
        return redirect('/')

    question_ids = session.get('exam_question_ids', [])
    if not question_ids:
        return "⚠️ No exam session found. Please start the exam again."

    # Re-fetch questions by ID
    selected_questions = []
    for qid in question_ids:
        doc = db.collection("question_bank").document(qid).get()
        if doc.exists:
            q = doc.to_dict()
            q['id'] = qid
            selected_questions.append(q)

    score = 0
    answers_record = []

    for q in selected_questions:
        qid = q['id']
        ans = request.form.get(qid)
        correct = ans == q.get('correct_id')
        score += int(correct)
        answers_record.append({
            "qid": qid,
            "answer": ans,
            "correct": correct
        })

    db.collection("scores").add({
        "student": session['user'],
        "score": score,
        "total": len(selected_questions),
        "answers": answers_record,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    session.pop('exam_question_ids', None)
    return render_template("result.html", message=f"✅ تم إرسال اختبارك. نتيجتك: {score} من {len(selected_questions)}")


# -------------------- Admin Dashboard -------------------- #
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect('/')

    scores = db.collection("scores").stream()

    # Group scores by student and keep only the latest
    latest_scores = {}
    for doc in scores:
        data = doc.to_dict()
        student = data.get("student")
        timestamp = data.get("timestamp", datetime.min)
        if student not in latest_scores or timestamp > latest_scores[student]['timestamp']:
            latest_scores[student] = {
                "doc_id": doc.id,
                "score": data.get("score", 0),
                "total": data.get("total", 0),
                "timestamp": timestamp
            }

    results = [{
        "student": student,
        "score": info["score"],
        "total": info["total"],
        "doc_id": info["doc_id"]
    } for student, info in latest_scores.items()]

    return render_template("admin_dashboard.html", scores=results)


# -------------------- Student Detail -------------------- #
@app.route('/student/<doc_id>')
def student_detail(doc_id):
    if not session.get('is_admin'):
        return redirect('/')

    doc = db.collection("scores").document(doc_id).get()
    if not doc.exists:
        return "Not found", 404

    data = doc.to_dict()
    detailed_answers = []

    for ans in data.get('answers', []):
        qid = ans['qid']
        q_doc = db.collection("question_bank").document(qid).get()
        if not q_doc.exists:
            continue
        q_data = q_doc.to_dict()
        detailed_answers.append({
            "qid": qid,
            "question": q_data.get("question_ar", q_data.get("question_en", "")),
            "choices": q_data.get("answers", {}),
            "student_answer": ans['answer'],
            "correct_answer": q_data.get("correct_id"),
            "is_correct": ans['correct']
        })

    return render_template("student_detail.html", student=data['student'], answers=detailed_answers)



# -------------------- Export PDF -------------------- #
@app.route('/export/<doc_id>')
def export_pdf(doc_id):
    doc = db.collection("scores").document(doc_id).get()
    if not doc.exists:
        return "Not found", 404
    data = doc.to_dict()

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('ArialUnicode', '', 'Arial-Unicode-MS.ttf', uni=True)
    pdf.set_font('ArialUnicode', '', 14)

    pdf.cell(0, 10, txt=f"Student: {data['student']}", ln=1)
    pdf.cell(0, 10, txt=f"Score: {data['score']} / {data['total']}", ln=1)
    pdf.ln(10)

    for idx, ans in enumerate(data['answers'], start=1):
        q_line = f"Q{idx}: ID {ans['qid']} - Answer: {ans['answer']} - {'Correct' if ans['correct'] else 'Wrong'}"
        pdf.multi_cell(0, 10, txt=q_line)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"{data['student']}_score.pdf")


# -------------------- Logout -------------------- #
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
