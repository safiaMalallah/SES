from flask import Flask, render_template, request, redirect, session, send_file, send_from_directory
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import check_password_hash
import random, os, io
from fpdf import FPDF
from datetime import datetime
import pandas as pd 


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret")

# ---------- Firebase ----------
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ---------- Login ----------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # username field is the email
        email = request.form['username'].strip().lower()
        pword = request.form['password']

        # fetch user by doc-id = email
        doc = db.collection("users").document(email).get()
        if doc.exists:
            user = doc.to_dict() or {}
            # default active=True if not set
            if user.get("active", True) and check_password_hash(user.get("password_hash", ""), pword):
                session['user'] = email
                session['is_admin'] = (user.get('role') == 'admin')
                return redirect('/admin' if session['is_admin'] else '/exam')

        return render_template('login.html', error="اسم المستخدم أو كلمة المرور غير صحيحة")

    return render_template('login.html')

# ---------- Exam ----------
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

    # Group by category
    grouped = {'1': [], '2': [], '3': []}
    for q in all_questions:
        cat = str(q.get('category'))
        if cat in grouped:
            grouped[cat].append(q)

    # Select equal number from each category
    selected, selected_ids = [], []
    per_category = 10
    for cat in grouped:
        sample = random.sample(grouped[cat], min(per_category, len(grouped[cat])))
        selected.extend(sample)
        selected_ids.extend([q['id'] for q in sample])

    # store only IDs in session (small cookie)
    session['exam_question_ids'] = selected_ids
    return render_template('exam.html', questions=selected)

# ---------- Submit ----------
@app.route('/submit', methods=['POST'])
def submit():
    if 'user' not in session or session.get('is_admin'):
        return redirect('/')

    question_ids = session.get('exam_question_ids', [])
    if not question_ids:
        return "⚠️ لا توجد جلسة اختبار. فضلاً ابدأ الاختبار مرة أخرى."

    # re-fetch to avoid trusting client
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
        ans = request.form.get(qid)  # 'A'/'B'/'C'/'D' or None
        correct_id = q.get('correct_id')
        is_correct = (ans == correct_id)
        score += int(is_correct)
        answers_record.append({
            "qid": qid,
            "answer": ans,
            "correct": is_correct
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

# ---------- Admin Dashboard ----------
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect('/')

    scores = db.collection("scores").stream()

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

# ---------- Student Detail ----------
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

# ---------- Export PDF ----------
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

    for idx, ans in enumerate(data.get('answers', []), start=1):
        q_line = f"Q{idx}: ID {ans.get('qid')} - Answer: {ans.get('answer')} - {'Correct' if ans.get('correct') else 'Wrong'}"
        pdf.multi_cell(0, 10, txt=q_line)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"{data['student']}_score.pdf")



# ---------- Export all scores to Excel ----------
@app.route('/admin/export.xlsx')
def export_all_scores():
    if not session.get('is_admin'):
        return redirect('/')

    # Pull all score docs
    score_docs = list(db.collection("scores").stream())

    rows_answers = []   # one row per question answer
    rows_summary = []   # one row per attempt

    # cache to avoid refetching same question
    q_cache = {}

    for doc in score_docs:
        d = doc.to_dict() or {}
        student = d.get("student", "")
        total = d.get("total", 0)
        score = d.get("score", 0)
        ts = d.get("timestamp")
        submitted_at = ts.isoformat() if hasattr(ts, "isoformat") else ""

        rows_summary.append({
            "attempt_id": doc.id,
            "student": student,
            "score": score,
            "total": total,
            "percent": round((score / total) * 100, 2) if total else 0.0,
            "submitted_at": submitted_at,
        })

        for a in d.get("answers", []):
            qid = a.get("qid")
            selected = a.get("answer")
            is_correct = a.get("correct", False)

            # fetch correct_id (and question text) once per qid
            if qid and qid not in q_cache:
                q_doc = db.collection("question_bank").document(qid).get()
                if q_doc.exists:
                    q_data = q_doc.to_dict() or {}
                    q_cache[qid] = {
                        "correct_id": q_data.get("correct_id"),
                        "question": q_data.get("question_ar") or q_data.get("question_en") or "",
                        "A_ar": q_data.get("answers", {}).get("A_ar"),
                        "B_ar": q_data.get("answers", {}).get("B_ar"),
                        "C_ar": q_data.get("answers", {}).get("C_ar"),
                        "D_ar": q_data.get("answers", {}).get("D_ar"),
                    }
                else:
                    q_cache[qid] = {"correct_id": None, "question": ""}

            meta = q_cache.get(qid, {})
            rows_answers.append({
                "attempt_id": doc.id,
                "student": student,
                "submitted_at": submitted_at,
                "qid": qid,
                "question": meta.get("question"),
                "A": meta.get("A_ar"),
                "B": meta.get("B_ar"),
                "C": meta.get("C_ar"),
                "D": meta.get("D_ar"),
                "selected": selected,
                "correct_id": meta.get("correct_id"),
                "is_correct": is_correct,
            })

    # Build Excel in memory
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        if rows_summary:
            pd.DataFrame(rows_summary).sort_values(["student", "submitted_at"]).to_excel(
                xw, sheet_name="Summary", index=False
            )
        else:
            pd.DataFrame(columns=["attempt_id","student","score","total","percent","submitted_at"])\
              .to_excel(xw, sheet_name="Summary", index=False)

        if rows_answers:
            pd.DataFrame(rows_answers).sort_values(["student", "attempt_id", "qid"]).to_excel(
                xw, sheet_name="Answers", index=False
            )
        else:
            pd.DataFrame(columns=["attempt_id","student","submitted_at","qid","question",
                                  "A","B","C","D","selected","correct_id","is_correct"])\
              .to_excel(xw, sheet_name="Answers", index=False)

        # optional: better column widths for first sheet
        wb = xw.book
        ws = xw.sheets.get("Summary")
        if ws:
            ws.set_column(0, 0, 18)  # attempt_id
            ws.set_column(1, 1, 26)  # student
            ws.set_column(2, 5, 14)  # numbers/dates

    out.seek(0)
    return send_file(
        out,
        as_attachment=True,
        download_name="exam_results.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------- Static: data/ (logo etc.) ----------
@app.route('/data/<path:filename>')
def data_file(filename):
    return send_from_directory(os.path.join(app.root_path, 'data'), filename)

# ---------- Logout ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
