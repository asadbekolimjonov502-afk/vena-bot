"""
Vena Vokabeltrainer — Telegram bot for vocabulary training
Python + aiogram 3

Install:  pip install aiogram
Run:      python bot.py
Token:    set env var BOT_TOKEN or paste below
"""

import asyncio
import os
import random
import sqlite3

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# --------------------------------------------------------------------------- #
#  CONFIG
# --------------------------------------------------------------------------- #
BOT_TOKEN = os.getenv("BOT_TOKEN", "8921915862:AAEEdHr0vtd_eKOF4pDdKM12UEjhA4Wqylk")
DB = "vokabeln.db"

# Max repetitions (Leitner boxes): 0 = brand new, 5 = learned
MAX_BOX = 5

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="html"))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# --------------------------------------------------------------------------- #
#  DATABASE
# --------------------------------------------------------------------------- #
def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS words(
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            front    TEXT NOT NULL,
            back     TEXT NOT NULL,
            box      INTEGER DEFAULT 0,
            correct  INTEGER DEFAULT 0,
            wrong    INTEGER DEFAULT 0
        )
        """
    )
    con.commit()
    con.close()


def get_words(user_id: int):
    con = db()
    rows = con.execute(
        "SELECT * FROM words WHERE user_id=? ORDER BY id", (user_id,)
    ).fetchall()
    con.close()
    return rows


def add_word(user_id: int, front: str, back: str):
    con = db()
    con.execute(
        "INSERT INTO words(user_id, front, back) VALUES(?,?,?)",
        (user_id, front.strip(), back.strip()),
    )
    con.commit()
    con.close()


def update_result(word_id: int, correct: bool):
    con = db()
    row = con.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
    if not row:
        con.close()
        return
    box = row["box"]
    if correct:
        box = min(box + 1, MAX_BOX)
        con.execute(
            "UPDATE words SET box=?, correct=correct+1 WHERE id=?", (box, word_id)
        )
    else:
        box = max(box - 1, 0)
        con.execute(
            "UPDATE words SET box=?, wrong=wrong+1 WHERE id=?", (box, word_id)
        )
    con.commit()
    con.close()


def delete_word(user_id: int, word_id: int):
    con = db()
    con.execute("DELETE FROM words WHERE id=? AND user_id=?", (word_id, user_id))
    con.commit()
    con.close()


def reset_user(user_id: int):
    con = db()
    con.execute(
        "UPDATE words SET box=0, correct=0, wrong=0 WHERE user_id=?", (user_id,)
    )
    con.commit()
    con.close()


# --------------------------------------------------------------------------- #
#  FSM STATES
# --------------------------------------------------------------------------- #
class AddState(StatesGroup):
    waiting = State()


class TrainState(StatesGroup):
    waiting = State()


# --------------------------------------------------------------------------- #
#  KEYBOARDS
# --------------------------------------------------------------------------- #
def quiz_kb(options, correct_id):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=opt, callback_data=f"q:{correct_id}:{oid}"
                )
            ]
            for opt, oid in options
        ]
    )
    return kb


# --------------------------------------------------------------------------- #
#  COMMANDS
# --------------------------------------------------------------------------- #
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🇦🇹 <b>Vena Vokabeltrainer</b>\n\n"
        "Nemischa so'zlarni o'yin orqali yodlaymiz!\n\n"
        "<b>Buyruqlar:</b>\n"
        "/add — so'z qo'shish\n"
        "/quiz — variantli test\n"
        "/train — yozib tarjima qilish\n"
        "/list — so'zlar ro'yxati\n"
        "/stats — statistika\n"
        "/reset — progressni noldan boshlash\n"
        "/del — so'z o'chirish\n"
        "/seed — namuna so'zlar yuklash\n\n"
        "Boshlash uchun <code>/add</code> bilan so'z qo'sh yoki "
        "<code>/seed</code> bilan 20 ta namuna yukla."
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await message.answer(
        "So'zni shunday yubor:\n<code>der Hund | it</code>\n"
        "(old tomoni | orqa tomoni)"
    )
    await state.set_state(AddState.waiting)


@router.message(AddState.waiting)
async def process_add(message: Message, state: FSMContext):
    text = message.text or ""
    sep = None
    for s in ("|", "=", ";", " - "):
        if s in text:
            sep = s
            break
    if not sep:
        await message.answer("❗️ Ajratgichni qo'y: <code>der Hund | it</code>")
        return
    front, back = text.split(sep, 1)
    if not front.strip() or not back.strip():
        await message.answer("❗️ Ikkala tomon ham bo'sh bo'lmasin.")
        return
    add_word(message.from_user.id, front, back)
    await state.clear()
    await message.answer(f"✅ Qo'shildi: <b>{front.strip()}</b> — {back.strip()}")


@router.message(Command("list"))
async def cmd_list(message: Message):
    words = get_words(message.from_user.id)
    if not words:
        await message.answer("Baza bo'sh. /add yoki /seed dan foydalan.")
        return
    lines = [
        f"{i + 1}. {w['front']} — {w['back']}  (box {w['box']})"
        for i, w in enumerate(words[:60])
    ]
    txt = "📚 <b>So'zlaring:</b>\n" + "\n".join(lines)
    if len(words) > 60:
        txt += f"\n\n... va yana {len(words) - 60} ta"
    await message.answer(txt)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    words = get_words(message.from_user.id)
    if not words:
        await message.answer("Hali so'z yo'q. /add bilan boshlaymiz!")
        return
    total = len(words)
    correct = sum(w["correct"] for w in words)
    wrong = sum(w["wrong"] for w in words)
    learned = sum(1 for w in words if w["box"] >= MAX_BOX)
    answered = correct + wrong
    acc = round(correct / answered * 100) if answered else 0
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"So'zlar: <b>{total}</b>\n"
        f"O'rganilgan (box {MAX_BOX}): <b>{learned}</b>\n"
        f"To'g'ri javob: <b>{correct}</b>\n"
        f"Xato javob: <b>{wrong}</b>\n"
        f"Aniqlik: <b>{acc}%</b>"
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    reset_user(message.from_user.id)
    await message.answer("♻️ Progress noldan boshlandi.")


@router.message(Command("del"))
async def cmd_del(message: Message):
    words = get_words(message.from_user.id)
    if not words:
        await message.answer("O'chiradigan so'z yo'q.")
        return
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{w['front']} — {w['back']}",
                callback_data=f"del:{w['id']}",
            )
        ]
        for w in words[:30]
    ]
    await message.answer(
        "O'chirmoqchi bo'lgan so'zni tanla:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("del:"))
async def cb_del(call: CallbackQuery):
    word_id = int(call.data.split(":")[1])
    delete_word(call.from_user.id, word_id)
    await call.message.edit_text("🗑 O'chirildi.")
    await call.answer()


# --------------------------------------------------------------------------- #
#  SEED DATA
# --------------------------------------------------------------------------- #
SEED = [
    ("der Hund", "it"),
    ("die Katze", "mushuk"),
    ("das Haus", "uy"),
    ("der Baum", "daraxt"),
    ("das Wasser", "suv"),
    ("das Brot", "non"),
    ("die Milch", "sut"),
    ("der Apfel", "olma"),
    ("der Freund", "do'st"),
    ("die Schule", "maktab"),
    ("das Buch", "kitob"),
    ("der Tag", "kun"),
    ("die Nacht", "tun"),
    ("das Auto", "mashina"),
    ("der Weg", "yo'l"),
    ("die Stadt", "shahar"),
    ("das Kind", "bola"),
    ("die Familie", "oila"),
    ("die Arbeit", "ish"),
    ("das Essen", "ovqat"),
]


@router.message(Command("seed"))
async def cmd_seed(message: Message):
    if get_words(message.from_user.id):
        await message.answer(
            "Sizda allaqachon so'zlar bor. Avval /reset qilishingiz mumkin."
        )
        return
    for front, back in SEED:
        add_word(message.from_user.id, front, back)
    await message.answer(
        f"🌱 {len(SEED)} ta namuna so'z yuklandi. Endi /quiz yoki /train!"
    )


# --------------------------------------------------------------------------- #
#  QUIZ (multiple choice)
# --------------------------------------------------------------------------- #
@router.message(Command("quiz"))
async def cmd_quiz(message: Message):
    words = get_words(message.from_user.id)
    if len(words) < 4:
        await message.answer("Quiz uchun kamida 4 ta so'z kerak. /add yoki /seed.")
        return
    word = random.choice(words)
    others = [w for w in words if w["id"] != word["id"]]
    distractors = random.sample(others, min(3, len(others)))
    options = [(word["back"], word["id"])] + [(d["back"], d["id"]) for d in distractors]
    random.shuffle(options)
    await message.answer(
        f"❓ <b>{word['front']}</b>\n\nTo'g'ri tarjimani tanla:",
        reply_markup=quiz_kb(options, word["id"]),
    )


@router.callback_query(F.data.startswith("q:"))
async def cb_quiz(call: CallbackQuery):
    _, correct_id, chosen_id = call.data.split(":")
    correct_id, chosen_id = int(correct_id), int(chosen_id)
    is_right = correct_id == chosen_id

    con = db()
    correct_row = con.execute("SELECT * FROM words WHERE id=?", (correct_id,)).fetchone()
    con.close()

    update_result(correct_id, is_right)

    if is_right:
        await call.message.edit_text(
            call.message.html_text + "\n\n✅ <b>To'g'ri!</b>"
        )
    else:
        await call.message.edit_text(
            call.message.html_text
            + f"\n\n❌ <b>Xato.</b> To'g'ri javob: <b>{correct_row['back']}</b>"
        )
    await call.answer("To'g'ri ✅" if is_right else "Xato ❌")


# --------------------------------------------------------------------------- #
#  TRAIN (typing)
# --------------------------------------------------------------------------- #
@router.message(Command("train"))
async def cmd_train(message: Message, state: FSMContext):
    words = get_words(message.from_user.id)
    if not words:
        await message.answer("Baza bo'sh. /add yoki /seed.")
        return
    word = random.choice(words)
    await state.update_data(word_id=word["id"], back=word["back"])
    await state.set_state(TrainState.waiting)
    await message.answer(f"✍️ <b>{word['front']}</b> — tarjimasini yoz:")


@router.message(TrainState.waiting)
async def process_train(message: Message, state: FSMContext):
    data = await state.get_data()
    expected = data.get("back", "")
    answer = (message.text or "").strip().lower()
    is_right = answer == expected.strip().lower()

    update_result(data["word_id"], is_right)

    if is_right:
        await message.answer("✅ <b>To'g'ri!</b>")
    else:
        await message.answer(f"❌ Xato. To'g'ri javob: <b>{expected}</b>")

    # next question automatically
    words = get_words(message.from_user.id)
    word = random.choice(words)
    await state.update_data(word_id=word["id"], back=word["back"])
    await message.answer(f"✍️ <b>{word['front']}</b> — tarjimasini yoz:")


# --------------------------------------------------------------------------- #
#  RUN
# --------------------------------------------------------------------------- #
async def main():
    init_db()
    print("Vena Vokabeltrainer is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
