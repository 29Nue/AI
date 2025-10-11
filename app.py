from flask import Flask,jsonify, render_template, request, redirect, url_for, flash, session,send_from_directory # type: ignore
from deep_translator import GoogleTranslator  # type: ignore
import speech_recognition as sr  # type: ignore
from gtts import gTTS  # type: ignore
from pydub import AudioSegment  # type: ignore
from pydub.utils import which  # type: ignore
import os
import google.generativeai as genai  # type: ignore
import json
import base64
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
import cv2,  uuid # type: ignore
from docx import Document # type: ignore
from PIL import Image # type: ignore
import io
from datetime import datetime, timedelta


# Cài đặt
AudioSegment.converter = which("ffmpeg")
genai.configure(api_key="AIzaSyD5fOve7k8CZMfZNWChXLcuLpHxVsclY0E")  # Gemini API

app = Flask(__name__)
app.secret_key = "emiu-dang-yeu-vo-cuc-2025"



USERS_FILE = "data/users.json"
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)


os.makedirs("static/audio", exist_ok=True)
os.makedirs("data", exist_ok=True)


# TRANG CHÍNH
@app.route("/")
def home():
    return render_template("index.html")
#Dang nhap
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        # Check admin
        if username == "nhi" and password == "123456":
            session["username"] = "nhi"
            session["role"] = "admin"
            flash("Đăng nhập thành công với quyền Admin!", "success")
            return redirect("/")

        users = load_users()
        if username not in users:
            flash("Tài khoản không tồn tại!", "danger")
            return render_template("login.html")

        user = users[username]

        if not check_password_hash(user["password"], password):
            flash("Mật khẩu không đúng!", "danger")
            return render_template("login.html")

        # Check duyệt giảng viên
        if user["role"] == "teacher" and not user.get("approved", False):
            flash("Tài khoản giảng viên của bạn chưa được duyệt!", "warning")
            return render_template("login.html")

        # Lưu session
        session["username"] = username
        session["role"] = user["role"]

        flash(f"Đăng nhập thành công! Bạn là { 'Giảng viên' if user['role']=='teacher' else 'Học sinh' }.", "success")
        return redirect("/")

    return render_template("login.html")

@app.route("/approve_teachers")
def approve_teachers():
    users = load_users()
    teachers = []
    for username, info in users.items():
        if info.get("role") == "teacher":
            teachers.append({
                "username": username,
                "created_at": info.get("created_at", "N/A"),
                "approved": info.get("approved", False)
            })
    return render_template("approve_teachers.html", teachers=teachers)


@app.route("/approve_teacher/<username>")
def approve_teacher(username):
    users = load_users()
    if username in users and users[username].get("role") == "teacher":
        users[username]["approved"] = True
        save_users(users)
        flash(f"✅ Đã duyệt giảng viên {username} thành công!", "success")
    else:
        flash("⚠️ Không tìm thấy giảng viên cần duyệt!", "danger")
    return redirect(url_for("approve_teachers"))


@app.route("/remove_teacher/<username>")
def remove_teacher(username):
    users = load_users()
    if username in users and users[username].get("role") == "teacher":
        users.pop(username)
        save_users(users)
        flash(f"🗑️ Đã xóa giảng viên {username} thành công!", "danger")
    else:
        flash("⚠️ Không tìm thấy giảng viên cần xóa!", "warning")
    return redirect(url_for("approve_teachers"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        users = load_users()
        
        # ❌ Không cho trùng với bất kỳ username nào trong JSON
        if username in users:
            flash("Tên đăng ký đã tồn tại! Vui lòng chọn tên khác.", "danger")
            return render_template("register.html")

        # ❌ Không cho trùng với tài khoản admin mặc định
        if username == "nhi":
            flash("Tên này được dành cho admin, hãy chọn tên khác!", "danger")
            return render_template("register.html")

        # Phân loại vai trò (nếu form có chọn role)
        role = request.form.get("role", "student")

        user_data = {
            "password": generate_password_hash(password),
            "role": role,
            "approved": True if role == "student" else False
        }

        users[username] = user_data
        save_users(users)

        if role == "teacher":
            flash("Đăng ký thành công! Vui lòng chờ admin duyệt tài khoản giảng viên.", "info")
        else:
            flash("Đăng ký thành công! Hãy đăng nhập.", "success")

        return redirect(url_for("login"))  # ✅ về trang login

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()  # Xóa toàn bộ session
    flash("Bạn đã đăng xuất!", "info")
    return redirect(url_for("login"))  # Quay về trang login

#===============
# AI DỊCH
@app.route("/translate", methods=["GET", "POST"])
def translate():
    translated_text = ""
    original_text = ""
    lang = "en"

    if request.method == "POST":
        original_text = request.form.get("text_input", "")
        lang = request.form.get("lang", "en")

        if original_text.strip():
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = f"""
            Nhiệm vụ của bạn là DỊCH chính xác đoạn văn sau sang ngôn ngữ "{lang}".
            - Nếu có ý cần giải thích hoặc phân tích thêm, hãy ghi ở DÒNG MỚI sau bản dịch, bắt đầu bằng '📘 Giải thích:'.
            - Tuyệt đối không trộn phần giải thích vào nội dung dịch chính.
            Đoạn cần dịch:
            {original_text}
            """
            response = model.generate_content(prompt)
            translated_text = response.text.strip()

    return render_template(
        "translate.html",
        translated=translated_text,
        original_text=original_text,
        lang=lang
    )
    
# AI GHI ÂM + DỊCH + PHÁT ÂM
from datetime import datetime

@app.route("/speech_translate", methods=["POST"])
def speech_translate():
    os.makedirs("static/audio", exist_ok=True)
    r = sr.Recognizer()

    if "voice_input" not in request.files:
        return redirect(url_for("translate"))

    file = request.files["voice_input"]
    input_path = "static/audio/voice_input.webm"
    wav_path = "static/audio/converted.wav"
    file.save(input_path)

    # chuyển webm -> wav
    AudioSegment.from_file(input_path).export(wav_path, format="wav")

    try:
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
            speech_text = r.recognize_google(audio, language="vi-VN")
    except sr.UnknownValueError:
        return render_template("translate.html",
            speech_text="Không nghe rõ, vui lòng thử lại",
            speech_translated="", lang="en")
    except sr.RequestError:
        return render_template("translate.html",
            speech_text="Lỗi kết nối với Google Speech API",
            speech_translated="", lang="en")

    target_lang = request.form.get("target_lang", "en")
    speech_translated = GoogleTranslator(source='auto', target=target_lang).translate(speech_text)

    # 🔸 tạo tên file mp3 duy nhất
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    mp3_filename = f"output_{timestamp}.mp3"
    mp3_path = os.path.join("static/audio", mp3_filename)

    # lưu file mp3
    tts = gTTS(speech_translated, lang=target_lang)
    tts.save(mp3_path)

    # truyền tên file mp3 sang html
    audio_url = f"/{mp3_path}"

    return render_template(
        "translate.html",
        lang=target_lang,
        speech_text=speech_text,
        speech_translated=speech_translated,
        audio_file=audio_url
    )


# AI HỌC TẬP
@app.route("/ai_tutor", methods=["GET", "POST"])
def ai_tutor():
    question = ""
    answer = ""

    if request.method == "POST":
        question = request.form.get("question", "")
        if question:
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                chat = model.start_chat(history=[])
                response = chat.send_message(f"{question}\n\nHãy trả lời hoàn toàn bằng tiếng Việt.")
                answer = response.text

                # Gộp nhiều dòng trống liên tiếp thành 1 dòng trống
                answer = re.sub(r'\n\s*\n+', '\n', answer.strip())

            except Exception as e:
                answer = f"Lỗi kết nối Gemini: {e}"

    return render_template("ai_tutor.html", question=question, answer=answer)
# AI CẢM XÚC
import re

@app.route("/emotion", methods=["GET", "POST"])
def emotion():
    emotion_text = ""
    emotion_response = ""

    if request.method == "POST":
        emotion_text = request.form.get("emotion_text", "")
        if emotion_text:
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                response = model.generate_content(
                    f"Người dùng viết: \"{emotion_text}\".\n\n"
                    "Hãy phân tích cảm xúc này và đưa ra gợi ý cải thiện tinh thần. "
                    "Trả lời hoàn toàn bằng tiếng Việt, trình bày rõ ràng, chia ý theo từng đoạn."
                )
                # Lấy text
                emotion_response = response.text
                # Gộp nhiều dòng trống liên tiếp thành 1
                emotion_response = re.sub(r'\n\s*\n+', '\n', emotion_response.strip())
            except Exception as e:
                emotion_response = f"Lỗi kết nối Gemini: {e}"

    return render_template("emotion.html",
                           emotion_text=emotion_text,
                           emotion_response=emotion_response)

# tinh toan vui
@app.route('/calculator_tools')
def calculator_tools():
    return render_template('calculator_tools.html')


DATA_FILE = "data/classrooms.json"

def load_classrooms():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_classrooms(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# Trang chính AI Hỗ Trợ Giáo Dục
@app.route("/ai_education", methods=["GET", "POST"])
def ai_education():
    user = session.get("user", "Khách")
    classrooms = load_classrooms()
    lectures = load_lectures()
    links = load_links()   # ← load link học tập từ JSON
    quizzes = load_quizzes()     
    all_results = load_quiz_results()  # list dict kết quả
    username = session.get("username")

    # thêm flag để template check
    for q in quizzes:
        q["has_done"] = any(r["quiz_id"] == q["id"] and r["user"] == username for r in all_results)


    return render_template("ai_education.html", 
                           user=user, 
                           classrooms=classrooms,
                           lectures=lectures,
                           links=links,  # ← truyền links vào template
                            quizzes=quizzes)


    # Nếu form Thêm Lớp được submit
    if request.method == "POST":
        class_name = request.form.get("class_name")
        teacher = request.form.get("teacher")
        time = request.form.get("time")
        description = request.form.get("description")

        # Tạo ID mới
        new_id = max([c["id"] for c in classrooms], default=100) + 1

        # Thêm lớp mới với trạng thái mặc định là pending
        new_class = {
            "id": new_id,
            "name": class_name,
            "teacher": teacher,
            "time": time,
            "description": description,
            "subject": "general",  
            "link": f"https://meet.jit.si/class{new_id}",
            "status": "pending"   # mặc định chưa hoàn thành
        }

        classrooms.append(new_class)
        save_classrooms(classrooms)  # Lưu lại JSON

        return redirect(url_for("ai_education"))

    return render_template(
        "ai_education.html",
        user=user,
        classrooms=classrooms
    )


# Vào phòng học trực tiếp trên Jitsi
@app.route("/class/<int:class_id>")
def class_room(class_id):
    classrooms = load_classrooms()
    cls = next((c for c in classrooms if c["id"] == class_id), None)

    if not cls:
        return "Không tìm thấy lớp", 404

    if cls.get("status") == "done":
        return "<h2>Lớp học đã kết thúc ✅</h2>"

    # Redirect sang link Jitsi (vd: https://meet.jit.si/class101)
    return redirect(cls["link"])


# Đánh dấu lớp hoàn thành
@app.route("/class/<int:class_id>/complete", methods=["POST"])
def complete_class(class_id):
    classrooms = load_classrooms()
    for c in classrooms:
        if c["id"] == class_id:
            c["status"] = "done"  # đổi trạng thái
            break
    save_classrooms(classrooms)
    return redirect(url_for("ai_education"))
# Xóa lớp học
@app.route("/class/<int:class_id>/delete", methods=["POST"])
def delete_class(class_id):
    classrooms = load_classrooms()
    classrooms = [c for c in classrooms if c["id"] != class_id]
    save_classrooms(classrooms)
    return redirect(url_for("ai_education"))

#baigiang
import uuid
LECTURE_FILE = "data/lectures.json"
UPLOAD_FOLDER = "uploads/lectures"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def load_lectures():
    try:
        with open(LECTURE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_lectures(data):
    with open(LECTURE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
@app.route("/lecture/view/<filename>")
def view_lecture(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)

@app.route("/lecture/upload", methods=["POST"])
def upload_lecture():
    if "username" not in session:
        return redirect(url_for("login"))

    title = request.form["title"]
    file = request.files["file"]

    if file:
        # tạo tên file duy nhất
        filename = f"{uuid.uuid4()}_{file.filename}" # type: ignore
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        lectures = load_lectures()
        lectures.append({
        "id": str(uuid.uuid4()),
        "title": title,
        "filename": filename,
        "uploader": session.get("username"),
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M")  # ngày giờ upload
    })

        save_lectures(lectures)

    return redirect(url_for("ai_education"))


@app.route("/lecture/download/<filename>")
def download_lecture(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True) # type: ignore

# Sửa bài giảng
@app.route("/lecture/edit/<lecture_id>", methods=["GET", "POST"])
def edit_lecture(lecture_id):
    if "username" not in session or session.get("role") != "teacher":
        flash("⚠️ Chỉ giảng viên mới được sửa bài giảng", "danger")
        return redirect(url_for("ai_education"))

    lectures = load_lectures()
    lecture = next((l for l in lectures if l["id"] == lecture_id), None)
    if not lecture:
        flash("❌ Bài giảng không tồn tại", "danger")
        return redirect(url_for("ai_education"))

    if request.method == "POST":
        lecture["title"] = request.form.get("title", lecture["title"])
        save_lectures(lectures)
        flash("✏️ Đã cập nhật bài giảng!", "success")
        return redirect(url_for("ai_education"))

    return render_template("edit_lecture.html", lecture=lecture)


# Xóa bài giảng
@app.route("/lecture/delete/<lecture_id>", methods=["POST"])
def delete_lecture(lecture_id):
    if "username" not in session or session.get("role") != "teacher":
        flash("⚠️ Chỉ giảng viên mới được xóa bài giảng", "danger")
        return redirect(url_for("ai_education"))

    lectures = load_lectures()
    lectures = [l for l in lectures if l["id"] != lecture_id]
    save_lectures(lectures)
    flash("🗑️ Đã xóa bài giảng!", "info")
    return redirect(url_for("ai_education"))

#Link hoc tap
LINKS_FILE = "data/links.json"

def load_links():
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_links(data):
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/links/add", methods=["POST"])
def add_link():
    if "username" not in session:
        return redirect(url_for("login"))

    title = request.form["title"]
    description = request.form.get("description", "")
    url = request.form["url"]

    links = load_links()
    links.append({
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "url": url,
        "added_by": session.get("username")
    })
    save_links(links)
    flash("✅ Thêm link học tập thành công!", "success")
    return redirect(url_for("ai_education"))

@app.route("/links/delete/<link_id>", methods=["POST"])
def delete_link(link_id):
    if "username" not in session:
        return redirect(url_for("login"))

    links = load_links()
    links = [l for l in links if l["id"] != link_id]
    save_links(links)
    flash("🗑️ Đã xóa link.", "info")
    return redirect(url_for("ai_education"))

REGISTER_FILE = "data/registers.json"

def load_registers():
    if os.path.exists(REGISTER_FILE):
        with open(REGISTER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_registers(data):
    with open(REGISTER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/class/<class_id>/register", methods=["GET", "POST"])
def register_class(class_id):
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        student_name = request.form.get("student_name")
        img_data = request.form.get("captured_image")

        if not student_name or not img_data:
            flash("❌ Vui lòng nhập tên và chụp ảnh khuôn mặt.", "danger")
            return redirect(url_for("register_class", class_id=class_id))

        # Giải mã ảnh base64
        img_data = img_data.split(",")[1]  # bỏ phần 'data:image/png;base64,...'
        img_bytes = base64.b64decode(img_data)

        face_dir = os.path.join("static", "faces")
        os.makedirs(face_dir, exist_ok=True)
        filename = f"{student_name}_{uuid.uuid4().hex}.png"
        filepath = os.path.join(face_dir, filename)

        with open(filepath, "wb") as f:
            f.write(img_bytes)

        # Lưu thông tin đăng ký
        registers = load_registers()
        registers.append({
            "student": student_name,
            "class_id": class_id,
            "class_name": f"Lớp {class_id}",
            "face_image": f"faces/{filename}"
        })
        save_registers(registers)

        flash("🎉 Đăng ký học thành công!", "success")
        return redirect(url_for("view_registers"))

    return render_template("register_face.html", class_id=class_id)

@app.route("/class/registers")
def view_registers():
    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in ["admin", "teacher"]:
        flash("⛔ Bạn không có quyền xem danh sách đăng ký.", "danger")
        return redirect(url_for("ai_education"))

    registers = load_registers()
    return render_template("register_list.html", registers=registers)

# KIEM TRA
QUIZ_FILE = "data/quizzes.json"

# ========== UTILS ==========
def load_quizzes():
    if os.path.exists(QUIZ_FILE):
        with open(QUIZ_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_quizzes(quizzes):
    os.makedirs("data", exist_ok=True)
    with open(QUIZ_FILE, "w", encoding="utf-8") as f:
        json.dump(quizzes, f, ensure_ascii=False, indent=2)

def extract_text_from_docx(filepath):
    doc = Document(filepath)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)

def count_questions_in_text(text):
    import re
    matches = re.findall(r"Câu\s*\d+[:.]", text, flags=re.IGNORECASE)
    return len(matches) if matches else None

# ========== AI GENERATE ==========
def ai_generate_questions(text, num_questions=None):
    prompt = f"""
Bạn là một trợ lý giáo dục. 
Từ đoạn văn bản sau, hãy tạo {num_questions} câu hỏi trắc nghiệm, 
mỗi câu có 4 phương án (A, B, C, D) và một đáp án đúng.

Trả về JSON array, mỗi phần tử:
{{
  "question": "...?",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "answer": "A"
}}

Đoạn văn bản:
\"\"\" 
{text}
\"\"\"
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    content = response.text.strip()

    # --- xử lý JSON ---
    import re, json
    try:
        # Lấy phần JSON thuần từ text
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            content = match.group(0)
        questions = json.loads(content)

        clean = []
        for q in questions:
            if "question" in q and "options" in q and "answer" in q:
                clean.append(q)
        return clean
    except Exception as e:
        print("⚠️ Lỗi parse JSON:", e, "\nContent:\n", content)
        return []

# ========== ROUTES ==========

@app.route("/quiz/auto", methods=["POST"])
def create_auto_quiz():
    quizzes = load_quizzes()

    title = request.form["title"]
    duration = int(request.form["duration"])
    file = request.files["file"]

    if not file:
        return "Chưa upload file Word", 400

    filepath = os.path.join("uploads", file.filename)
    os.makedirs("uploads", exist_ok=True)
    file.save(filepath)

    # Trích text và gọi AI
    text = extract_text_from_docx(filepath)
    questions = ai_generate_questions(text)
    if not questions:
        flash("❌ AI không tạo được câu hỏi, kiểm tra lại file Word!", "danger")
        return redirect(url_for("ai_education"))


    new_quiz = {
        "id": len(quizzes) + 1,
        "title": title,
        "duration": duration,
        "num_questions": len(questions),
        "questions": questions,
        "creator": session.get("username", "Giáo viên"),
        "created_at": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "type": "Trắc nghiệm AI"
    }


    quizzes.append(new_quiz)
    save_quizzes(quizzes)

    return redirect(url_for("ai_education"))


@app.route("/quiz/essay", methods=["POST"])
def create_essay_quiz():
    quizzes = load_quizzes()

    title = request.form["title"]
    duration = int(request.form["duration"])
    content = request.form["content"]

    new_quiz = {
        "id": len(quizzes) + 1,
        "title": title,
        "duration": duration,
        "num_questions": 1,
        "questions": [
            {
                "question": content,
                "options": {},
                "answer": None
            }
        ],
        "creator": session.get("username", "Giáo viên"),
        "created_at": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "type": "Tự luận"
    }

    quizzes.append(new_quiz)
    save_quizzes(quizzes)

    return redirect(url_for("ai_education"))

# Khi vào trang làm quiz
@app.route("/quiz/<int:quiz_id>")
def start_quiz(quiz_id):
    quizzes = load_quizzes()
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        flash("❌ Không tìm thấy bài kiểm tra.", "danger")
        return redirect(url_for("ai_education"))
    if quiz.get("locked"):
        flash("⚠️ Bài kiểm tra này đã bị khóa. Bạn không thể làm bài.", "warning")
        return redirect(url_for("ai_education"))
    username = session.get("username")
    all_results = load_quiz_results()

    # ✅ Ràng buộc: nếu user đã làm quiz này → redirect sang danh sách kết quả
    if any(r["quiz_id"] == quiz_id and r["user"] == username for r in all_results):
        flash("⚠️ Bạn chỉ được làm bài kiểm tra này 1 lần.", "warning")
        return redirect(url_for("quiz_results_list", quiz_id=quiz_id))

    # Lưu thời gian bắt đầu vào session
    session['start_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template("quiz_start.html", quiz=quiz)


RESULTS_FILE = "data/quiz_results.json"

@app.route("/quiz/<int:quiz_id>/submit", methods=["POST"])
def submit_quiz(quiz_id):
    username = session.get("username", "Unknown")
    quizzes = load_quizzes()  # load quiz từ JSON hoặc nguồn khác
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        flash("❌ Không tìm thấy bài kiểm tra.", "danger")
        return redirect(url_for("ai_education"))

    # ===== Tính thời gian làm bài =====
    start_time = session.get("start_time")
    end_time = datetime.now()
    time_used = 0
    if start_time:
        start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        time_used = (end_time - start_time).seconds // 60

    # ===== Chấm điểm =====
    user_answers = {}
    score = 0
    questions = quiz["questions"]
    for idx, q in enumerate(questions):
        ans = request.form.get(f"q{idx}")
        user_answers[idx] = ans
        if quiz.get("type") == "Trắc nghiệm AI" and ans == q.get("answer"):
            score += 1

    # ===== Tạo dict kết quả =====
    result = {
        "quiz_id": quiz_id,
        "user": username,
        "title": quiz.get("title"),
        "total": len(questions),
        "score": score if quiz.get("type") == "Trắc nghiệm AI" else None,
        "answers": user_answers,
        "time_used": time_used,
        "submitted_at": end_time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # ===== Lưu vào JSON =====
    save_quiz_result(result)

    return render_template("quiz_result.html", result=result, quiz=quiz)

# ===== Hàm load JSON =====
def load_quiz_results():
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)
            if isinstance(results, list):
                return results
            return []
    except FileNotFoundError:
        return []

# ===== Hàm save JSON =====
def save_quiz_result(result):
    results = load_quiz_results()
    # chỉ lưu nếu user chưa làm quiz này
    if not any(r["quiz_id"] == result["quiz_id"] and r["user"] == result["user"] for r in results):
        results.append(result)
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


@app.route("/quiz/<int:quiz_id>/results")
def quiz_results_list(quiz_id):
    quizzes = load_quizzes()
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        flash("❌ Không tìm thấy bài kiểm tra.", "danger")
        return redirect(url_for("ai_education"))

    # đọc tất cả kết quả từ file JSON
    all_results = load_quiz_results()  # trả về list
    # lọc theo quiz_id
    results = [r for r in all_results if r["quiz_id"] == quiz_id]

    return render_template("quiz_results_list.html", quiz=quiz, results=results)

@app.route("/quiz/<int:quiz_id>/lock", methods=["POST"])
def lock_quiz(quiz_id):
    quizzes = load_quizzes()
    quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    if not quiz:
        flash("❌ Không tìm thấy bài kiểm tra.", "danger")
        return redirect(url_for("ai_education"))

    # Chỉ cho teacher hoặc admin khóa
    if session.get("role") not in ["teacher", "admin"]:
        flash("⚠️ Bạn không có quyền thực hiện thao tác này.", "warning")
        return redirect(url_for("ai_education"))

    quiz["locked"] = True
    save_quizzes(quizzes)  # Hàm ghi lại JSON

    flash(f"🔒 Bài kiểm tra '{quiz['title']}' đã bị khóa.", "success")
    return redirect(url_for("ai_education"))

# ===== Hàm save toàn bộ results =====
def save_quiz_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


@app.route("/quiz/<int:quiz_id>/delete", methods=["POST"])
def delete_quiz(quiz_id):
    quizzes = load_quizzes()
    quiz = next((q for q in quizzes if q.get("id") == quiz_id), None)

    if not quiz:
        flash("❌ Không tìm thấy bài kiểm tra.", "danger")
        return redirect(url_for("ai_education"))

    # Ràng buộc quyền xoá
    if not (
        session.get("role") == "admin"
        or (session.get("role") == "teacher" and session.get("username") == quiz.get("creator"))
    ):
        flash("⚠️ Bạn không có quyền xoá bài kiểm tra này.", "warning")
        return redirect(url_for("ai_education"))

    # Thực hiện xoá
    quizzes = [q for q in quizzes if q.get("id") != quiz_id]
    save_quizzes(quizzes)

    # Xoá luôn kết quả liên quan
    results = load_quiz_results()
    results = [r for r in results if r.get("quiz_id") != quiz_id]
    save_quiz_results(results)

    flash("✅ Đã xoá bài kiểm tra và toàn bộ kết quả liên quan.", "success")
    return redirect(url_for("ai_education"))

#THONG TIN CA NHAN
PROFILE_FILE = "data/profile.json"

def load_profiles():
    if not os.path.exists(PROFILE_FILE):
        return {}
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:  # file rỗng
                return {}
            return json.loads(content)
    except json.JSONDecodeError:
        return {}


def save_profiles(profiles):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "username" not in session:
        flash("⚠️ Bạn cần đăng nhập trước khi chỉnh sửa thông tin.", "warning")
        return redirect(url_for("login"))

    username = session["username"]
    profiles = load_profiles()

    # Nếu chưa có profile cho user → tạo trống
    user_profile = profiles.get(username, {
        "name": "",
        "student_id": "",
        "birthdate": "",
        "gender": "",
        "hometown": ""
    })

    if request.method == "POST":
        # Lấy dữ liệu từ form
        user_profile = {
            "name": request.form.get("name", "").strip(),
            "student_id": request.form.get("student_id", "").strip(),
            "birthdate": request.form.get("birthdate", "").strip(),
            "gender": request.form.get("gender", "").strip(),
            "hometown": request.form.get("hometown", "").strip()
        }

        # Cập nhật vào dict profiles theo username
        profiles[username] = user_profile
        save_profiles(profiles)

        flash("✅ Cập nhật thông tin thành công!", "success")
        return redirect(url_for("profile"))
        

    # Truyền dữ liệu ra giao diện
    return render_template("profile.html", user=user_profile, username=username)

@app.route("/profile/<username>/<int:quiz_id>")
def view_profile(username, quiz_id):
    profiles = load_profiles()
    user = profiles.get(username)

    if not user:
        flash("❌ Không tìm thấy thông tin người dùng.", "danger")
        return redirect(url_for("ai_education"))

    return render_template("profile_view.html", user=user, username=username, quiz_id=quiz_id)

# Route đến trang AI Tạo Lịch Trình
@app.route('/ai_schedule')
def ai_schedule_page():
    if "username" not in session:
        return redirect(url_for("login"))
    
    # Nếu login rồi thì render trang tạo lịch trình
    return render_template("ai_schedule.html")

SCHEDULE_FILE = "data/scheduleNew.json"

def load_schedules():
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_schedules(data):
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Route trả về toàn bộ lịch trình
@app.route('/get_all_schedules')
def get_all_schedules():
    username = request.args.get('username') or session.get('username')
    schedules = load_schedules()
    if username:
        # chỉ trả lịch của user đó
        schedules = [s for s in schedules if s.get('username') == username]
    return jsonify(schedules)

# Route đánh dấu hoàn thành
@app.route('/mark_complete/<int:schedule_id>', methods=['POST'])
def mark_complete(schedule_id):
    # username có thể gửi trong body JSON hoặc lấy từ session
    body = {}
    try:
        body = request.get_json(force=False) or {}
    except Exception:
        body = {}
    username = body.get('username') or request.form.get('username') or session.get('username')

    schedules = load_schedules()
    updated = False
    for s in schedules:
        if s.get("id") == schedule_id:
            # kiểm tra ownership (nếu schedule gắn username)
            owner = s.get("username")
            if owner and username and owner != username:
                return jsonify({"error": "Không có quyền sửa lịch này"}), 403
            s["status"] = "hoàn thành"
            updated = True
            break

    if updated:
        save_schedules(schedules)
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Không tìm thấy lịch"}), 404

# Xóa lịch: chỉ xóa khi cùng username (hoặc admin nếu ko truyền username)
@app.route('/delete_schedule/<int:schedule_id>', methods=['POST'])
def delete_schedule(schedule_id):
    try:
        body = request.get_json(force=False) or {}
    except Exception:
        body = {}
    username = body.get('username') or request.form.get('username') or session.get('username')

    schedules = load_schedules()
    target = None
    for s in schedules:
        if s.get("id") == schedule_id:
            target = s
            break

    if not target:
        return jsonify({"error": "Không tìm thấy lịch"}), 404

    owner = target.get("username")
    if owner and username and owner != username:
        return jsonify({"error": "Không có quyền xóa lịch này"}), 403

    # xóa thật
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    save_schedules(schedules)
    return jsonify({"success": True})

# Route xử lý ảnh và append vào JSON
@app.route('/process_image', methods=['POST'])
def process_image_route():
    if 'file' not in request.files:
        return jsonify({"error": "Không tìm thấy file ảnh"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "File không hợp lệ"}), 400

    # username có thể được gửi kèm trong form hoặc lấy từ session
    username = request.form.get('username') or session.get('username')

    schedule_data = ai_generate_schedule(file)
    if schedule_data:
        schedules = load_schedules()
        max_id = max([s.get("id", 0) for s in schedules], default=0)
        for item in schedule_data.get("schedule", []):
            max_id += 1
            item["id"] = max_id
            item["status"] = "chưa"
            # gán username nếu có (nếu ko có, để None hoặc 'public')
            if username:
                item["username"] = username
            else:
                item["username"] = "public"
            # nếu item chưa có date, map theo start_date (đã có hàm get_date_for_weekday)
            if "date" not in item or not item["date"] or item["date"] == "N/A":
                item["date"] = get_date_for_weekday(schedule_data.get("start_date", "N/A"), item.get("day", ""))
            # nếu group rỗng thì xoá key cho gọn
            if "group" in item and (item["group"] is None or str(item["group"]).strip() == ""):
                item.pop("group", None)

        schedules.extend(schedule_data.get("schedule", []))
        save_schedules(schedules)
        return jsonify(schedule_data)
    else:
        return jsonify({"error": "Không thể xử lý ảnh. Vui lòng thử lại"}), 500


# Hàm xử lý logic chính: gửi ảnh đến Gemini và yêu cầu trích xuất thông tin
def ai_generate_schedule(image_file):
    """
    Gửi ảnh thời khóa biểu đến Gemini 1.5-flash để trích xuất thông tin.
    """
    try:
        img = Image.open(io.BytesIO(image_file.read()))
        
        prompt = """
        Phân tích hình ảnh thời khóa biểu này. Trích xuất các thông tin sau:
            1. Bắt đầu từ ngày và từ ngày.
            2. Tên các môn học.
            3. Thứ (Thứ Hai, Thứ Ba, ...).
            4. Tiết học (ví dụ: 678, 12345).
            5. Nhóm học (nếu có, nếu không có thì để chuỗi rỗng "")
            6. Phòng học.
            Dựa vào bảng quy ước sau, hãy tính thời gian tương ứng cho mỗi môn:
            - Tiết 1: 7:30-8:20
            - Tiết 2: 8:20-9:10
            - Tiết 3: 9:10-10:00
            - Tiết 4: 10:10-11:00
            - Tiết 5: 11:00-11:50
            - Tiết 6: 13:00-13:50
            - Tiết 7: 13:50-14:40
            - Tiết 8: 14:40-15:30
            - Tiết 9: 15:40-16:30
            - Tiết 10: 16:30-17:20

            - Quy tắc: Với một chuỗi tiết học, hãy chỉ lấy giờ bắt đầu của tiết đầu tiên và giờ kết thúc của tiết cuối cùng.
            - Lưu ý đặc biệt: Tiết 10 được ký hiệu là số 0 hoặc 10. Khi bạn thấy một số 0 đứng sau một số từ 1 đến 9, hãy hiểu nó là tiết 10. Ví dụ, "90" là Tiết 9 và Tiết 10.

            - Ví dụ:
                - Tiết 123: Lấy giờ bắt đầu của Tiết 1 (7:30) và giờ kết thúc của Tiết 3 (10:00). Kết quả: "7:30-10:00".
                - Tiết 45: Lấy giờ bắt đầu của Tiết 4(10h10) và giờ kết thúc của Tiết 5 (11h50). Kết quả: "10:10-11:50".
                - Tiết 12345: 7:30-11:50.
                - Tiết 678: Lấy giờ bắt đầu của Tiết 6 (13:00) và giờ kết thúc của Tiết 8 (15:30). Kết quả: "13:00-15:30".
                - Tiết 90: Lấy giờ bắt đầu của Tiết 9 (15:40) và giờ kết thúc của Tiết 10 (17:20). Kết quả: "15:40-17:20".
                - Tiết 67890: Lấy giờ bắt đầu của Tiết 6 (13:00) và giờ kết thúc của Tiết 10 (17:20). Kết quả: "13:00-17:20".

            Xuất kết quả dưới định dạng JSON, với cấu trúc sau:
            {
            "start_date": "Ngày bắt đầu học",
            "week_info": "Tuần học và ngày bắt đầu-kết thúc",
            "schedule": [
                {
                "subject": "Tên môn học",
                "day": "Thứ",
                "sessions": "Tiết học",
                "group": "Nhóm học hoặc chuỗi rỗng nếu không có",
                "room": "Phòng học",
                "time": "Thời gian"
                }
            ]
            }
        """
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content([prompt, img])
        content = response.text.strip()
        
        # Thêm logic để xử lý JSON trả về
        # Tìm phần tử JSON trong chuỗi trả về (nếu có)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            json_string = match.group(0)
            try:
                schedule_data = json.loads(json_string)

                # ✅ thêm date cho từng lịch
                for item in schedule_data.get("schedule", []):
                    item["date"] = get_date_for_weekday(
                        schedule_data.get("start_date", "N/A"),
                        item.get("day", "")
                    )

                # Trả về đối tượng JSON đã parse và bổ sung date
                return schedule_data

            except json.JSONDecodeError as e:
                print(f"Lỗi JSONDecodeError: {e}")
                print(f"Chuỗi JSON bị lỗi: {json_string}")
                return None


    except Exception as e:
        print(f"Lỗi xử lý ảnh: {e}")
        return None
    
    
def get_date_for_weekday(start_date_str, weekday_name):
    """
    Trả về ngày (dd/mm/yyyy) ứng với weekday_name dựa vào start_date.
    Hỗ trợ cả dạng 'Thứ Hai', 'Thứ 2', '2', 'T2', ...
    """
    from datetime import datetime, timedelta
    
    # Map chuẩn (Mon=0, Sun=6)
    weekday_map = {
        "thứ hai": 0, "thứ 2": 0, "2": 0, "t2": 0,
        "thứ ba": 1, "thứ 3": 1, "3": 1, "t3": 1,
        "thứ tư": 2, "thứ 4": 2, "4": 2, "t4": 2,
        "thứ năm": 3, "thứ 5": 3, "5": 3, "t5": 3,
        "thứ sáu": 4, "thứ 6": 4, "6": 4, "t6": 4,
        "thứ bảy": 5, "thứ 7": 5, "7": 5, "t7": 5,
        "chủ nhật": 6, "cn": 6, "8": 6
    }

    # Chuẩn hóa weekday_name về chữ thường
    wk = str(weekday_name).strip().lower()
    target_index = weekday_map.get(wk, None)
    if target_index is None:
        return "N/A"

    # Chuẩn hóa start_date
    try:
        if "-" in start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        else:
            start_date = datetime.strptime(start_date_str, "%d/%m/%Y")
    except Exception:
        return "N/A"

    # Giả định start_date là Thứ Hai đầu tuần
    delta_days = target_index - 0
    target_date = start_date + timedelta(days=delta_days)
    return target_date.strftime("%d/%m/%Y")

@app.route('/get_sorted_schedules')
def get_sorted_schedules():
    username = request.args.get('username') or session.get('username')
    schedules = load_schedules()
    if username:
        schedules = [s for s in schedules if s.get('username') == username]

    from datetime import datetime

    def parse_date_safe(d):
        if not d or d == "N/A":
            return datetime.max
        try:
            if "-" in d:
                return datetime.strptime(d.strip(), "%Y-%m-%d")
            return datetime.strptime(d.strip(), "%d/%m/%Y")
        except:
            return datetime.max

    def parse_time_safe(t):
        if not t or t == "N/A":
            return datetime.min
        try:
            start = str(t).split("-")[0].strip()
            # thêm 0 nếu chỉ có 1 chữ số giờ
            if re.match(r"^\d:\d{2}$", start):
                start = "0" + start
            return datetime.strptime(start, "%H:%M")
        except:
            return datetime.min

    def status_order_safe(status):
        order = {"chưa": 0, "trễ": 1, "hoàn thành": 2, "hoàn thành trễ": 3}
        if not status:
            return 0
        return order.get(status.strip().lower(), 99)

    schedules.sort(
        key=lambda s: (
            status_order_safe(s.get("status")),
            parse_date_safe(s.get("date")),
            parse_time_safe(s.get("time"))
        )
    )

    return jsonify(schedules)

#Thi
EXAM_FILE = "data/exams.json"

# ---- Load & Save Exams ----
def load_exams():
    if os.path.exists(EXAM_FILE):
        with open(EXAM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_exams(data):
    with open(EXAM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- Route trả về toàn bộ lịch thi ----
@app.route('/get_all_exams')
def get_all_exams():
    username = request.args.get('username') or session.get('username')
    exams = load_exams()
    if username:
        exams = [e for e in exams if e.get('username') == username]
    return jsonify(exams)

# ---- Route xoá lịch thi ----
@app.route('/delete_exam/<int:exam_id>', methods=['POST'])
def delete_exam(exam_id):
    try:
        body = request.get_json(force=False) or {}
    except Exception:
        body = {}
    username = body.get('username') or request.form.get('username') or session.get('username')

    exams = load_exams()
    target = None
    for e in exams:
        if e.get("id") == exam_id:
            target = e
            break

    if not target:
        return jsonify({"error": "Không tìm thấy lịch thi"}), 404

    owner = target.get("username")
    if owner and username and owner != username:
        return jsonify({"error": "Không có quyền xóa lịch thi này"}), 403

    exams = [e for e in exams if e.get("id") != exam_id]
    save_exams(exams)
    return jsonify({"success": True})

# ---- Route xử lý ảnh và append vào JSON ----
@app.route('/process_exam_image', methods=['POST'])
def process_exam_image_route():
    if 'file' not in request.files:
        return jsonify({"error": "Không tìm thấy file ảnh"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "File không hợp lệ"}), 400

    # Ưu tiên lấy username từ session
    username = session.get('username')
    
    # Nếu session không có, kiểm tra trong form data
    if not username:
        username = request.form.get('username')

    # Nếu vẫn không có username, trả về lỗi
    if not username:
        return jsonify({"error": "Không tìm thấy thông tin người dùng. Vui lòng đăng nhập lại"}), 401

    # Gọi AI để phân tích ảnh lịch thi
    exam_data = ai_generate_exam_schedule(file)

    if exam_data:
        exams = load_exams()
        max_id = max([e.get("id", 0) for e in exams], default=0)
        for item in exam_data.get("exams", []):
            max_id += 1
            item["id"] = max_id
            item["status"] = "chưa"
            # Gán username đã được xác thực
            item["username"] = username
            
        exams.extend(exam_data.get("exams", []))
        save_exams(exams)
        return jsonify(exam_data)
    else:
        return jsonify({"error": "Không thể xử lý ảnh. Vui lòng thử lại"}), 500

def ai_generate_exam_schedule(image_file):
    """
    Gửi ảnh lịch thi đến Gemini để trích xuất thông tin.
    """
    try:
        img = Image.open(io.BytesIO(image_file.read()))
        
        prompt = """
        Phân tích hình ảnh lịch thi này và trích xuất thông tin sau cho từng môn thi:
        1. Tên môn học.
        2. Ngày thi (dd/mm/yyyy).
        3. Giờ thi (ví dụ: 7:30).
        4. Phòng thi.
        5. Số tín chỉ của môn học (nếu có).

        Quy tắc trích xuất và kế thừa thông tin:
        - Nếu trong bảng, một cụm nhiều môn học nằm liền kề theo hàng, nhưng ngày/giờ/phòng chỉ ghi ở **hàng đầu tiên**, thì các môn phía dưới **phải kế thừa** đầy đủ ngày, giờ, phòng từ hàng đầu tiên của cụm đó.
        - **TUYỆT ĐỐI KHÔNG** để trống hoặc điền null.
        - **CHỈ** điền "N/A" cho một trường thông tin khi và chỉ khi nó không được đề cập ở bất kỳ đâu, bao gồm cả các hàng phía trên trong cùng một cụm.
        
        Mỗi môn thi là một đối tượng JSON riêng, ngay cả khi chung ngày/giờ/phòng.

        Xuất kết quả dưới định dạng JSON như sau:
        
        {
        "exam_info": "Thông tin kỳ thi (nếu có, ví dụ: kỳ thi học kỳ 1, năm học 2025)",
        "exams": [
            {
            "subject": "Tên môn học",
            "date": "Ngày thi",
            "time": "Giờ thi",
            "room": "Phòng thi",
            "credits": "Số tín chỉ"
            }
        ]
        }
        """
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([prompt, img])
        content = response.text.strip()
        
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            json_string = match.group(0)
            try:
                exam_data = json.loads(json_string)
                exams = exam_data.get("exams", [])
                
                # Logic xử lý hậu kỳ để kế thừa dữ liệu
                last_valid_date = None
                last_valid_time = None
                last_valid_room = None
                
                for item in exams:
                    # Cập nhật giá trị hợp lệ cuối cùng cho các cột
                    if item.get("date") not in ["N/A", "", None]:
                        last_valid_date = item.get("date")
                    
                    if item.get("time") not in ["N/A", "", None]:
                        last_valid_time = item.get("time")
                    
                    if item.get("room") not in ["N/A", "", None]:
                        last_valid_room = item.get("room")
                
                # Sau khi có các giá trị hợp lệ cuối cùng, duyệt lại để điền vào các trường bị thiếu
                for item in exams:
                    if item.get("date") in ["N/A", "", None]:
                        item["date"] = last_valid_date if last_valid_date else "N/A"
                    
                    if item.get("time") in ["N/A", "", None]:
                        item["time"] = last_valid_time if last_valid_time else "N/A"
                        
                    if item.get("room") in ["N/A", "", None]:
                        item["room"] = last_valid_room if last_valid_room else "N/A"

                    item.setdefault("credits", "N/A")

                return exam_data

            except json.JSONDecodeError as e:
                print(f"Lỗi JSONDecodeError: {e}")
                print(f"Chuỗi JSON bị lỗi: {json_string}")
                return None

    except Exception as e:
        print(f"Lỗi xử lý ảnh lịch thi: {e}")
        return None
########
# if __name__ == "__main__":
#      app.run(debug=True) 
if __name__ == "__main__":
   port = int(os.environ.get("PORT", 5000))
   app.run(host="0.0.0.0", port=port)

