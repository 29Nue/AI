from flask import Flask, render_template, request, redirect, url_for, flash, session,send_from_directory # type: ignore
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

# Cài đặt
AudioSegment.converter = which("ffmpeg")
genai.configure(api_key="AIzaSyDivJEnLAKUhoj0kXrB-EDfQ77YQqECUv0")  # Gemini API

app = Flask(__name__)
app.secret_key = "emiu-dang-yeu-vo-cuc-2025"

# Đường dẫn lưu lịch trình
DATA_PATH = "data/schedules.json"

USERS_FILE = "data/users.json"
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)


def load_schedules():
    if not os.path.exists(DATA_PATH):
        return {}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except json.JSONDecodeError:
        return {}

os.makedirs("static/audio", exist_ok=True)
os.makedirs("data", exist_ok=True)

# Đảm bảo file JSON tồn tại
if not os.path.exists(DATA_PATH):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False)

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

users = {
    "nhi": {"password": "nhi123", "role": "admin", "approved": True, "created_at": str(datetime.now())}
}
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
        if original_text:
            translated_text = GoogleTranslator(source='auto', target=lang).translate(original_text)

    return render_template(
        "translate.html",
        translated=translated_text,
        original_text=original_text,
        lang=lang
    )


# AI GHI ÂM + DỊCH + PHÁT ÂM
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

    # Chuyển webm → wav
    AudioSegment.from_file(input_path).export(wav_path, format="wav")

    try:
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
            speech_text = r.recognize_google(audio, language="vi-VN")
    except sr.UnknownValueError:
        return render_template(
            "translate.html",
            speech_text="Không nghe rõ, vui lòng thử lại",
            speech_translated="",
            lang="en"
        )
    except sr.RequestError:
        return render_template(
            "translate.html",
            speech_text="Lỗi kết nối với Google Speech API",
            speech_translated="",
            lang="en"
        )

    target_lang = request.form.get("target_lang", "en")
    speech_translated = GoogleTranslator(source='auto', target=target_lang).translate(speech_text)

    # Phát âm bản dịch từ giọng nói
    tts = gTTS(speech_translated, lang=target_lang)
    mp3_path = "static/audio/output.mp3"
    tts.save(mp3_path)

    return render_template(
        "translate.html",
        translated="",
        original_text="",
        lang=target_lang,
        speech_text=speech_text,
        speech_translated=speech_translated
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
                model = genai.GenerativeModel("gemini-1.5-flash")
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
                model = genai.GenerativeModel("gemini-1.5-flash")
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

# QUẢN LÝ THỜI GIAN – GIAI ĐOẠN 1: Lập lịch
import os
import json
from datetime import datetime
import random

# 🎯 Hàm đánh giá trạng thái và lời khen theo thời gian hoàn thành
def get_task_status(task_time_str: str, done_time_str: str):
    fmt = "%H:%M"
    task_time = datetime.strptime(task_time_str, fmt)
    done_time = datetime.strptime(done_time_str, fmt)
    diff_minutes = (done_time - task_time).total_seconds() / 60

    khen_dung_gio = [
        "🎉 Làm đúng giờ, đúng chuẩn không cần chỉnh!",
        "✨ Bạn làm đúng giờ như đồng hồ Thụy Sĩ!",
        "💪 Bạn đỉnh thiệt, hoàn thành đúng hẹn rồi!",
        "🕐 Đúng giờ như hẹn hò crush, xịn xò!"
    ]
    khen_30p = [
        "⏱️ Chậm tí thôi nè, vẫn rất tuyệt nha!",
        "💡 Vào làm rồi mới bấm, hợp lý đó!",
        "🌈 Chấp nhận được, vẫn xứng đáng được khen!",
        "👏 Tuy hơi trễ nhẹ, nhưng tinh thần tốt lắm!"
    ]
    loanghoang = [
        "😅 Hơi trễ rồi đó nha, nhớ cố hơn lần sau nha~",
        "🐌 Lịch bị sên kéo hả? Mau cải thiện nghen!",
        "😴 Trễ thiệt rồi, nhưng vẫn hoàn thành là đáng khen!",
        "🧸 Bạn vẫn ổn chứ? Muộn nhưng có trách nhiệm!"
    ]

    if diff_minutes <= 0:
        return "hoanthanh", random.choice(khen_dung_gio)
    elif diff_minutes <= 30:
        return "hoanthanh_som", random.choice(khen_30p)
    else:
        return "hoanthanh_tre", random.choice(loanghoang)

# 🧱 GIAI ĐOẠN 1: Lập bảng lịch trình
@app.route("/time_manager", methods=["GET", "POST"])
def time_manager():
    if "username" not in session:
        flash("⚠️ Vui lòng đăng nhập trước!", "danger")
        return redirect(url_for("login"))

    username = session["username"]
    schedules = load_schedules()

    if request.method == "POST":
        selected_date = request.form.get("date")
        tasks = json.loads(request.form.get("tasks_json", "[]"))

        if username not in schedules:
            schedules[username] = {}

        schedules[username][selected_date] = tasks

        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(schedules, f, ensure_ascii=False, indent=2)

        return redirect(url_for("view_schedule_list"))

    return render_template("time_manager.html")

# 🗂️ GIAI ĐOẠN 2.1: Danh sách các ngày đã có lịch
@app.route("/schedule_list", methods=["GET", "POST"])
def view_schedule_list():
    if "username" not in session:
        flash("⚠️ Vui lòng đăng nhập trước!", "danger")
        return redirect(url_for("login"))

    username = session["username"]
    schedules = load_schedules()
    user_schedules = schedules.get(username, {})

    if request.method == "POST":
        date_to_delete = request.form.get("delete_date")
        if date_to_delete and date_to_delete in user_schedules:
            del user_schedules[date_to_delete]
            schedules[username] = user_schedules
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(schedules, f, ensure_ascii=False, indent=2)
            flash(f"🗑️ Đã xóa lịch trình ngày {date_to_delete}", "info")
        else:
            flash("❌ Không tìm thấy ngày cần xóa", "danger")

        return redirect(url_for("view_schedule_list"))

    sorted_dates = sorted(user_schedules.keys(), reverse=True)
    return render_template("schedule_list.html", dates=sorted_dates)

# 📝 GIAI ĐOẠN 2.2: Chi tiết lịch trình theo ngày
@app.route("/schedule/<date>", methods=["GET", "POST"])
def view_schedule_by_date(date):
    if "username" not in session:
        flash("⚠️ Vui lòng đăng nhập trước!", "danger")
        return redirect(url_for("login"))

    username = session["username"]
    schedules = load_schedules()
    user_schedules = schedules.get(username, {})

    today = datetime.now().date()
    date_obj = datetime.strptime(date, "%Y-%m-%d").date()

    if request.method == "POST":
        action = request.form.get("action")
        index = int(request.form.get("index", -1))

        if date not in user_schedules or not (0 <= index < len(user_schedules[date])):
            flash("❌ Không tìm thấy lịch trình!", "danger")
            return redirect(url_for("view_schedule_by_date", date=date))

        task = user_schedules[date][index]

        if action == "done":
            if date_obj > today:
                flash(f"📅 Chưa đến ngày {date}, không thể đánh dấu hoàn thành nha bạn iu~", "warning")
                return redirect(url_for("view_schedule_by_date", date=date))

            now = datetime.now()
            task_time = datetime.strptime(f"{date} {task['time']}", "%Y-%m-%d %H:%M")

            if now < task_time:
                flash(f"⏳ Chưa tới giờ làm task này đâu nè! Giờ task là {task['time']}", "warning")
                return redirect(url_for("view_schedule_by_date", date=date))

            now_time = now.strftime("%H:%M")
            task["done"] = True
            task["done_time"] = now_time
            task["status"], task["message"] = get_task_status(task["time"], now_time)
            flash("✅ Đã đánh dấu hoàn thành!", "success")

        elif action == "edit":
            task["content"] = request.form.get("new_content", task["content"])
            task["time"] = request.form.get("new_time", task["time"])
            flash("✏️ Đã cập nhật lịch trình!", "success")

        elif action == "delete":
            user_schedules[date].pop(index)
            flash("🗑️ Đã xóa lịch trình!", "info")

        schedules[username] = user_schedules
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(schedules, f, ensure_ascii=False, indent=2)

        return redirect(url_for("view_schedule_by_date", date=date))

    # Nếu là GET
    task_list = user_schedules.get(date, [])
    now = datetime.now()

    for task in task_list:
        if not task.get("done"):
            task_time = datetime.strptime(f"{date} {task['time']}", "%Y-%m-%d %H:%M")
            if task_time < now:
                task["status"] = "tre"
                task["message"] = "😢 Trễ mất rồi, lần sau cố nha~"

    return render_template("schedule_detail.html", date=date, tasks=task_list, now=now)

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
    model = genai.GenerativeModel("gemini-1.5-flash")
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


########
# if __name__ == "__main__":
#     app.run(debug=True) 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

