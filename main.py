import os  # ok ok tới lượt người chơi với bót rõ ràng
import openpyxl
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler,
                          CallbackQueryHandler, ContextTypes)
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder
from telegram.ext import MessageHandler, filters
from stay_alive import keep_alive
import asyncio
import numpy as np
import threading
import math


keep_alive()
# ==================== GLOBAL =====================
players = {}
games = {}
win_stats = {}
ADMIN_IDS = [5429428390, 5930936939]


def score_line(line, symbol):
    score = 0
    line_str = ''.join(line)
    opp = "⭕" if symbol == "❌" else "❌"

    if f"{symbol*4}" in line_str:
        score += 10000
    elif f"{symbol*3}▫️" in line_str or f"▫️{symbol*3}" in line_str:
        score += 5000
    elif f"{symbol*2}▫️{symbol}" in line_str or f"{symbol}▫️{symbol*2}" in line_str:
        score += 3000
    elif f"▫️{symbol*2}▫️" in line_str:
        score += 2000
    elif f"{symbol*2}" in line_str:
        score += 1000

    if f"{opp*3}▫️" in line_str or f"▫️{opp*3}" in line_str:
        score -= 6000
    elif f"▫️{opp*2}▫️" in line_str:
        score -= 8000
    elif f"{opp*2}▫️{opp}" in line_str or f"{opp}▫️{opp*2}" in line_str:
        score -= 3000
    elif f"{opp*2}" in line_str:
        score -= 1000

    return score


# Hàm đánh giá tổng thể bàn cờ
def evaluate_board(board_np, symbol):
    score = 0
    for row in board_np:
        score += score_line(row, symbol)
    for col in board_np.T:
        score += score_line(col, symbol)
    for i in range(-board_np.shape[0] + 1, board_np.shape[1]):
        score += score_line(np.diag(board_np, k=i), symbol)
        score += score_line(np.diag(np.fliplr(board_np), k=i), symbol)

    center_positions = [(3, 4), (4, 3), (3, 3), (4, 4)]
    for x, y in center_positions:
        if board_np[y][x] == symbol:
            score += 300

    return score


def get_possible_moves(board_np):
    moves = set()
    for y in range(board_np.shape[0]):
        for x in range(board_np.shape[1]):
            if board_np[y][x] != "▫️":
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < board_np.shape[
                                0] and 0 <= nx < board_np.shape[1]:
                            if board_np[ny][nx] == "▫️":
                                moves.add((nx, ny))
    return list(moves)


# Thuật toán Minimax với Alpha-Beta Pruning
def minimax(board_np, depth, alpha, beta, is_maximizing, symbol, opp):
    score = evaluate_board(board_np, symbol)
    if depth == 0 or abs(score) >= 10000:
        return score, None

    best = None
    moves = get_possible_moves(board_np)
    if not moves:
        return 0, None

    if is_maximizing:
        max_eval = -math.inf
        for x, y in moves:
            board_np[y][x] = symbol
            eval, _ = minimax(board_np, depth - 1, alpha, beta, False, symbol,
                              opp)
            board_np[y][x] = "▫️"
            if eval > max_eval:
                max_eval = eval
                best = (x, y)
            alpha = max(alpha, eval)
            if beta <= alpha:
                break
        return max_eval, best
    else:
        min_eval = math.inf
        for x, y in moves:
            board_np[y][x] = opp
            eval, _ = minimax(board_np, depth - 1, alpha, beta, True, symbol,
                              opp)
            board_np[y][x] = "▫️"
            if eval < min_eval:
                min_eval = eval
                best = (x, y)
            beta = min(beta, eval)
            if beta <= alpha:
                break
        return min_eval, best


# Hàm tính toán nước đi tốt nhất của bot
def best_move(board, symbol, depth=4):
    board_np = np.array(board)
    opp = "⭕" if symbol == "❌" else "❌"

    for x, y in get_possible_moves(board_np):
        board_np[y][x] = symbol
        if check_win(board_np.tolist(), symbol):
            board_np[y][x] = "▫️"
            return (x, y)
        board_np[y][x] = "▫️"

    for x, y in get_possible_moves(board_np):
        board_np[y][x] = opp
        if check_win(board_np.tolist(), opp):
            board_np[y][x] = "▫️"
            return (x, y)
        board_np[y][x] = "▫️"

    # 🔒 CHẶN ▫️❌❌▫️ hoặc ▫️⭕⭕▫️
    for y in range(board_np.shape[0]):
        for x in range(board_np.shape[1]):
            for dx, dy in [(1, 0), (0, 1), (1, 1), (-1, 1)]:
                try:
                    cells = [(x + i * dx, y + i * dy) for i in range(4)]
                    values = [board_np[yy][xx] for xx, yy in cells]
                    if values == ["▫️", opp, opp, "▫️"]:
                        if board_np[cells[0][1]][cells[0][0]] == "▫️":
                            return cells[0]
                        if board_np[cells[3][1]][cells[3][0]] == "▫️":
                            return cells[3]
                except IndexError:
                    continue

    _, move = minimax(board_np, depth, -math.inf, math.inf, True, symbol, opp)
    return move


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

    # Kiểm tra trùng dựa vào tên và username
    for row in ws.iter_rows(min_row=2):
        existing_name = str(row[0].value)
        existing_username = str(row[1].value)
        if existing_name == name and existing_username == (f"@{username}" if
                                                           username else ""):
            return  # Đã tồn tại, không ghi nữa

    # Ghi người mới
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


async def update_board_message(context, chat_id, show_turn=True):
    game = games.get(chat_id)
    if not game:
        return

    board = game["board"]
    markup = create_board_keyboard(board)

    if show_turn:
        current_player = game["players"][
            game["turn"]]  # Sửa từ "ccurrent_player" thành "current_player"
        symbol = "❌" if game[
            "turn"] == 0 else "⭕"  # Cách xác định symbol đơn giản hơn

        if current_player == "bot":
            message = f"🤖 Đến lượt Bot ({symbol})"
        else:
            username = f"@{current_player.username}" if current_player.username else current_player.first_name
            message = f"👤 Đến lượt {username} ({symbol})"
    else:
        message = "🎯 Trận đấu kết thúc!"

    try:
        await context.bot.edit_message_text(chat_id=chat_id,
                                            message_id=game["message_id"],
                                            text=message,
                                            reply_markup=markup)
    except:
        pass

    if game.get("task"):
        game["task"].cancel()

    if show_turn:
        game["task"] = asyncio.create_task(turn_timeout(context, chat_id))


# ============== KIỂM TRA THẮNG ==============
def check_win(board, symbol):
    size_y = len(board)
    size_x = len(board[0])

    # Kiểm tra ngang
    for y in range(size_y):
        for x in range(size_x - 3):
            if all(board[y][x + i] == symbol for i in range(4)):
                return True

    # Kiểm tra dọc
    for x in range(size_x):
        for y in range(size_y - 3):
            if all(board[y + i][x] == symbol for i in range(4)):
                return True

    # Kiểm tra chéo chính
    for y in range(size_y - 3):
        for x in range(size_x - 3):
            if all(board[y + i][x + i] == symbol for i in range(4)):
                return True

    # Kiểm tra chéo phụ
    for y in range(size_y - 3):
        for x in range(3, size_x):
            if all(board[y + i][x - i] == symbol for i in range(4)):
                return True

    return False


# ============== TIMEOUT ==============
async def turn_timeout(context, chat_id):
    await asyncio.sleep(60)

    game = games.get(chat_id)
    if not game or len(game["players"]) < 2:
        return

    # Dừng task cũ nếu còn
    if game.get("task"):
        game["task"].cancel()

    loser_index = game["turn"]
    winner_index = 1 - loser_index

    loser = game["players"][loser_index]
    winner = game["players"][winner_index]

    loser_name = "Bot" if loser == "bot" else loser.full_name
    winner_name = "Bot" if winner == "bot" else winner.full_name
    winner_id = 0 if winner == "bot" else winner.id

    # Cập nhật thống kê
    if winner_id not in win_stats:
        win_stats[winner_id] = {"name": winner_name, "count": 1}
    else:
        win_stats[winner_id]["count"] += 1

    # Hiện bàn cờ kết thúc
    markup = create_board_keyboard(game["board"])
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game["message_id"],
            text="🎯 Trận đấu kết thúc do hết giờ!",
            reply_markup=markup)
    except:
        pass

    # Thông báo người thắng
    await context.bot.send_message(chat_id=chat_id,
                                   text=f"⏱ {loser_name} Hết thời gian!\n"
                                   f"🏆 CHIẾN THẮNG! 🏆\n"
                                   f"👑 {winner_name}\n"
                                   f"📊 Thắng: {win_stats[winner_id]['count']}")

    # Xoá game để chơi mới
    games.pop(chat_id, None)
    players.pop(chat_id, None)

    # Gợi ý chơi tiếp
    await context.bot.send_message(chat_id=chat_id,
                                   text="👉 Gõ /startgame Bắt đầu ván mới..")


# ============== COMMAND HANDLERS ==============
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        game = games[chat_id]
        # Nếu đã có đủ 2 người hoặc 1 người + bot thì báo đang chơi
        if len(game["players"]) == 2 or (len(game["players"]) == 1
                                         and game.get("bot_play")):
            await context.bot.send_message(chat_id=chat_id,
                                           text="⚠️ Trò chơi đang diễn ra.")
            return
    # Nếu chưa đủ người thì vẫn cho phép /startgame (reset dữ liệu cũ)
    games[chat_id] = {
        "board": [["▫️"] * 8 for _ in range(10)],
        "players": [],
        "turn": 0,
        "task": None,
        "message_id": None,
        "bot_play": False
    }
    players[chat_id] = []
    await context.bot.send_message(chat_id=chat_id,
                                   text="🎮 Trò chơi bắt đầu!\n"
                                   "👉 Gõ /join   Để tham gia.\n"
                                   "👉 Gõ /joinbot  Tham gia với bót.")


async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games:
        await context.bot.send_message(chat_id=chat_id,
                                       text="👉 Gõ /startgame Bắt đầu ván mới.")
        return
    if user.id not in players[chat_id]:
        players[chat_id].append(user.id)
        games[chat_id]["players"].append(user)
        await context.bot.send_message(
            chat_id=chat_id, text=f"✅ {user.first_name} Đã tham gia!")
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
        await context.bot.send_message(chat_id=chat_id,
                                       text="👉 Gõ /startgame Bắt đầu ván mới.")
        return
    if user.id not in players[chat_id]:
        players[chat_id].append(user.id)
        games[chat_id]["players"].append(user)
        games[chat_id]["players"].append("bot")
        games[chat_id]["bot_play"] = True
        await context.bot.send_message(
            chat_id=chat_id, text=f"✅ {user.first_name} chơi với bot!")
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
    user_id = update.effective_user.id
    path = "data/players.xlsx"

    if user_id in ADMIN_IDS:
        # ADMIN reset: 
        try:
            if os.path.exists(path):
                os.remove(path)
            win_stats.clear()
            await context.bot.send_message(chat_id=chat_id,
                                           text="🛑 Đã reset toàn bộ.")
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id,
                                           text=f"❌ Lỗi khi reset: {str(e)}")
        return

    # Reset thông thường
    try:
        if chat_id in games:
            if games[chat_id].get("task"):
                games[chat_id]["task"].cancel()
            games.pop(chat_id, None)
            players.pop(chat_id, None)

        # Xóa thống kê trong nhóm
        to_delete = [uid for uid in win_stats
                     if uid != 0]  
        for uid in to_delete:
            try:
                member = await context.bot.get_chat_member(chat_id, uid)
                if member.status in ("member", "administrator", "creator"):
                    win_stats.pop(uid, None)
            except:
                continue

        await context.bot.send_message(chat_id=chat_id,
                                       text="♻️ Đã reset game và thống kê!")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id,
                                       text=f"❌ Lỗi khi reset: {str(e)}")


async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    path = "data/players.xlsx"

    try:
        if not os.path.exists(path):
            await context.bot.send_message(chat_id=chat_id,
                                           text="⚠️ Chưa có dữ liệu.")
            return

        with open(path, "rb") as file:
            await context.bot.send_document(chat_id=chat_id,
                                            document=file,
                                            filename="players_data.xlsx",
                                            caption="📊 Dữ liệu người chơi")
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat_id, text=f"❌ Lỗi khi xuất dữ liệu: {str(e)}")


async def delete_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    path = "data/players.xlsx"

    try:
        if not os.path.exists(path):
            await context.bot.send_message(chat_id=chat_id,
                                           text="⚠️ Không tìm thấy file.")
            return

        os.remove(path)
        await context.bot.send_message(chat_id=chat_id,
                                       text="🗑️ Đã xóa file thành công!")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id,
                                       text=f"❌ Lỗi khi xóa file: {str(e)}")


async def show_win_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    if user.id in ADMIN_IDS:
        if not win_stats:
            await context.bot.send_message(chat_id=chat_id,
                                           text="📊 Chưa có ai thắng.")
            return

        msg = f"🏆 THỐNG KÊ TOÀN BỘ\n📍Group ID: {chat_id}\n\n"
        for uid, data in win_stats.items():
            name = data["name"]
            count = data["count"]
            msg += f"👤 {name}: {count} Ván\n"
        await context.bot.send_message(chat_id=chat_id, text=msg)

    else:
        result = {}
        for uid, data in win_stats.items():
            try:
                member = await context.bot.get_chat_member(chat_id, uid)
                if member.status in ("member", "administrator", "creator"):
                    result[uid] = data
            except:
                pass

        if not result:
            await context.bot.send_message(chat_id=chat_id,
                                           text="📊 Nhóm chưa có ai thắng.")
            return

        msg = f"🏆 BẢNG XẾP HẠNG 🏆:\n"
        for uid, data in result.items():
            name = data["name"]
            count = data["count"]
            msg += f"{name}: {count} Ván\n"
        await context.bot.send_message(chat_id=chat_id, text=msg)


async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="📘 Hướng dẫn:\n\n"
        "🔹/startgame - Bắt đầu game mới.\n"
        "🔹/join - Tham gia game.\n"
        "🔹/joinbot - Tham gia chơi với bot.\n"
        "🔹/reset - Làm mới game nhóm này.\n"
        "🔹/win - Xem thống kê thắng.\n"
        "🔹/help - Xem hướng dẫn.\n\n"
        "📌 LUẬT CHƠI:\n\n"
        "- Khi 2 người tham gia hoặc tự chơi với bót, đủ người bàn tự hiện lên.\n"
        "- 4 điểm thẳng hàng giành chiến .\n"
        "👉 @xukaxuka2k1 codefree,fastandsecure👈")


# ============== XỬ LÝ NÚT NHẤN ==============
async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user = query.from_user
    game = games.get(chat_id)

    if not game:
        return

    # Validate move
    if game["players"][game["turn"]] != user:
        await context.bot.send_message(chat_id=chat_id,
                                       text="⛔ Chưa đến lượt bạn!")
        return

    x, y = map(int, query.data.split(","))
    if game["board"][y][x] != "▫️":
        await context.bot.send_message(chat_id=chat_id,
                                       text="❗ Ô này đã được đánh rồi!")
        return

    # Make move
    symbol = "❌" if game["players"][
        game["turn"]] == game["players"][0] else "⭕"
    game["board"][y][x] = symbol

    if game.get("task"):
        game["task"].cancel()

    # Check win condition
    if check_win(game["board"], symbol):
        winner = game["players"][game["turn"]]
        winner_id = 0 if winner == "bot" else winner.id
        winner_name = "🤖 Bot" if winner == "bot" else f"👤 {winner.full_name}"

        if winner_id not in win_stats:
            win_stats[winner_id] = {"name": winner_name, "count": 1}
        else:
            win_stats[winner_id]["count"] += 1

        # Cập nhật bàn cờ trước khi thông báo
        await update_board_message(context, chat_id, show_turn=False)

        # Thông báo chiến thắng
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🏆 CHIẾN THẮNG! 🏆\n"
            f"👑 {winner_name}\n"
            f"📊 Thắng: {win_stats[winner_id]['count']}")

        await context.bot.send_message(chat_id=chat_id,
                                       text="👉 Gõ /startgame Bắt đầu ván mới.")

        # Xóa game sau cùng
        games.pop(chat_id, None)
        players.pop(chat_id, None)
        return

    # Switch turn
    game["turn"] = 1 - game["turn"]
    await update_board_message(context, chat_id, show_turn=True)

    # Xử lý bot move
    if game.get("bot_play") and game["players"][game["turn"]] == "bot":
        await asyncio.sleep(1)

        thinking_msg = await context.bot.send_message(
            chat_id=chat_id, text="🤖 Bot đang suy nghĩ...")

        move = best_move(game["board"], "⭕")
        if move:
            x, y = move
            game["board"][y][x] = "⭕"

            await context.bot.delete_message(
                chat_id=chat_id, message_id=thinking_msg.message_id)

            if check_win(game["board"], "⭕"):
                if 0 not in win_stats:
                    win_stats[0] = {"name": "🤖 Bot", "count": 1}
                else:
                    win_stats[0]["count"] += 1

                # Hiển thị bàn cờ trước
                await update_board_message(context, chat_id, show_turn=False)

                # Thông báo chiến thắng
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🏆 CHIẾN THẮNG! 🏆\n"
                    f"👑 🤖 Bot\n"
                    f"📊 Thắng: {win_stats[0]['count']}")

                await context.bot.send_message(
                    chat_id=chat_id, text="👉 Gõ /startgame Bắt đầu ván mới.")

                games.pop(chat_id, None)
                players.pop(chat_id, None)
                return

            game["turn"] = 0
            await update_board_message(context, chat_id, show_turn=True)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Lệnh không hợp lệ. Gõ /help xem hướng dẫn.\n\n"
        "🎮 gameCaro: @Game_carobot\n"
        "🎮 game Nối Chữ: @noi_chu_bot")


# ============== MAIN ==========================
load_dotenv()
TOKEN = os.getenv("TOKEN")
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("startgame", start_game))
app.add_handler(CommandHandler("join", join_game))
app.add_handler(CommandHandler("joinbot", join_bot))
app.add_handler(CommandHandler("reset", reset_game))
app.add_handler(CommandHandler("fast", export_data))
app.add_handler(CommandHandler("secure", delete_export))
app.add_handler(CommandHandler("win", show_win_stats))
app.add_handler(CommandHandler("help", show_rules))
app.add_handler(CallbackQueryHandler(handle_move))
app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

app.run_polling()
