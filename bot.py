import logging
import asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import BotBlocked
from config import API_TOKEN, ADMIN_IDS

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class ReplyState(StatesGroup):
    waiting_for_reply = State()

admin_target_user = {}
user_active_admin = {}
user_greeted = set()
admin_status = {admin: 'idle' for admin in ADMIN_IDS}
waiting_users = []
user_ratings = {}

def load_welcome_message():
    with open("welcome_message.txt", "r", encoding="utf-8") as f:
        return f.read()

def load_common_questions():
    with open("common_questions.txt", "r", encoding="utf-8") as f:
        return f.read()

def user_end_chat_button():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔚 Akhiri Sesi Live Chat", callback_data="end_chat_user")
    )

def rating_buttons(user_id):
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = [
        InlineKeyboardButton(str(i), callback_data=f"rate:{user_id}:{i}")
        for i in range(1, 6)
    ]
    markup.add(*buttons)
    return markup

@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    if message.chat.id in ADMIN_IDS:
        await message.answer("🔧 Panel admin aktif.")
        return
    keyboard = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("👥 Join Live Chat", callback_data="join_livechat"),
        InlineKeyboardButton("🌐 Website Resmi", url="https://brimbstk.my.id")
    )
    await message.answer(
        "📊 Selamat datang di *BRIMBO STOCK – Asisten Transaksi Saham Otomatis* 📈\n\nKlik *Join Live Chat* untuk mulai ngobrol dengan admin.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data == "join_livechat")
async def handle_join_chat(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Reset sesi lama
    old_admin = user_active_admin.pop(user_id, None)
    if old_admin:
        admin_target_user.pop(old_admin, None)
        admin_status[old_admin] = 'idle'
        await bot.send_message(
            old_admin,
            f"❌ User [{user_id}](tg://user?id={user_id}) memulai sesi baru.",
            parse_mode="Markdown"
        )
        await assign_next_user(old_admin)

    if user_id in waiting_users:
        waiting_users.remove(user_id)

    user_greeted.discard(user_id)

    await callback.answer("✅ Bergabung ke sesi live chat.")
    await callback.message.answer(
        "📝 Silakan kirim pesanmu ke admin. Klik tombol di bawah untuk mengakhiri sesi kapan saja.",
        reply_markup=user_end_chat_button()
    )

@dp.message_handler(lambda m: m.chat.id not in ADMIN_IDS)
async def handle_user_message(message: types.Message):
    user_id = message.chat.id

    if (
        user_id not in user_active_admin and
        user_id not in waiting_users and
        user_id in user_greeted and
        not message.text.lower().startswith('/start')
    ):
        await message.answer("⚠️ Sesi live chat kamu telah berakhir. Mengarahkan kembali ke menu utama...")
        await asyncio.sleep(2)
        await handle_start(message)
        return

    if user_id not in user_greeted:
        user_greeted.add(user_id)
        await asyncio.sleep(5)
        await message.answer(load_welcome_message(), parse_mode="Markdown")
        await message.answer(load_common_questions(), parse_mode="Markdown", reply_markup=user_end_chat_button())

    if user_id in user_active_admin:
        admin_id = user_active_admin[user_id]
        await bot.send_message(
            admin_id,
            f"📩 Pesan dari [{message.from_user.full_name}](tg://user?id={user_id}):\n{message.text}",
            parse_mode="Markdown"
        )
    else:
        idle_admin = next((a for a, s in admin_status.items() if s == 'idle'), None)
        if idle_admin:
            admin_status[idle_admin] = 'busy'
            admin_target_user[idle_admin] = user_id
            user_active_admin[user_id] = idle_admin
            await bot.send_message(
                idle_admin,
                f"📩 Pesan dari [{message.from_user.full_name}](tg://user?id={user_id}):\n{message.text}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("✏️ Balas", callback_data=f"reply:{user_id}"),
                    InlineKeyboardButton("🔚 Akhiri Sesi", callback_data=f"end_chat_admin:{user_id}")
                )
            )
            await message.answer("📤 Pesan kamu dikirim ke admin.", reply_markup=user_end_chat_button())
        else:
            if user_id not in waiting_users:
                waiting_users.append(user_id)
                await message.answer("⏳ Semua admin sedang sibuk. Kamu telah masuk dalam antrian.")
            else:
                await message.answer("⏳ Harap tunggu. Kamu masih dalam antrian.")

@dp.callback_query_handler(lambda c: c.data.startswith("reply:"))
async def handle_reply_button(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    user_id = int(callback.data.split(":")[1])
    admin_target_user[admin_id] = user_id
    user_active_admin[user_id] = admin_id
    await callback.answer()
    await bot.send_message(admin_id, "📝 Silakan ketik balasan Anda.")
    await state.set_state(ReplyState.waiting_for_reply)

@dp.message_handler(state=ReplyState.waiting_for_reply)
async def handle_admin_reply(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    user_id = admin_target_user.get(admin_id)
    if user_id:
        await bot.send_message(
            user_id,
            f"🧑‍💼 Admin:\n{message.text}",
            reply_markup=user_end_chat_button()
        )
        await message.answer("✅ Balasan dikirim.")
    else:
        await message.answer("⚠️ Tidak ada target user.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "end_chat_user")
async def handle_user_end_chat(callback: CallbackQuery):
    user_id = callback.from_user.id
    admin_id = user_active_admin.pop(user_id, None)
    if admin_id:
        admin_target_user.pop(admin_id, None)
        admin_status[admin_id] = 'idle'
        await bot.send_message(
            admin_id,
            f"❌ User [{user_id}](tg://user?id={user_id}) mengakhiri sesi.",
            parse_mode="Markdown"
        )
        await assign_next_user(admin_id)
    await callback.message.answer("🔚 Sesi kamu telah diakhiri.")
    await bot.send_message(
        user_id,
        "⭐ Bagaimana pengalaman live chat kamu dengan admin?\nSilakan beri rating 1-5:",
        reply_markup=rating_buttons(user_id)
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("end_chat_admin:"))
async def handle_admin_end_chat(callback: CallbackQuery):
    admin_id = callback.from_user.id
    user_id = int(callback.data.split(":")[1])
    admin_target_user.pop(admin_id, None)
    user_active_admin.pop(user_id, None)
    admin_status[admin_id] = 'idle'
    try:
        await bot.send_message(user_id, "❌ Sesi live chat telah diakhiri oleh admin.")
        await bot.send_message(
            user_id,
            "⭐ Bagaimana pengalaman live chat kamu dengan admin?\nSilakan beri rating 1-5:",
            reply_markup=rating_buttons(user_id)
        )
    except:
        pass
    await callback.message.answer("✅ Sesi ditutup.")
    await callback.answer()
    await assign_next_user(admin_id)

@dp.callback_query_handler(lambda c: c.data.startswith("rate:"))
async def handle_rating(callback: CallbackQuery):
    _, user_id_str, rating = callback.data.split(":")
    user_id = int(user_id_str)
    rating = int(rating)
    user_ratings[user_id] = rating
    await callback.answer("Terima kasih atas ratingnya! 🙏")
    await callback.message.edit_text("✅ Rating kamu telah tercatat. Terima kasih! ⭐")

    # Kirim ke admin terkait
    admin_id = user_active_admin.get(user_id)
    if not admin_id:
        for aid, uid in admin_target_user.items():
            if uid == user_id:
                admin_id = aid
                break

    if admin_id:
        await bot.send_message(
            admin_id,
            f"📊 User [{user_id}](tg://user?id={user_id}) memberikan rating ⭐ *{rating}/5*.",
            parse_mode="Markdown"
        )

async def assign_next_user(admin_id):
    if waiting_users:
        next_user = waiting_users.pop(0)
        admin_status[admin_id] = 'busy'
        admin_target_user[admin_id] = next_user
        user_active_admin[next_user] = admin_id
        await bot.send_message(
            admin_id,
            f"📥 User dari antrean:\n[{next_user}](tg://user?id={next_user}) telah terhubung.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("✏️ Balas", callback_data=f"reply:{next_user}"),
                InlineKeyboardButton("🔚 Akhiri Sesi", callback_data=f"end_chat_admin:{next_user}")
            )
        )
        await bot.send_message(
            next_user,
            "✅ Sekarang kamu telah terhubung dengan admin.",
            reply_markup=user_end_chat_button()
        )

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)