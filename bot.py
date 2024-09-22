import logging
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

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


async def get(query: str, args: list = [], one_row: bool = False):
    global pool
    async with pool.acquire() as conn:
        if not one_row:
            return await conn.fetch(query, *args)
        else:
            return await conn.fetchrow(query, *args)

async def put(query: str, args: list = None):
    global pool
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


@dp.message(CommandStart())
async def command_start(message: Message, state: FSMContext):
    if await get('select 1 from users where tg_username = $1', [message.from_user.username], True):
        await message.answer('Вы уже зарегестрированы!')
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
    cities = await get('select * from cities')
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
    activities = await get('select * from type_of_activity')
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
    await state.set_state(Registration.contacts)
    await state.update_data(meet=callback.data)
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
    await callback.message.delete()
    await callback.message.answer('Поздравляем, вы зарегестрированы!\nВаш уровень: 1')
    await put(
        """
            insert into users(user_name, city_id, activity_id, in_meetings, in_contacts, tg_username)
            VALUES ($1, $2, $3, $4, $5, $6)
        """,
        [data['name'], int(data['city']), int(data['activity']), bool(data['meet']), bool(data['contacts']), callback.from_user.username]
    )

async def main():
    global pool
    pool = await asyncpg.create_pool(PG_LINK)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())