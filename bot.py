import os
import json
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)
import pdfplumber
import google.generativeai as genai

# ==================== الإعدادات ====================
BOT_TOKEN = "8711634325:AAGiz78oW_FT4wc10LHsQ8w31z3HPdDhfl4"
GEMINI_API_KEY = "AIzaSyCWuZa88wNUql8XNgVHuzwam7AlhuzdZ18"

DATA_FILE = "data.json"

# حالات المحادثة
WAITING_PASSWORD = 1
WAITING_PDF = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ==================== قاعدة البيانات البسيطة ====================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"password": "1234", "users": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_verified(user_id):
    data = load_data()
    return str(user_id) in data.get("users", {})

def verify_user(user_id):
    data = load_data()
    data["users"][str(user_id)] = True
    save_data(data)

def get_password():
    return load_data().get("password", "1234")

def has_used_free(user_id):
    data = load_data()
    return data.get("free_used", {}).get(str(user_id), False)

def mark_free_used(user_id):
    data = load_data()
    if "free_used" not in data:
        data["free_used"] = {}
    data["free_used"][str(user_id)] = True
    save_data(data)

# ==================== استخراج النص من PDF ====================
def extract_text_from_pdfs(pdf_paths):
    all_text = ""
    for i, path in enumerate(pdf_paths):
        with pdfplumber.open(path) as pdf:
            text = f"\n\n===== المحاضرة {i+1} =====\n"
            for page in pdf.pages:
                text += page.extract_text() or ""
        all_text += text
    return all_text

# ==================== التلخيص ====================
def summarize_text(text):
    prompt = f"""
أنت أستاذ أكاديمي متخصص في تلخيص المحتوى التعليمي.

قم بتلخيص المحتوى التالي وفق المنهجية الأكاديمية التالية:

1. **مقدمة عامة**: نظرة شاملة على الموضوع
2. **المحاور الرئيسية**: اعرض كل فكرة رئيسية بوضوح
3. **التفاصيل المهمة**: النقاط الأساسية لكل محور
4. **الخلاصة**: أبرز ما يجب حفظه وفهمه

اجعل التلخيص:
- واضحاً ومنظماً
- شاملاً ودقيقاً
- مناسباً للمراجعة قبل الامتحانات
- باللغة العربية الفصيحة

المحتوى:
{text[:15000]}
"""
    response = model.generate_content(prompt)
    return response.text

# ==================== إنشاء الامتحان ====================
def create_exam(text):
    prompt = f"""
أنت أستاذ جامعي متخصص في إعداد الامتحانات.

من المحتوى التالي، أنشئ امتحاناً شاملاً يحتوي على:

**أسئلة الامتحان:**
- 5 أسئلة مقالية (تحتاج شرحاً)
- 5 أسئلة قصيرة (إجابة محددة)
- 10 أسئلة صح/خطأ

**ثم اكتب: الإجابات النموذجية**
اذكر الإجابة الكاملة والنموذجية لكل سؤال

اجعل الأسئلة تغطي جميع محاور المحتوى بشكل متوازن.

المحتوى:
{text[:15000]}
"""
    response = model.generate_content(prompt)
    return response.text

# ==================== أوامر البوت ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    welcome = f"""
👋 أهلاً {name}!

🎓 **بوت تلخيص المحاضرات**

أنا أساعدك في:
📄 **تلخيص المحاضرات** - تلخيص شامل ومنهجي
📝 **إنشاء الامتحانات** - أسئلة مع إجابات نموذجية

📌 يمكنك رفع من **1 إلى 4 محاضرات** PDF

━━━━━━━━━━━━━━━
🆓 **أول تلخيص مجاني تماماً!**
🔐 بعدها تحتاج كلمة المرور

اضغط /summary لتبدأ
"""
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["pdfs"] = []
    context.user_data["mode"] = "summary"
    
    user_id = update.effective_user.id
    
    # تحقق هل مستخدم موثق أو لم يستخدم المجاني بعد
    if is_verified(user_id) or not has_used_free(user_id):
        await update.message.reply_text(
            "📎 أرسل ملفات PDF (من 1 إلى 4 ملفات)\nعندما تنتهي من الإرسال، اكتب /done",
            parse_mode="Markdown"
        )
        return WAITING_PDF
    else:
        await update.message.reply_text(
            "🔐 لقد استخدمت نسختك المجانية!\n\nأدخل كلمة المرور للمتابعة:"
        )
        return WAITING_PASSWORD

async def exam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["pdfs"] = []
    context.user_data["mode"] = "exam"
    
    user_id = update.effective_user.id
    
    if is_verified(user_id):
        await update.message.reply_text(
            "📎 أرسل ملفات PDF (من 1 إلى 4 ملفات)\nعندما تنتهي اكتب /done"
        )
        return WAITING_PDF
    else:
        await update.message.reply_text(
            "🔐 هذه الميزة تتطلب كلمة المرور:\nأدخلها الآن:"
        )
        return WAITING_PASSWORD

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entered = update.message.text.strip()
    correct = get_password()
    
    if entered == correct:
        verify_user(user_id)
        await update.message.reply_text(
            "✅ كلمة المرور صحيحة! مرحباً بك\n\n📎 أرسل ملفات PDF (من 1 إلى 4)\nعندما تنتهي اكتب /done"
        )
        return WAITING_PDF
    else:
        await update.message.reply_text("❌ كلمة المرور خاطئة! حاول مرة أخرى:")
        return WAITING_PASSWORD

async def receive_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("⚠️ أرسل ملف PDF فقط!")
        return WAITING_PDF
    
    doc = update.message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("⚠️ الملف يجب أن يكون PDF!")
        return WAITING_PDF
    
    pdfs = context.user_data.get("pdfs", [])
    
    if len(pdfs) >= 4:
        await update.message.reply_text("⚠️ الحد الأقصى 4 ملفات! اكتب /done للمتابعة.")
        return WAITING_PDF
    
    # تحميل الملف
    file = await doc.get_file()
    path = f"pdf_{update.effective_user.id}_{len(pdfs)}.pdf"
    await file.download_to_drive(path)
    pdfs.append(path)
    context.user_data["pdfs"] = pdfs
    
    await update.message.reply_text(
        f"✅ تم استلام الملف {len(pdfs)}/4\n"
        f"{'اكتب /done للمتابعة' if len(pdfs) >= 4 else 'أرسل المزيد أو اكتب /done'}"
    )
    return WAITING_PDF

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pdfs = context.user_data.get("pdfs", [])
    mode = context.user_data.get("mode", "summary")
    user_id = update.effective_user.id
    
    if not pdfs:
        await update.message.reply_text("❌ لم ترسل أي ملف PDF!")
        return WAITING_PDF
    
    await update.message.reply_text(f"⏳ جاري المعالجة... ({len(pdfs)} ملف)\nانتظر قليلاً...")
    
    try:
        # استخراج النص
        text = extract_text_from_pdfs(pdfs)
        
        if len(text.strip()) < 100:
            await update.message.reply_text("❌ لم أتمكن من قراءة النص من الملفات. تأكد أنها PDF نصية.")
            return ConversationHandler.END
        
        # معالجة حسب النوع
        if mode == "summary":
            result = summarize_text(text)
            header = "📋 **الملخص الشامل**\n\n"
            if not is_verified(user_id):
                mark_free_used(user_id)
        else:
            result = create_exam(text)
            header = "📝 **الامتحان والإجابات النموذجية**\n\n"
        
        # إرسال النتيجة (تقسيم إذا كانت طويلة)
        full_result = header + result
        
        for i in range(0, len(full_result), 4000):
            chunk = full_result[i:i+4000]
            await update.message.reply_text(chunk, parse_mode="Markdown")
        
        context.user_data.clear()
        
        await update.message.reply_text(
            "✅ تم! أرسل /summary لتلخيص جديد أو /exam لإنشاء امتحان"
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
    
    finally:
        # حذف الملفات المؤقتة دائماً حتى عند الخطأ
        for path in pdfs:
            if os.path.exists(path):
                os.remove(path)
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # حذف الملفات المؤقتة عند الإلغاء
    pdfs = context.user_data.get("pdfs", [])
    for path in pdfs:
        if os.path.exists(path):
            os.remove(path)
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء. اكتب /start للبداية.")
    return ConversationHandler.END

# ==================== أمر المشرف - تغيير كلمة المرور ====================
ADMIN_ID = 8711634325  # ID حساب المشرف

async def change_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر للمشرف فقط!")
        return
    
    if not context.args:
        await update.message.reply_text("الاستخدام: /setpass كلمة_المرور_الجديدة")
        return
    
    new_pass = context.args[0]
    data = load_data()
    data["password"] = new_pass
    save_data(data)
    
    await update.message.reply_text(f"✅ تم تغيير كلمة المرور إلى: `{new_pass}`", parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    data = load_data()
    users_count = len(data.get("users", {}))
    free_count = len(data.get("free_used", {}))
    password = data.get("password", "غير محدد")
    
    await update.message.reply_text(
        f"📊 **إحصائيات البوت**\n\n"
        f"👥 المشتركين المدفوعين: {users_count}\n"
        f"🆓 مستخدمو النسخة المجانية: {free_count}\n"
        f"🔑 كلمة المرور الحالية: `{password}`",
        parse_mode="Markdown"
    )

# ==================== تشغيل البوت ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # المحادثة الرئيسية
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("summary", summary_command),
            CommandHandler("exam", exam_command),
        ],
        states={
            WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)],
            WAITING_PDF: [
                MessageHandler(filters.Document.ALL, receive_pdf),
                CommandHandler("done", done_command),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpass", change_password))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل!")
    app.run_polling()

if __name__ == "__main__":
    main()
