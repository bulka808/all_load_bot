import telebot
from telebot import types
#####
import json
#####
from typing import Callable
#####
import asyncio
import aiohttp
#####
import io
import zipfile
# import requests
# import shutil
# import os


# загрузка cfg, пока что только токен
with open("config.json", "r", encoding="UTF-8") as f:
    cfg = json.load(f)
bot = telebot.TeleBot(cfg["TOKEN"])

# загрузка команд
with open("commands.json", "r", encoding="UTF-8") as f:
    commands: dict[str, str] = json.load(f)

list_commands = [types.BotCommand(command=cmd, description=desc) for cmd, desc in commands.items()]
bot.set_my_commands(list_commands)
print("Команды загружены из commands.json")

# функции получения file_id
funcs: dict[str, Callable[[types.Message], str]] = {
    "photo": lambda m: m.photo[-1].file_id,
    "animation": lambda m: m.animation.file_id,
    "video": lambda m: m.video.file_id,
    "document": lambda m: m.document.file_id
}
# словарь со всеми file_id каждого пользователя
files: dict[int, list[dict[str, str]]] = {}


# функция с приветствием и краткой справкой
@bot.message_handler(commands=["start"])
def start(message: types.Message) -> None:

    uid = message.from_user.id
    print(f"{uid}\tstart\n")

    msg_text = "Для начала работы просто отправьте нужные файлы боту," \
    " после чего удостоверьтесь что все из них загружены с помощью /stat\n\n" \
    "Для выгрузки всех файлов в виде zip-архива используйте /load"

    bot.reply_to(message=message, text=msg_text)
    

# основная функция приёма сообщений
@bot.message_handler(content_types=["photo", "video", "document", "animation", ])
def files_get(message: types.Message) -> None:

    uid = message.from_user.id
    print(f"{uid}\t{message.content_type}\n")

    file = funcs[message.content_type](message)
    
    # если uid еще нет в словаре, добавляем uid c пустым списком
    if(uid not in files): files[uid] = []
    # если файла с таким id нет то добавляем в список
    if(file not in files[uid]): 
        path = bot.get_file(file).file_path
        ext = path.split(".")[-1]
        obj = {
            "file_id": file,  # file id
            "path": path,  # путь на сервере у тг
            "ext": ext  # расширение
        }
        files[uid].append(obj)
    

@bot.message_handler(commands= ['load'])
def load(message: types.Message) -> None:
    # тут будет загрузка ВСЕХ файлов
    global files
    
    uid = message.from_user.id
    print(f"{uid}\tload\n")

    if(uid not in files): files[uid] = []

    # Запуск асинхронной задачи
    if(len(files[uid]) <= 0):
        bot.reply_to(message=message, text=f"У вас загружено 0 файлов")
        return

    asyncio.run(handle_files_async(message, files[uid]))

async def handle_files_async(message: types.Message, user_files):
    #временное сообщение чтобы пользователь видел что бот жив
    wait_msg = bot.reply_to(message=message, text="Идет загрузка...")

    # Асинхронный контекст для HTTP-запросов
    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, file_info in enumerate(user_files):
            task = download_file(session, file_info, idx)
            tasks.append(task)

        print("Запускаем скачивание всех файлов...")
        downloaded_files = await asyncio.gather(*tasks)
        print("Все файлы скачаны.")

        # Создаем ZIP-архив
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as zipf:
            for idx, (filename, content) in enumerate(downloaded_files):
                zipf.writestr(filename, content)

        # Отправляем архив пользователю
        bot.send_document(
            chat_id=message.chat.id,
            document=stream.getvalue(),
            caption="Вот ваши файлы.",
            reply_to_message_id=message.id,
            visible_file_name=f"{message.from_user.id}.zip"
        )
        # удаляем временное сообщение
        bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.id)

async def download_file(session, file_info, idx):
    file_id = file_info["file_id"]
    path = file_info["path"]
    ext = file_info["ext"]

    url = f"https://api.telegram.org/file/bot{cfg['TOKEN']}/{path}"

    print(f"Скачиваю {file_id}.{ext}")
    async with session.get(url) as resp:
        if resp.status == 200:
            data = await resp.read()
            return (f"file_{idx}.{ext}", data)
        else:
            print(f"Ошибка при скачивании файла {file_id}: статус {resp.status}")
            return (f"file_{idx}.{ext}", b"")


# очистка загруженных файлов пользователя
@bot.message_handler(commands= ['reset'])
def reset(message: types.Message) -> None:
    uid = message.from_user.id
    print(f"{uid}\treset\n")

    # если uid есть то очищаем то что было внутри
    if(uid in files): files[uid].clear()

    bot.reply_to(message=message, text="Файлы очищены.")


# вывод количества загруженных файлов
@bot.message_handler(commands=["stat"])
def stat(message: types.Message) -> None:
    uid = message.from_user.id
    print(f"{uid}\tstat\n")

    if(uid not in files): files[uid] = []

    bot.reply_to(message=message, text=f"Загружено {len(files[uid])} файлов")


print(f"start: \"{bot.get_me().full_name}\"")
bot.infinity_polling()
