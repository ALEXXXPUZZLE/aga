import asyncio
import logging

import httpx
import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

# ============ КОНФИГУРАЦИЯ ============
BOT_TOKEN = "8931082488:AAGNTk7_fg2RJfnRK3p52_wE3ADqvgT4AFs"
API_KEY = "idUAeMTqIB9wfoA2vOSvTduxHdFHdti2Pz"
SERVER = "RU1"  # Поменял на RU1

BASE_URL = "https://api.majestic-files.net"
HEADERS = {
    "X-API-Key": API_KEY,
    "X-Language": "ru"
}

DB_NAME = "data.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============ БАЗА ДАННЫХ ============
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS tracks(
            user_id INTEGER,
            item TEXT,
            last_count INTEGER DEFAULT 0,
            last_min INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, item)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS notified(
            user_id INTEGER,
            item_name TEXT,
            item_id INTEGER,
            price INTEGER,
            PRIMARY KEY(user_id, item_name, item_id)
        )
        """)

        # Таблица для настроек пользователя
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            user_id INTEGER PRIMARY KEY,
            server TEXT DEFAULT 'RU1'
        )
        """)

        await db.commit()
        logger.info("База данных инициализирована")


async def add_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users VALUES(?)", (user_id,))
        await db.execute("INSERT OR IGNORE INTO settings(user_id) VALUES(?)", (user_id,))
        await db.commit()


async def get_user_server(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT server FROM settings WHERE user_id=?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else "RU1"


async def set_user_server(user_id: int, server: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        UPDATE settings SET server=? WHERE user_id=?
        """, (server, user_id))
        await db.commit()


async def add_track(user_id: int, item: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT OR IGNORE INTO tracks(user_id, item)
        VALUES(?, ?)
        """, (user_id, item))
        await db.commit()


async def remove_track(user_id: int, item: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM tracks WHERE user_id=? AND item=?", (user_id, item))
        await db.commit()


async def get_tracks(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT item FROM tracks WHERE user_id=?", (user_id,))
        return await cursor.fetchall()


async def get_all_tracks():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, item, last_count, last_min FROM tracks")
        return await cursor.fetchall()


async def update_cache(user_id: int, item: str, count: int, min_price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        UPDATE tracks
        SET last_count=?, last_min=?
        WHERE user_id=? AND item=?
        """, (count, min_price, user_id, item))
        await db.commit()


# ============ API ============
async def get_marketplace_items(server_id: str = None):
    if not server_id:
        server_id = SERVER

    url = f"{BASE_URL}/v1/ext/marketplace/items/{server_id}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.json()


async def search_item(item_name: str, server_id: str = None):
    try:
        data = await get_marketplace_items(server_id)
    except Exception as e:
        logger.error(f"API Error: {e}")
        return None

    if "itemStatistics" not in data:
        return None

    results = []
    item_lower = item_name.lower()

    for item in data["itemStatistics"]:
        if item_lower in item["itemName"].lower():
            results.append({
                "id": item["itemId"],
                "name": item["itemName"],
                "count": item["totalCount"],
                "sold": item["soldCount"],
                "avg_price": item["averagePrice"],
                "min_price": item["minPrice"],
                "max_price": item["maxPrice"]
            })

    return results


# ============ МОНИТОРИНГ ============
async def check_updates(bot: Bot):
    tracks = await get_all_tracks()

    if not tracks:
        return

    logger.info(f"Проверка обновлений для {len(tracks)} предметов")

    for user_id, item_name, last_count, last_min in tracks:
        try:
            server = await get_user_server(user_id)
            results = await search_item(item_name, server)

            if not results:
                continue

            current = results[0]
            current_count = current["count"]
            current_min = current["min_price"]

            changes = []

            if current_count != last_count:
                if current_count > last_count:
                    changes.append(f"📦 Новых объявлений: +{current_count - last_count} (было {last_count}, стало {current_count})")
                else:
                    changes.append(f"📦 Объявлений стало меньше: -{last_count - current_count} (было {last_count}, стало {current_count})")

            if current_min != last_min:
                if current_min < last_min:
                    changes.append(f"💰 Цена снизилась: {last_min:,}$ → {current_min:,}$")
                else:
                    changes.append(f"💰 Цена выросла: {last_min:,}$ → {current_min:,}$")

            if changes:
                changes_text = "\n".join(changes)
                await bot.send_message(
                    user_id,
                    f"🔔 Изменение предмета '{item_name}' (сервер {server}):\n\n"
                    f"{changes_text}\n\n"
                    f"📊 Текущая статистика:\n"
                    f"📦 В продаже: {current_count}\n"
                    f"💰 Средняя цена: {current['avg_price']:,}$\n"
                    f"⬇ Мин: {current_min:,}$\n"
                    f"⬆ Макс: {current['max_price']:,}$\n"
                    f"📊 Продано: {current['sold']}"
                )

                await update_cache(user_id, item_name, current_count, current_min)

        except Exception as e:
            logger.error(f"Ошибка при проверке {item_name} для {user_id}: {e}")
            continue


async def start_checker(bot: Bot):
    logger.info("Запуск мониторинга...")
    while True:
        try:
            await check_updates(bot)
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}")
        await asyncio.sleep(30)


# ============ ОБРАБОТЧИКИ КОМАНД ============
async def cmd_start(message: Message):
    await add_user(message.from_user.id)
    await message.answer(
        "👋 Привет! Я бот для отслеживания предметов на маркетплейсе Majestic RP.\n\n"
        "📌 Доступные команды:\n"
        "/check <название> — проверить наличие предмета\n"
        "/track <название> — начать отслеживать предмет\n"
        "/untrack <название> — перестать отслеживать\n"
        "/list — список отслеживаемых предметов\n"
        "/all — показать все предметы на сервере\n"
        "/servers — показать доступные серверы\n"
        "/set <сервер> — выбрать сервер (например /set RU1)\n"
        "/help — помощь"
    )


async def cmd_help(message: Message):
    await message.answer(
        "📖 Помощь по командам:\n\n"
        "/check <название> — поиск предмета\n"
        "Пример: /check ID card\n\n"
        "/track <название> — добавить в отслеживание\n"
        "Пример: /track AK-47\n\n"
        "/untrack <название> — удалить из отслеживания\n"
        "Пример: /untrack AK-47\n\n"
        "/list — показать отслеживаемые предметы\n"
        "/all — показать все предметы на сервере\n"
        "/servers — показать доступные серверы\n"
        "/set <сервер> — выбрать сервер\n"
        "Пример: /set RU1"
    )


async def cmd_servers(message: Message):
    """Команда /servers - показать доступные серверы"""
    await message.answer(
        "🌍 Доступные серверы:\n\n"
        "• RU1 — основной сервер\n"
        "• RU2\n"
        "• RU3\n"
        "• RU4\n"
        "• RU5\n"
        "• EU1 — европейский\n"
        "• EU2\n\n"
        "Выбери сервер командой /set <сервер>\n"
        "Пример: /set RU1"
    )


async def cmd_set(message: Message):
    """Команда /set - выбрать сервер"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажите сервер.\nПример: /set RU1")
        return
    
    server = args[1].strip().upper()
    
    # Проверяем, существует ли сервер
    try:
        await get_marketplace_items(server)
        await set_user_server(message.from_user.id, server)
        await message.answer(f"✅ Сервер изменен на {server}")
    except Exception as e:
        await message.answer(f"❌ Сервер {server} не найден или недоступен.\nИспользуй /servers для списка.")


async def cmd_all(message: Message):
    """Команда /all - показать все предметы на сервере"""
    user_id = message.from_user.id
    await add_user(user_id)
    
    server = await get_user_server(user_id)
    
    await message.answer(f"🔍 Загружаю список всех предметов на сервере {server}...")
    
    try:
        data = await get_marketplace_items(server)
        
        if "itemStatistics" not in data or not data["itemStatistics"]:
            await message.answer(f"❌ На сервере {server} нет предметов или ошибка загрузки.")
            return
        
        items = sorted(data["itemStatistics"], key=lambda x: x["itemName"])
        
        answer = f"📋 Все предметы на сервере {server} (всего: {len(items)}):\n\n"
        
        for i, item in enumerate(items[:50], 1):
            answer += f"{i}. {item['itemName']} — {item['totalCount']} шт., от {item['minPrice']:,}$\n"
        
        if len(items) > 50:
            answer += f"\n... и еще {len(items) - 50} предметов"
        
        await message.answer(answer)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка загрузки с сервера {server}: {e}")


async def cmd_check(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("❌ Укажите название предмета.\nПример: /check ID card")
        return

    user_id = message.from_user.id
    item_name = args[1].strip()
    server = await get_user_server(user_id)

    await message.answer(f"🔍 Ищу '{item_name}' на сервере {server}...")

    results = await search_item(item_name, server)

    if not results:
        await message.answer(f"❌ Предмет '{item_name}' не найден на сервере {server}.")
        return

    answer = f"🔎 Найдено {len(results)} предметов на сервере {server}:\n\n"

    for i, item in enumerate(results[:10], 1):
        answer += (
            f"{i}. {item['name']}\n"
            f"   📦 В продаже: {item['count']}\n"
            f"   💰 Средняя: {item['avg_price']:,}$\n"
            f"   ⬇ Мин: {item['min_price']:,}$\n"
            f"   ⬆ Макс: {item['max_price']:,}$\n"
            f"   📊 Продано: {item['sold']}\n\n"
        )

    if len(results) > 10:
        answer += f"... и еще {len(results) - 10} предметов"

    await message.answer(answer)


async def cmd_track(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("❌ Укажите название предмета.\nПример: /track ID card")
        return

    user_id = message.from_user.id
    item_name = args[1].strip()
    server = await get_user_server(user_id)

    await add_user(user_id)

    results = await search_item(item_name, server)

    if not results:
        await message.answer(f"❌ Предмет '{item_name}' не найден на сервере {server}.")
        return

    tracks = await get_tracks(user_id)
    track_list = [t[0].lower() for t in tracks]

    if item_name.lower() in track_list:
        await message.answer(f"ℹ️ Предмет '{item_name}' уже отслеживается на сервере {server}.")
        return

    first_result = results[0]

    await add_track(user_id, item_name)

    await update_cache(
        user_id,
        item_name,
        first_result["count"],
        first_result["min_price"]
    )

    await message.answer(
        f"✅ Предмет '{item_name}' добавлен в отслеживание на сервере {server}!\n\n"
        f"📦 В продаже: {first_result['count']}\n"
        f"💰 Мин. цена: {first_result['min_price']:,}$\n\n"
        "Я буду уведомлять тебя об изменениях."
    )


async def cmd_untrack(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("❌ Укажите название предмета.\nПример: /untrack ID card")
        return

    user_id = message.from_user.id
    item_name = args[1].strip()

    tracks = await get_tracks(user_id)
    track_list = [t[0].lower() for t in tracks]

    if item_name.lower() not in track_list:
        await message.answer(f"❌ Предмет '{item_name}' не отслеживается.")
        return

    await remove_track(user_id, item_name)

    await message.answer(f"✅ Предмет '{item_name}' удален из отслеживания.")


async def cmd_list(message: Message):
    user_id = message.from_user.id
    tracks = await get_tracks(user_id)
    server = await get_user_server(user_id)

    if not tracks:
        await message.answer("📭 Вы не отслеживаете ни одного предмета.")
        return

    answer = f"📋 Ваши отслеживаемые предметы (сервер {server}):\n\n"
    for i, (item,) in enumerate(tracks, 1):
        answer += f"{i}. {item}\n"

    await message.answer(answer)


# ============ ГЛАВНАЯ ФУНКЦИЯ ============
async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_servers, Command("servers"))
    dp.message.register(cmd_set, Command("set"))
    dp.message.register(cmd_all, Command("all"))
    dp.message.register(cmd_check, Command("check"))
    dp.message.register(cmd_track, Command("track"))
    dp.message.register(cmd_untrack, Command("untrack"))
    dp.message.register(cmd_list, Command("list"))

    logger.info("Бот запущен!")

    asyncio.create_task(start_checker(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())