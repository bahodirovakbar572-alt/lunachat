import asyncio
import httpx
import json
import base64
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TEXT_MODEL = "openai/gpt-oss-120b:free"
VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"

CHANNEL_USERNAME = "@infortxluna"  # ← O'zgartiring!
GROUP_AUTO_CHANCE = 20  # Har 20 xabarda 1 marta o'zi yozadi

SYSTEM_PROMPT = """Sen Luna ismli aqlli va do'stona AI yordamchisan.
O'zing haqingda: Isming Luna, yaratuvching InfortX.
Faqat o'zbek tilida, do'stona va qisqa javob ber.
Guruhda o'zing yozganda juda qisqa va tabiiy yoz."""

MAX_HISTORY = 10

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

user_histories: dict = {}
group_counters: dict = {}


# ==================== YORDAMCHI FUNKSIYALAR ====================

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status not in ["left", "kicked", "banned"]
    except Exception:
        return False


def sub_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="📢 Kanalga o'tish", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"),
        types.InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")
    ]])


async def ask_ai_stream(messages: list, sent: types.Message, vision: bool = False) -> str:
    """Streaming — lichka uchun"""
    model = VISION_MODEL if vision else TEXT_MODEL
    full_text = ""
    last_update = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages, "stream": True}
            ) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            full_text += delta
                            if len(full_text) - len(last_update) > 40:
                                await sent.edit_text(full_text + " ✍️")
                                last_update = full_text
                                await asyncio.sleep(0.5)
                    except Exception:
                        continue
        except Exception as e:
            return f"Xatolik: {e}"

    if full_text:
        try:
            await sent.edit_text(full_text)
        except Exception:
            pass
    return full_text


async def ask_ai_simple(messages: list, vision: bool = False) -> str:
    """Oddiy javob — guruh uchun"""
    model = VISION_MODEL if vision else TEXT_MODEL
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": messages}
        )
        data = response.json()
        if response.status_code != 200:
            raise Exception(data.get("error", {}).get("message", "Xato"))
        return data["choices"][0]["message"]["content"]


# ==================== START ====================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_histories[message.from_user.id] = []

    if message.chat.type == "private":
        if not await check_subscription(message.from_user.id):
            await message.answer(
                "👋 Salom! Men <b>Luna</b>.\n\n"
                "Botdan foydalanish uchun avval kanalimizga obuna bo'ling:\n"
                f"➡️ {CHANNEL_USERNAME}\n\n"
                "Obuna bo'lgach <b>✅ Tekshirish</b> ni bosing!",
                reply_markup=sub_keyboard()
            )
            return

    await message.answer(
        "👋 Salom! Men <b>Luna</b> — sizning aqlli yordamchingizman.\n"
        "Matn yoki rasm yuboring! 🌙"
    )


# ==================== OBUNA CALLBACK ====================

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "✅ Obuna tasdiqlandi!\n\n"
            "👋 Salom! Men <b>Luna</b> — sizning aqlli yordamchingizman.\n"
            "Matn yoki rasm yuboring! 🌙"
        )
    else:
        await callback.answer("❌ Siz hali obuna bo'lmadingiz!", show_alert=True)


# ==================== LICHKA ====================

@dp.message(F.chat.type == "private")
async def private_handler(message: types.Message):
    user_id = message.from_user.id

    # Obuna tekshirish
    if not await check_subscription(user_id):
        await message.answer(
            f"❌ Botdan foydalanish uchun kanalga obuna bo'ling:\n➡️ {CHANNEL_USERNAME}",
            reply_markup=sub_keyboard()
        )
        return

    if user_id not in user_histories:
        user_histories[user_id] = []

    await bot.send_chat_action(message.chat.id, "typing")
    sent = await message.answer("typing...")

    try:
        # Rasm
        if message.photo:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

            async with httpx.AsyncClient() as client:
                img_res = await client.get(file_url)
                img_b64 = base64.b64encode(img_res.content).decode()

            prompt = message.caption or "Ushbu rasmni tasvirlab ber."
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]}
            ]
            await ask_ai_stream(messages, sent, vision=True)

        # Matn
        elif message.text:
            user_histories[user_id].append({"role": "user", "content": message.text})
            if len(user_histories[user_id]) > MAX_HISTORY:
                user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]

            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_histories[user_id]
            reply = await ask_ai_stream(messages, sent)
            if reply:
                user_histories[user_id].append({"role": "assistant", "content": reply})

        else:
            await sent.edit_text("⚠️ Faqat matn yoki rasm yuboring.")

    except Exception as e:
        await sent.edit_text(f"❌ Xatolik: {str(e)}")


# ==================== GURUH ====================

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message):
    chat_id = message.chat.id
    text = message.text or message.caption or ""

    bot_info = await bot.get_me()
    luna_mentioned = (
    "luna" in text.lower() or
    f"@{bot_info.username}".lower() in text.lower() or
    (message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id)  # ← QO'SHING
)

    # Luna deb yozilsa — reply bilan javob
    if luna_mentioned:
        await bot.send_chat_action(chat_id, "typing")
        try:
            # Rasm bilan luna deb yozilsa
            if message.photo:
                photo = message.photo[-1]
                file = await bot.get_file(photo.file_id)
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

                async with httpx.AsyncClient() as client:
                    img_res = await client.get(file_url)
                    img_b64 = base64.b64encode(img_res.content).decode()

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": text or "Rasmni tasvirla."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]}
                ]
                reply = await ask_ai_simple(messages, vision=True)
            else:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ]
                reply = await ask_ai_simple(messages)

            await message.reply(reply)
        except Exception as e:
            await message.reply(f"❌ Xatolik: {e}")
        return

    # Har 20 xabarda o'zi yozadi
    group_counters[chat_id] = group_counters.get(chat_id, 0) + 1
    if group_counters[chat_id] >= GROUP_AUTO_CHANCE:
        group_counters[chat_id] = 0
        await asyncio.sleep(random.uniform(1, 4))
        await bot.send_chat_action(chat_id, "typing")
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Guruhda shu yozildi: '{text}'. Shunga mos qisqa va tabiiy izoh qo'sh."}
            ]
            reply = await ask_ai_simple(messages)
            await message.answer(reply)
        except Exception:
            pass


# ==================== MAIN ====================

async def main():
    print("🚀 Luna bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())