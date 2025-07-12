import asyncio
import logging
import os
import sqlite3
import subprocess

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "7023692797:AAE6Il1tsaJ_9e-L2vq5ranR3Plu4csQnC4"
ADMIN_ID = 5873723609
FILES_DIR = "uploaded_bots"

logging.basicConfig(level=logging.INFO)
os.makedirs(FILES_DIR, exist_ok=True)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

conn = sqlite3.connect("users.db")
cursor = conn.cursor()

def check_and_add_banned_column():
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if "banned" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
        conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    approved INTEGER DEFAULT 0
)
""")
conn.commit()

check_and_add_banned_column()

def is_user_approved(user_id: int) -> bool:
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row is not None and row[0] == 1

def is_user_banned(user_id: int) -> bool:
    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row is not None and row[0] == 1

def approve_user(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET approved = 1, banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def ban_user(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET banned = 1, approved = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def unban_user(user_id: int):
    cursor.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_banned_users():
    cursor.execute("SELECT user_id FROM users WHERE banned = 1")
    return [row[0] for row in cursor.fetchall()]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return await message.answer("🚫 Siz botdan foydalanishdan banlangansiz.")
    if is_user_approved(user_id):
        return await message.answer("✅ Siz tasdiqlangansiz.\nIltimos, <b>.py</b> fayl yuboring.")

    user = message.from_user
    text = (
        f"🆕 <b>Yangi foydalanuvchi:</b>\n"
        f"👤 Ism: {user.full_name}\n"
        f"🔗 Username: @{user.username if user.username else 'yo‘q'}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"❓ Tasdiqlaysizmi yoki ban qilasizmi?"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{user_id}"),
                InlineKeyboardButton(text="❌ Banlash", callback_data=f"ban:{user_id}")
            ]
        ]
    )
    await bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=keyboard)
    await message.answer("⏳ So‘rovingiz yuborildi. Admin tasdiqlamaguncha kuting.")

@dp.callback_query(F.data.startswith("approve:"))
async def approve_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Sizda ruxsat yo‘q.", show_alert=True)
    user_id = int(callback.data.split(":")[1])
    approve_user(user_id)
    await bot.send_message(chat_id=user_id, text="✅ Siz tasdiqlandingiz! Endi .py fayl yuboring.")
    await callback.message.edit_text("✅ Foydalanuvchi tasdiqlandi.")
    await callback.answer()

@dp.callback_query(F.data.startswith("ban:"))
async def ban_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Sizda ruxsat yo‘q.", show_alert=True)
    user_id = int(callback.data.split(":")[1])
    ban_user(user_id)
    await bot.send_message(chat_id=user_id, text="🚫 Siz botdan foydalanishdan banlangansiz.")
    await callback.message.edit_text("❌ Foydalanuvchi ban qilindi.")
    await callback.answer()

@dp.message(Command("unban"))
async def unban_user_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Sizda ruxsat yo‘q.")
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await message.answer("❗ To‘g‘ri foydalaning: <code>/unban user_id</code>")
    user_id = int(args[1])
    unban_user(user_id)
    await message.answer(f"✅ Foydalanuvchi <code>{user_id}</code> unban qilindi.")

@dp.message(Command("banned"))
async def banned_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Sizda ruxsat yo‘q.")
    banned_users = get_banned_users()
    if not banned_users:
        return await message.answer("✅ Banlangan foydalanuvchilar yo‘q.")
    text = "<b>🚫 Banlangan foydalanuvchilar:</b>\n"
    text += "\n".join([f"• <code>{uid}</code>" for uid in banned_users])
    await message.answer(text)

@dp.message(F.document)
async def handle_file(message: types.Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")
    document = message.document
    if not document.file_name.endswith(".py"):
        return await message.answer("⚠️ Faqat .py fayl yuboring.")
    user_dir = os.path.join(FILES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, document.file_name)
    log_path = file_path + ".log"
    pid_path = file_path + ".pid"
    await bot.download(document, destination=file_path)
    subprocess.Popen(
        f"nohup python3 {file_path} > {log_path} 2>&1 & echo $! > {pid_path}",
        shell=True
    )
    await message.answer(f"✅ Fayl saqlandi: <code>{document.file_name}</code>\n🚀 Fon rejimda ishga tushdi.")

@dp.message(Command("mybots"))
async def my_bots(message: types.Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")
    user_dir = os.path.join(FILES_DIR, str(user_id))
    if not os.path.exists(user_dir):
        return await message.answer("📂 Hech qanday fayl topilmadi.")
    files = [f for f in os.listdir(user_dir) if f.endswith(".py")]
    if not files:
        return await message.answer("📂 Hech qanday ishga tushirilgan fayl yo‘q.")
    for filename in files:
        file_path = os.path.join(user_dir, filename)
        log_path = file_path + ".log"
        pid_path = file_path + ".pid"
        buttons = [InlineKeyboardButton(text="📥 Log", callback_data=f"log:{filename}")]
        if os.path.exists(pid_path):
            buttons.append(InlineKeyboardButton(text="🔴 To‘xtatish", callback_data=f"stop:{filename}"))
        markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await message.answer(f"🤖 <code>{filename}</code>", reply_markup=markup)

@dp.callback_query(F.data.startswith("log:"))
async def log_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    filename = callback.data.split(":")[1]
    file_path = os.path.join(FILES_DIR, str(user_id), filename + ".log")
    if not os.path.exists(file_path):
        return await callback.answer("❌ Log fayli topilmadi.", show_alert=True)
    await callback.message.answer_document(FSInputFile(file_path), caption="📥 Log fayli")
    await callback.answer()

@dp.callback_query(F.data.startswith("stop:"))
async def stop_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    filename = callback.data.split(":")[1]
    pid_path = os.path.join(FILES_DIR, str(user_id), filename + ".pid")
    if not os.path.exists(pid_path):
        return await callback.answer("❌ PID topilmadi.", show_alert=True)
    with open(pid_path, "r") as f:
        pid = f.read().strip()
    subprocess.call(["kill", pid])
    os.remove(pid_path)
    await callback.answer("🛑 Bot to‘xtatildi.")
    await callback.message.edit_text(f"🔴 <code>{filename}</code> to‘xtatildi.")

@dp.message(Command("install"))
async def install_lib(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Sizda bu buyruqni bajarish huquqi yo‘q.")
    args = message.text.strip().split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("❗ Kutubxona nomini kiriting.\nMisol: /install aiogram")
    package = args[1].strip()
    await message.answer(f"🔄 <code>{package}</code> o‘rnatilmoqda...")
    proc = await asyncio.create_subprocess_shell(
        f"pip install {package}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        output = stdout.decode().strip()
        await message.answer(f"✅ O‘rnatildi:\n<pre>{output[:1000]}</pre>")
    else:
        error = stderr.decode().strip()
        await message.answer(f"❌ Xato:\n<pre>{error[:1000]}</pre>")

@dp.message(Command("uninstall"))
async def uninstall_lib(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Sizda bu buyruqni bajarish huquqi yo‘q.")
    args = message.text.strip().split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("❗ Kutubxona nomini kiriting.\nMisol: /uninstall aiogram")
    package = args[1].strip()
    await message.answer(f"🗑️ <code>{package}</code> o‘chirilyapti...")
    proc = await asyncio.create_subprocess_shell(
        f"pip uninstall -y {package}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        output = stdout.decode().strip()
        await message.answer(f"✅ O‘chirildi:\n<pre>{output[:1000]}</pre>")
    else:
        error = stderr.decode().strip()
        await message.answer(f"❌ Xato:\n<pre>{error[:1000]}</pre>")

@dp.message(Command("list"))
async def list_installed_packages(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Sizda bu buyruqni bajarish huquqi yo‘q.")
    await message.answer("📦 Kutubxonalar ro‘yxati olinmoqda...")
    proc = await asyncio.create_subprocess_shell(
        "pip list",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        output = stdout.decode().strip()
        if len(output) > 4000:
            path = "pip_list.txt"
            with open(path, "w") as f:
                f.write(output)
            await message.answer_document(FSInputFile(path), caption="📦 pip list")
            os.remove(path)
        else:
            await message.answer(f"<b>📦 pip list:</b>\n<pre>{output}</pre>")
    else:
        error = stderr.decode().strip()
        await message.answer(f"❌ Xato:\n<pre>{error}</pre>")

@dp.message(Command("freeze"))
async def freeze_requirements(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Sizda bu buyruqni bajarish huquqi yo‘q.")
    await message.answer("📝 requirements.txt fayli yaratilmoqda...")
    proc = await asyncio.create_subprocess_shell(
        "pip freeze",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        filename = "requirements.txt"
        with open(filename, "w") as f:
            f.write(stdout.decode())
        await message.answer_document(FSInputFile(filename), caption="📄 requirements.txt")
        os.remove(filename)
    else:
        error = stderr.decode().strip()
        await message.answer(f"❌ Xato:\n<pre>{error}</pre>")

@dp.message(Command("version"))
async def python_version(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Sizda bu buyruqni bajarish huquqi yo‘q.")
    await message.answer("🐍 Python versiyasi aniqlanmoqda...")
    proc = await asyncio.create_subprocess_shell(
        "python3 --version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        version = stdout.decode().strip()
        await message.answer(f"🐍 Python versiyasi: <b>{version}</b>")
    else:
        error = stderr.decode().strip()
        await message.answer(f"❌ Xato:\n<pre>{error}</pre>")

# ======= YANGI QO‘SHILDI: Terminal buyruqlari =======
@dp.message(Command("terminal"))
async def terminal_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Sizda bu buyruqni bajarish huquqi yo‘q.")
    args = message.text.strip().split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("❗ Buyruq kiriting.\nMisol: /terminal ls -la")
    command = args[1]
    await message.answer(f"💻 Buyruq bajarilmoqda:\n<code>{command}</code>")
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip()
    error = stderr.decode().strip()
    if output == "" and error == "":
        await message.answer("✅ Buyruq bajarildi, ammo chiqish yo‘q.")
        return
    text = ""
    if output:
        text += f"📤 Natija:\n<pre>{output[:3000]}</pre>\n"
    if error:
        text += f"⚠️ Xato:\n<pre>{error[:3000]}</pre>"
    await message.answer(text)

@dp.message()
async def fallback_message(message: types.Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")
    await message.answer("✅ Siz tasdiqlangansiz.\nIltimos, <b>.py</b> fayl yuboring.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))