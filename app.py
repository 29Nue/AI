from flask import Flask, render_template, request, redirect, url_for, flash # type: ignore
from deep_translator import GoogleTranslator  # type: ignore
import speech_recognition as sr  # type: ignore
from gtts import gTTS  # type: ignore
from pydub import AudioSegment  # type: ignore
from pydub.utils import which  # type: ignore
import os
import google.generativeai as genai  # type: ignore
import json
from datetime import datetime



# Cài đặt
AudioSegment.converter = which("ffmpeg")
genai.configure(api_key="AIzaSyDivJEnLAKUhoj0kXrB-EDfQ77YQqECUv0")  # Gemini API

app = Flask(__name__)
app.secret_key = "emiu-dang-yeu-vo-cuc-2025"

# Đường dẫn lưu lịch trình
DATA_PATH = "data/schedules.json"

def load_schedules():
    if not os.path.exists(DATA_PATH):
        return {}

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
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

@app.route("/speech_translate", methods=["POST"])
def speech_translate():
    r = sr.Recognizer()

    if "voice_input" not in request.files:
        return redirect(url_for("translate"))

    file = request.files["voice_input"]
    input_path = "static/audio/voice_input.webm"
    wav_path = "static/audio/converted.wav"
    file.save(input_path)

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

    # Giữ nguyên phần phát âm giọng nói
    tts = gTTS(speech_translated, lang=target_lang)
    tts.save("static/audio/output.mp3")

    return render_template(
        "translate.html",
        translated="",
        original_text="",
        lang=target_lang,
        speech_text=speech_text,
        speech_translated=speech_translated
    )

# Phát âm văn bản dịch (không reload trang)
@app.route("/speak_translated", methods=["POST"])
def speak_translated():
    text = request.form.get("text_to_speak", "")
    lang = request.form.get("lang", "en")

    if not text:
        return "No text provided", 400

    tts = gTTS(text, lang=lang)
    mp3_path = "static/audio/text_output.mp3"
    tts.save(mp3_path)

    return send_file(mp3_path, mimetype="audio/mpeg") # type: ignore

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
                response = chat.send_message(question)
                answer = response.text
            except Exception as e:
                answer = f"Lỗi kết nối Gemini: {e}"

    return render_template("ai_tutor.html", question=question, answer=answer)

# AI CẢM XÚC
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
                    f"Phân tích cảm xúc sau đoạn văn sau và đưa ra gợi ý cải thiện tinh thần:\"{emotion_text}\"."
                )
                emotion_response = response.text
            except Exception as e:
                emotion_response = f"Lỗi kết nối Gemini: {e}"

    return render_template("emotion.html", emotion_text=emotion_text, emotion_response=emotion_response)

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
    if request.method == "POST":
        selected_date = request.form.get("date")
        tasks = json.loads(request.form.get("tasks_json", "[]"))

        schedules = load_schedules()

        schedules[selected_date] = tasks

        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(schedules, f, ensure_ascii=False, indent=2)

        return redirect(url_for("view_schedule_list"))

    return render_template("time_manager.html")

# 🗂️ GIAI ĐOẠN 2.1: Danh sách các ngày đã có lịch
@app.route("/schedule_list", methods=["GET", "POST"])
def view_schedule_list():
    schedules = load_schedules()

    if request.method == "POST":
        date_to_delete = request.form.get("delete_date")
        if date_to_delete and date_to_delete in schedules:
            del schedules[date_to_delete]
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(schedules, f, ensure_ascii=False, indent=2)
            flash(f"🗑️ Đã xóa lịch trình ngày {date_to_delete}", "info")
        else:
            flash("❌ Không tìm thấy ngày cần xóa", "danger")

        return redirect(url_for("view_schedule_list"))  # 👈 ở lại danh sách

    sorted_dates = sorted(schedules.keys(), reverse=True)
    return render_template("schedule_list.html", dates=sorted_dates)

# 📝 GIAI ĐOẠN 2.2: Chi tiết lịch trình theo ngày
@app.route("/schedule/<date>", methods=["GET", "POST"])
def view_schedule_by_date(date):
    schedules = load_schedules()
    today = datetime.now().date()
    date_obj = datetime.strptime(date, "%Y-%m-%d").date()

    if request.method == "POST":
        action = request.form.get("action")
        index = int(request.form.get("index", -1))

        if date not in schedules or not (0 <= index < len(schedules[date])):
            flash("❌ Không tìm thấy lịch trình!", "danger")
            return redirect(url_for("view_schedule_by_date", date=date))

        task = schedules[date][index]

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
            schedules[date].pop(index)
            flash("🗑️ Đã xóa lịch trình!", "info")

        # Ghi file và redirect sau khi xử lý bất kỳ action nào
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(schedules, f, ensure_ascii=False, indent=2)

        return redirect(url_for("view_schedule_by_date", date=date))


    # Nếu là GET
    task_list = schedules.get(date, [])
    now = datetime.now()

    for task in task_list:
        if not task.get("done"):
            task_time = datetime.strptime(f"{date} {task['time']}", "%Y-%m-%d %H:%M")
            if task_time < now:
                task["status"] = "tre"
                task["message"] = "😢 Trễ mất rồi, lần sau cố nha~"

    return render_template("schedule_detail.html", date=date, tasks=task_list, now=now)


@app.route('/calculator_tools')
def calculator_tools():
    return render_template('calculator_tools.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

