import logging
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import BOT_TOKEN, PG_LINK

pool = None

logger = logging.getLogger(__name__)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)


class Registration(StatesGroup):
    name = State()
    city = State()
    activity = State()
    meet = State()
    mentor = State()
    contacts = State()

class Contacts(StatesGroup):
    type_of_activity = State()

kb = [
        [
            KeyboardButton(text='Хочу общаться! ')
        ]
    ]
keyboard = ReplyKeyboardMarkup(
    keyboard=kb,
    resize_keyboard=True
)   

async def get(query: str, args: list = [], one_row: bool = False):
    global pool
    async with pool.acquire() as conn:
        if not one_row:
            return await conn.fetch(query, *args)
        else:
            return await conn.fetchrow(query, *args)

async def put(query: str, args: list = []):
    global pool
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


@dp.message(CommandStart())
async def command_start(message: Message, state: FSMContext):
    if await get('select 1 from users where user_id = $1', [message.from_user.id], True):
        await message.answer('Вы уже зарегистрированы!')
    else:
        await state.set_state(Registration.name)
        await message.answer(
            'Привет, добро пожаловать в Коммьюнити!\n\nКак тебя зовут?',
            reply_markup=ReplyKeyboardRemove(),
        )

@dp.message(Registration.name)
async def process_name(message: Message, state: FSMContext):
    await state.set_state(Registration.city)
    await state.update_data(name=message.text)
    cities = await get('select city_id, city_name from cities')
    await message.answer(
        f'Привет, {message.text}!\nВыбери свой город!',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=city['city_name'], callback_data=str(city['city_id']))] for city in cities
            ]
        )
    )

@dp.callback_query(Registration.city)
async def process_city(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.activity)
    await state.update_data(city=callback.data)
    activities = await get('select activity_id, activity_name from type_of_activity')
    await callback.message.edit_text(
        f'Чем ты занимаешься?',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=activity['activity_name'], callback_data=str(activity['activity_id']))] for activity in activities
            ]
        )
    )

@dp.callback_query(Registration.activity)
async def process_activity(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.meet)
    await state.update_data(activity=callback.data)
    await callback.message.edit_text(
        f'Готов ли ты получать приглашения на оффлайн встречи?',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='Да', callback_data='true'), InlineKeyboardButton(text='Нет', callback_data='false')]
            ]
        )
    )

@dp.callback_query(Registration.meet)
async def process_meet(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.mentor)
    await state.update_data(meet=callback.data)
    await callback.message.edit_text(
        f'Хочешь быть куратором в будущем? Мы проводим тестирование для желающих.',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='Да', callback_data='true'), InlineKeyboardButton(text='Нет', callback_data='false')]
            ]
        )
    )

@dp.callback_query(Registration.mentor)
async def process_mentor(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.contacts)
    await state.update_data(mentor=callback.data)
    await callback.message.edit_text(
        f'Готов ли ты участвовать в программе "контакты", где ты можешь обменяться контактами с любым участником коммьюнити?',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='Да', callback_data='true'), InlineKeyboardButton(text='Нет', callback_data='false')]
            ]
        )
    )

@dp.callback_query(Registration.contacts)
async def finish_registration(callback: CallbackQuery, state: FSMContext):
    await state.update_data(contacts=callback.data)
    data = await state.get_data()
    await state.clear()
    await callback.message.delete()
    tg_username = callback.from_user.username
    if tg_username:
        await callback.message.answer('Поздравляем, вы зарегистрированы!', reply_markup=keyboard)
        await put(
            """
                insert into users(user_id, user_name, city_id, activity_id, in_meetings, in_contacts, tg_username, wants_curator)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            [callback.from_user.id, data['name'], int(data['city']), int(data['activity']), True if data['meet'] == 'true' else False, True if data['contacts'] == 'true' else False, tg_username, True if data['mentor'] == 'true' else False]
        )
    elif not tg_username:
        await callback.message.answer('К сожалению, у вас не задан username в телеграме, вы зарегестрированы, но не участвуете в программе обмена контактами')
        await put(
            """
                insert into users(user_id, user_name, city_id, activity_id, in_meetings, in_contacts, wants_curator)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            [callback.from_user.id, data['name'], int(data['city']), int(data['activity']), True if data['meet'] == 'true' else False, False, True if data['mentor'] == 'true' else False]
        )

@dp.message(Command('cancel'))
async def cancel_command(message: Message, state: FSMContext):
    await message.answer('Вы отменили текущее действие!')
    await state.clear()

@dp.message(Command('meetings'))
async def change_status(message: Message):
    tg_username = message.from_user.username
    current_status = await get('select in_meetings from users where tg_username = $1', [tg_username], True)
    if not current_status:
        await message.answer('Похоже ты не зарегистрирован, нажми /start для регистрации')
    elif current_status['in_meetings'] == True:
        await put('update users set in_meetings = false where tg_username = $1', [tg_username])
        await message.answer('Статус изменен, теперь вы не получаете приглашения на мероприятия(')
    elif current_status['in_meetings'] == False:
        await put('update users set in_meetings = true where tg_username = $1', [tg_username])
        await message.answer('Ждем вас на будущих встречах!')
    

@dp.message(Command('contacts'))
async def change_contacts_status(message: Message):
    tg_id = message.from_user.id
    current_status = await get('select in_contacts from users where user_id = $1', [tg_id], True)
    if not current_status:
        await message.answer('Похоже вы не зарегистрированы, нажми /start для регистрации')
    elif not message.from_user.username:
        await message.answer('У вас нет tg username, вы не можете участвовать в программе обмена контактами')
    elif current_status['in_contacts'] == True:
        await put('update users set in_contacts = false where user_id = $1', [tg_id])
        await message.answer('Ваш контакт больше не отображается для других пользователей')
    elif current_status['in_contacts'] == False:
        await put('update users set in_contacts = true where user_id = $1', [tg_id])
        await message.answer('Ваш контакт теперь доступен в обмене контактами с другими пользователями!')

@dp.message(F.text == 'Хочу общаться!' or F.text == 'Хочу общаться')
async def get_contact(message: Message, state: FSMContext):
    await state.set_state(Contacts.type_of_activity)
    check = await get('select in_contacts from users where user_id = $1', [message.from_user.id], True)
    if check and check['in_contacts'] == True:
        activities = await get('select activity_id, activity_name from type_of_activity')
        await message.answer(
            'Отлично, давай подберем тебе подходящего собеседника!\nКого ты ищешь?',
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=activity['activity_name'], callback_data=str(activity['activity_id']))] for activity in activities
                ]
            )
        )
    elif not check:
        await message.answer('Похоже мы не знакомы, чтобы общаться с крутыми ребятами и быть в курсе событий ты должен зарегистрироваться! Для этого напиши /start')
    elif not check['in_contacts']:
        await message.answer('К сожалению, ты не участвуешь в программе контактов, чтобы это изменить напиши /contacts')

@dp.callback_query(Contacts.type_of_activity)
async def process_get_contact(callback: CallbackQuery, state: FSMContext):
    user_city = await get('select city_id from users where user_id = $1', [callback.from_user.id], True)
    contact = await get('select user_name, level, tg_username from users where activity_id = $1 and city_id = $2 and in_contacts is true and tg_username is not null order by random() limit 1', [int(callback.data), int(user_city['city_id'])], True)
    if contact:
        await callback.message.edit_text(
            f"Отлично, подобрал контакт по твоим запросам!\n{contact['user_name']}, {contact['level']} уровень: @{contact['tg_username']}"
        )
    else:
        await callback.message.edit_text('К сожалению по твоему запросу ничего не нашлось, попробуй позже(')
    await state.clear()

@dp.message(Command('delete'))
async def delete_profile(message: Message):
    await put('delete from users where user_id = $1', [message.from_user.id])
    await message.answer('Ваш профиль успешно удален!')

@dp.message(F.text)
async def welcome_func(message: Message):
    await message.answer(
        f'Привет! Меня зовут Сэлвестр, можно просто сэл, я коммьюнити менеджер, помогаю селлерам развивать свой нетворкинг.\nЧтобы найти собеседника напиши: "Хочу общаться!"',
        reply_markup=keyboard
    )

async def main():
    global pool
    pool = await asyncpg.create_pool(PG_LINK)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())