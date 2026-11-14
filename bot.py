import asyncio
import logging
import math
import os
import random
import string
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
)

# ================= НАЛАШТУВАННЯ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 9132955219
FIREBASE_URL = "https://" + "inroute-keys-default-rtdb" + ".firebaseio.com"

TIERS = {
    "3D": ("Ключ на 3 дня", 15, 3),
    "7D": ("Ключ на 7 дней", 50, 7),
    "30D": ("Ключ на 30 дней", 215, 30),
    "LT": ("Ключ Навсегда (Lifetime)", 450, 0),
}
# ================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def generate_key_string(prefix: str) -> str:
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    return f"{prefix}-{part1}-{part2}"


async def save_key_to_firebase(key: str, duration_days: int, creator_id: int) -> bool:
    url = f"{FIREBASE_URL}/keys/{key}.json"
    payload = {
        "durationDays": duration_days,
        "used": False,
        "deviceId": None,
        "createdBy": creator_id,
    }
    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=payload) as resp:
            return resp.status == 200


def get_user_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for code, (title, stars, _) in TIERS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"⭐ {title} — {stars} Stars",
                callback_data=f"buy_{code}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for code, (title, _, _) in TIERS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"🔑 Створити безкоштовно: {title}",
                callback_data=f"admin_gen_{code}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "👑 **Панель адміністратора**\n\n"
            "Ви можете безкоштовно створювати необмежену кількість одноразових ключів.\n"
            "Команда /shop покаже меню так, як його бачать звичайні покупці.",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "👋 **Вітаємо! Оберіть тариф для отримання ключа доступу:**\n\n"
            "• Кожен ключ є **одноразовим** і прив'язується до вашого браузера.\n"
            "• Видача відбувається миттєво після оплати через **Telegram Stars**.",
            parse_mode="Markdown",
            reply_markup=get_user_keyboard()
        )


@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    await message.answer(
        "🛒 **Вітрина ключів (вигляд для користувачів):**",
        parse_mode="Markdown",
        reply_markup=get_user_keyboard()
    )


@dp.message(Command("trial"))
async def cmd_trial(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Немає доступу!")
        return

    args = (message.text or "").split()
    if len(args) > 2:
        await message.answer("Використання: `/trial [години]`", parse_mode="Markdown")
        return

    try:
        hours = float(args[1]) if len(args) == 2 else 3.0
    except ValueError:
        await message.answer("Кількість годин має бути додатним числом.")
        return

    duration_days = hours / 24
    duration_ms = duration_days * 24 * 60 * 60 * 1000
    if (
        not math.isfinite(hours)
        or hours <= 0
        or duration_ms < 1
        or not math.isfinite(duration_ms)
    ):
        await message.answer("Кількість годин має бути додатним скінченним числом.")
        return

    new_key = generate_key_string("TR")
    saved = await save_key_to_firebase(new_key, duration_days, ADMIN_ID)
    if saved:
        await message.answer(
            f"✅ **Пробний ключ створено на {hours:g} год.!**\n\n"
            f"Ваш одноразовий ключ: `{new_key}`\n"
            f"_(Натисніть на ключ, щоб скопіювати)_",
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Помилка збереження у Firebase.")


@dp.callback_query(F.data.startswith("admin_gen_"))
async def process_admin_generate(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Немає доступу!", show_alert=True)
        return

    tier_code = callback.data.replace("admin_gen_", "")
    title, _, days = TIERS[tier_code]
    new_key = generate_key_string(tier_code)

    saved = await save_key_to_firebase(new_key, days, ADMIN_ID)
    if saved:
        await callback.message.answer(
            f"✅ **Ключ створено ({title})!**\n\n"
            f"Ваш одноразовий ключ: `{new_key}`\n"
            f"_(Натисніть на ключ, щоб скопіювати)_",
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer("❌ Помилка збереження у Firebase.")
    await callback.answer()


@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    tier_code = callback.data.replace("buy_", "")
    title, stars, _ = TIERS[tier_code]

    prices = [LabeledPrice(label=title, amount=stars)]
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description=f"Одноразовий ліцензійний ключ ({title}). Миттєва активація.",
        payload=f"tier_{tier_code}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )
    await callback.answer()


@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    tier_code = payload.replace("tier_", "")
    title, _, days = TIERS[tier_code]

    new_key = generate_key_string(tier_code)
    saved = await save_key_to_firebase(new_key, days, message.from_user.id)

    if saved:
        await message.answer(
            f"🎉 **Дякуємо за покупку!**\n\n"
            f"Тариф: **{title}**\n"
            f"Ваш одноразовий ключ: `{new_key}`\n\n"
            f"Скопіюйте його та вставте у вікно активації розширення.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "⚠️ Оплата пройшла, але виникла помилка збереження ключа. "
            f"Напишіть адміну ID платежу: `{message.successful_payment.telegram_payment_charge_id}`",
            parse_mode="Markdown"
        )


async def handle_ping(request):
    return web.Response(text="Bot is running 24/7!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await start_web_server()
    print("Бот успішно запущений 24/7!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
