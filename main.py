import os
import openpyxl
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler,
                          CallbackQueryHandler, ContextTypes)
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder
from telegram.ext import MessageHandler, filters
import asyncio

# ==================== GLOBAL =====================
players = {}
games = {}
win_stats = {}
ADMIN_IDS = [5429428390, 5930936939]


# ============== SAVE TO EXCEL ==============
async def save_player_to_excel(name, username, join_time):
    path = "data/players.xlsx"
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Tên", "Username", "Thời gian tham gia"])
    else:
        wb = openpyxl.load_workbook(path)
        ws = wb.active
    for row in ws.iter_rows(min_row=2):
        if row[0].value == name and row[1].value == username:
            return
    ws.append([
        name, f"@{username}" if username else "",
        join_time.strftime("%d-%m-%Y %H:%M:%S")
    ])
    wb.save(path)


# ============== BÀN CỜ ==============
def create_board_keyboard(board):
    keyboard = []
    for y, row in enumerate(board):
        line = [
            InlineKeyboardButton(text=cell, callback_data=f"{x},{y}")
            for x, cell in enumerate(row)
        ]
        keyboard.append(line)
    return InlineKeyboardMarkup(keyboard)


async def update_board_message(context, chat_id):
    game = games[chat_id]
    board = game["board"]
    current_player = game["players"][game["turn"]]
    username = f"@{current_player.username}" if current_player.username else current_player.first_name

    markup = create_board_keyboard(board)
    await context.bot.edit_message_text(chat_id=chat_id,
                                        message_id=game["message_id"],
                                        text=f"Đến lượt: {username}",
                                        reply_markup=markup)

    if game.get("task"):
        game["task"].cancel()
    game["task"] = asyncio.create_task(turn_timeout(context, chat_id))


# ============== KIỂM TRA THẮNG ==============
def check_win(board, symbol):
    size = len(board)
    for y in range(size):
        for x in range(size - 3):
            if all(board[y][x + i] == symbol for i in range(4)):
                return True
    for x in range(size):
        for y in range(size - 3):
            if all(board[y + i][x] == symbol for i in range(4)):
                return True
    for y in range(size - 3):
        for x in range(size - 3):
            if all(board[y + i][x + i] == symbol for i in range(4)):
                return True
    for y in range(size - 3):
        for x in range(3, size):
            if all(board[y + i][x - i] == symbol for i in range(4)):
                return True
    return False


# ============== TIMEOUT ==============
async def turn_timeout(context, chat_id):
    await asyncio.sleep(60)
    game = games.get(chat_id)
    if not game:
        return
    loser = game["players"][game["turn"]]
    winner = game["players"][1 - game["turn"]]
    uid = winner.id
    win_stats[uid] = win_stats.get(uid, 0) + 1
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏱ {loser.first_name} Hết thời gian!\n"
        f"👑{winner.first_name} Chiến thắng.\n"
        f"📊Tổng: {win_stats[uid]} Lần")
    games.pop(chat_id, None)
    players.pop(chat_id, None)
    await context.bot.send_message(chat_id=chat_id,
                                   text="Gõ /startgame để tiếp tục.")


# ============== COMMAND HANDLERS ==============
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        await update.message.reply_text(
            "⚠️ Trò chơi đang diễn ra. Dùng /reset để bắt đầu lại!")
        return
    games[chat_id] = {
        "board": [["▫️"] * 10 for _ in range(10)],
        "players": [],
        "turn": 0,
        "task": None,
        "message_id": None,
        "bot_play": False
    }
    players[chat_id] = []
    await update.message.reply_text(
        "🎮 Trò chơi bắt đầu!\n"
        "👉 Gõ \u2003/join \u2003 Để tham gia.\n"
        "👉 Gõ \u2003/joinbot\u2003Tham gia với bót.")


async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games:
        await update.message.reply_text(
            "⚠️ Hãy dùng /startgame để bắt đầu trước.")
        return
    if user.id not in players[chat_id]:
        players[chat_id].append(user.id)
        games[chat_id]["players"].append(user)
        await update.message.reply_text(f"✅ {user.first_name} đã tham gia!")
        await save_player_to_excel(user.full_name, user.username,
                                   datetime.now())

        if len(games[chat_id]["players"]) == 2:
            current_player = games[chat_id]["players"][0]
            username = f"@{current_player.username}" if current_player.username else current_player.first_name
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"Đến lượt: {username}",
                reply_markup=create_board_keyboard(games[chat_id]["board"]))
            games[chat_id]["message_id"] = msg.message_id
            games[chat_id]["task"] = asyncio.create_task(
                turn_timeout(context, chat_id))


async def join_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games:
        await update.message.reply_text(
            "⚠️ Hãy dùng /startgame để bắt đầu trước.")
        return
    if user.id not in players[chat_id]:
        players[chat_id].append(user.id)
        games[chat_id]["players"].append(user)
        games[chat_id]["players"].append("bot")
        games[chat_id]["bot_play"] = True
        await update.message.reply_text(f"✅ {user.first_name} chơi với bot!")
        await save_player_to_excel(user.full_name, user.username,
                                   datetime.now())

        current_player = games[chat_id]["players"][0]
        username = f"@{current_player.username}" if current_player != "bot" and current_player.username else current_player.first_name
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Đến lượt: {username}",
            reply_markup=create_board_keyboard(games[chat_id]["board"]))
        games[chat_id]["message_id"] = msg.message_id
        games[chat_id]["task"] = asyncio.create_task(
            turn_timeout(context, chat_id))


async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        if games[chat_id].get("task"):
            games[chat_id]["task"].cancel()
        games.pop(chat_id)
        players.pop(chat_id, None)
    await update.message.reply_text("🔄 Game đã được làm mới.")


async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = "data/players.xlsx"
    if os.path.exists(path):
        await update.message.reply_document(open(path, "rb"))
    else:
        await update.message.reply_text("⚠️ Chưa có ai tham.")


async def delete_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = "data/players.xlsx"
    if os.path.exists(path):
        os.remove(path)
        await update.message.reply_text("🗑️ File Excel đã bị xóa.")
    else:
        await update.message.reply_text("⚠️ Không có file nào.")


async def show_win_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    if user.id in ADMIN_IDS:
        if not win_stats:
            await update.message.reply_text("📊 Chưa có ai thắng trận nào.")
            return
        msg = "🏆 Thống kê tổng hợp toàn bộ người thắng:\n"
        for user_id, count in win_stats.items():
            try:
                user_obj = await context.bot.get_chat_member(chat_id, user_id)
                name = user_obj.user.full_name
                msg += f"- {name} (ID {user_id}): {count} lần\n"
            except:
                msg += f"- ID {user_id}: {count} lần\n"
        await update.message.reply_text(msg)
    else:
        result = {}
        for uid, count in win_stats.items():
            try:
                member = await context.bot.get_chat_member(chat_id, uid)
                if member.status in ("member", "administrator", "creator"):
                    result[uid] = count
            except:
                pass

        if not result:
            await update.message.reply_text(
                "📊 Nhóm này chưa có ai thắng trận nào.")
            return

        msg = f"🏆 BẢNG XẾP HẠNG 🏆:\n"
        for uid, count in result.items():
            try:
                member = await context.bot.get_chat_member(chat_id, uid)
                name = member.user.full_name
                msg += f"- {name}: {count} lần\n"
            except:
                msg += f"- ID {uid}: {count} lần\n"
        await update.message.reply_text(msg)


async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 Hướng dẫn:\n\n"
        "🔹/startgame - Bắt đầu game mới.\n"
        "🔹/join - Tham gia game.\n"
        "🔹/joinbot - Tham gia chơi với bot.\n"
        "🔹/reset - Làm mới game nhóm này.\n"
        "🔹/win - Xem thống kê thắng.\n"
        "🔹/hep - Xem hướng dẫn.\n"
        "📌 LUẬT CHƠI:\n\n"
        "-Khi 2 người tham gia hoặc tự chơi với bót, đủ người bàn cờ tự hiện lên.\n"
        "👉 @xukaxuka2k1 codefree,fastandsecure👈")


# ============== XỬ LÝ NÚT NHẤN ==============
async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user = query.from_user
    if chat_id not in games:
        return
    game = games[chat_id]
    if game["players"][game["turn"]] != user and game["players"][
            game["turn"]] != "bot":
        await query.message.reply_text("⛔ Không đến lượt bạn!")
        return
    x, y = map(int, query.data.split(","))
    if game["board"][y][x] != "▫️":
        await query.message.reply_text("❗ Ô này đã có người đánh!")
        return
    symbol = "❌" if game["turn"] == 0 else "⭕"
    game["board"][y][x] = symbol

    if game.get("task"):
        game["task"].cancel()

    if check_win(game["board"], symbol):
        winner = game["players"][game["turn"]]
        if winner != "bot":
            uid = winner.id
            win_stats[uid] = win_stats.get(uid, 0) + 1
            name = winner.first_name
        else:
            name = "Bot"
        await query.message.reply_text(f"🏆 {name} Chiến thắng\n"
                                       f"📊Tổng: {win_stats.get(uid, 0)} Lần")
        games.pop(chat_id, None)
        players.pop(chat_id, None)
        await query.message.reply_text("Gõ /startgame để tiếp tục.")
        return

    game["turn"] = 1 - game["turn"]

    if game["bot_play"] and game["players"][game["turn"]] == "bot":
        await asyncio.sleep(1)
        for j in range(size):
            for i in range(size):
                if game["board"][j][i] == "▫️":
                    game["board"][j][i] = "⭕"
                    if check_win(game["board"], "⭕"):
                        await query.message.reply_text("🤖 Bot Chiến thắng!")
                        games.pop(chat_id, None)
                        players.pop(chat_id, None)
                        await query.message.reply_text(
                            "Gõ /startgame để tiếp tục.")
                        return
                    game["turn"] = 0
                    await update_board_message(context, chat_id)
                    return
    await update_board_message(context, chat_id)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Lệnh không hợp lệ. Gõ /help để xem lệnh.")


# ============== MAIN ==========================
app = ApplicationBuilder().token(TOKEN).build()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("startgame", start_game))
app.add_handler(CommandHandler("join", join_game))
app.add_handler(CommandHandler("joinbot", join_bot))
app.add_handler(CommandHandler("reset", reset_game))
app.add_handler(CommandHandler("fast", export_data))
app.add_handler(CommandHandler("secure", delete_export))
app.add_handler(CommandHandler("win", show_win_stats))
app.add_handler(CommandHandler("hep", show_rules))
app.add_handler(CallbackQueryHandler(handle_move))
app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
app.run_polling()
