import asyncio
import logging
import sqlite3
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, 
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== КОНФИГУРАЦИЯ ==========
class Config:
    BOT_TOKEN = "7662653538:AAEUlSnB7cOdJ5GybKEWoHL88h3feko_xJQ"
    ADMIN_ID = 2132610146
    CHANNEL_ID = "@ChirchiqEstate"
    
    # Цены подписок (UZS)
    PRICES = {
        'риэлтор': 50000,
        'арендатор': 100000,
        'агентство': 150000,
        'застройщик': 200000
    }
    
    # Бесплатные периоды (дни)
    FREE_DAYS = {
        'риэлтор': 21,
        'арендатор': 28,
        'агентство': 14,
        'застройщик': 7
    }
    
    # Разделы недвижимости
    PROPERTY_TYPES = [
        'аренда',
        'посуточная аренда',
        'гаражи/стоянки', 
        'квартиры',
        'дома',
        'коммерческая недвижимость',
        'дома/квартиры от застройщика',
        'земля'
    ]
    
    # Роли пользователей
    ROLES = [
        'продавец',
        'покупатель',
        'арендатор',
        'риэлтор', 
        'агентство',
        'застройщик'
    ]

# ========== МОДЕЛИ ДАННЫХ ==========
@dataclass
class User:
    id: int
    telegram_id: int
    first_name: str
    username: str
    phone: str = ""
    role: str = "покупатель"
    language: str = "ru"
    currency: str = "uzs"
    subscription_start: datetime = None
    subscription_end: datetime = None
    is_active: bool = True
    created_at: datetime = None
    
    def has_active_subscription(self):
        if self.role in ['покупатель', 'продавец']:
            return True
        if not self.subscription_end:
            return False
        return self.subscription_end > datetime.now()

@dataclass
class Ad:
    id: int
    user_id: int
    type: str
    title: str
    description: str
    price: float
    currency: str
    location: str
    photos: List[str]
    status: str = "pending"  # pending, approved, rejected
    views: int = 0
    created_at: datetime = None

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('estate.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                first_name TEXT,
                username TEXT,
                phone TEXT,
                role TEXT DEFAULT 'покупатель',
                language TEXT DEFAULT 'ru',
                currency TEXT DEFAULT 'uzs',
                subscription_start DATETIME,
                subscription_end DATETIME,
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Объявления
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                title TEXT,
                description TEXT,
                price REAL,
                currency TEXT,
                location TEXT,
                photos TEXT,  # JSON список
                status TEXT DEFAULT 'pending',
                views INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Подписки
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                plan TEXT,
                start_date DATETIME,
                end_date DATETIME,
                is_paid BOOLEAN DEFAULT FALSE,
                payment_method TEXT DEFAULT 'transfer',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Платежи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                currency TEXT,
                description TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        self.conn.commit()
    
    def get_user(self, telegram_id: int) -> Optional[User]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        
        if row:
            return User(
                id=row[0], telegram_id=row[1], first_name=row[2], username=row[3],
                phone=row[4], role=row[5], language=row[6], currency=row[7],
                subscription_start=datetime.fromisoformat(row[8]) if row[8] else None,
                subscription_end=datetime.fromisoformat(row[9]) if row[9] else None,
                is_active=bool(row[10]), created_at=datetime.fromisoformat(row[11]) if row[11] else None
            )
        return None
    
    def create_user(self, telegram_id: int, first_name: str, username: str = None) -> User:
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO users (telegram_id, first_name, username) VALUES (?, ?, ?)',
            (telegram_id, first_name, username)
        )
        self.conn.commit()
        
        return self.get_user(telegram_id)
    
    def update_user_role(self, telegram_id: int, role: str):
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE users SET role = ? WHERE telegram_id = ?',
            (role, telegram_id)
        )
        
        # Устанавливаем бесплатный период для платных ролей
        if role in Config.FREE_DAYS:
            free_days = Config.FREE_DAYS[role]
            start_date = datetime.now()
            end_date = start_date + timedelta(days=free_days)
            
            cursor.execute(
                'UPDATE users SET subscription_start = ?, subscription_end = ? WHERE telegram_id = ?',
                (start_date.isoformat(), end_date.isoformat(), telegram_id)
            )
            
            # Создаем запись о подписке
            cursor.execute(
                '''INSERT INTO subscriptions (user_id, role, plan, start_date, end_date, is_paid) 
                   VALUES ((SELECT id FROM users WHERE telegram_id = ?), ?, 'free_trial', ?, ?, FALSE)''',
                (telegram_id, role, start_date.isoformat(), end_date.isoformat())
            )
        
        self.conn.commit()
    
    def create_ad(self, user_id: int, ad_data: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            '''INSERT INTO ads (user_id, type, title, description, price, currency, location, photos) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, ad_data['type'], ad_data['title'], ad_data['description'],
             ad_data['price'], ad_data['currency'], ad_data['location'],
             json.dumps(ad_data.get('photos', [])))
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get_user_ads(self, user_id: int) -> List[Ad]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM ads WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        rows = cursor.fetchall()
        
        ads = []
        for row in rows:
            ads.append(Ad(
                id=row[0], user_id=row[1], type=row[2], title=row[3], description=row[4],
                price=row[5], currency=row[6], location=row[7], 
                photos=json.loads(row[8]) if row[8] else [],
                status=row[9], views=row[10], 
                created_at=datetime.fromisoformat(row[11]) if row[11] else None
            ))
        return ads
    
    def get_pending_ads(self) -> List[Ad]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM ads WHERE status = "pending" ORDER BY created_at DESC')
        rows = cursor.fetchall()
        
        ads = []
        for row in rows:
            ads.append(Ad(
                id=row[0], user_id=row[1], type=row[2], title=row[3], description=row[4],
                price=row[5], currency=row[6], location=row[7], 
                photos=json.loads(row[8]) if row[8] else [],
                status=row[9], views=row[10], 
                created_at=datetime.fromisoformat(row[11]) if row[11] else None
            ))
        return ads
    
    def update_ad_status(self, ad_id: int, status: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE ads SET status = ? WHERE id = ?', (status, ad_id))
        self.conn.commit()

# ========== СОСТОЯНИЯ FSM ==========
class AdStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_location = State()
    waiting_for_photos = State()
    preview = State()

class UserStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_role = State()
    waiting_for_phone = State()

# ========== КЛАВИАТУРЫ ==========
class Keyboards:
    @staticmethod
    def get_main_menu(language: str = 'ru'):
        if language == 'uz':
            return ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🔄 Tilni o'zgartirish")],
                    [KeyboardButton(text="💰 Valyutani o'zgartirish")],
                    [KeyboardButton(text="🏠 Yangi e'lon qo'shish")],
                    [KeyboardButton(text="📋 Mening e'lonlarim")],
                    [KeyboardButton(text="🔍 Qidiruv")],
                    [KeyboardButton(text="👤 Profil")],
                    [KeyboardButton(text="💳 Obuna")]
                ],
                resize_keyboard=True
            )
        elif language == 'en':
            return ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🔄 Change Language")],
                    [KeyboardButton(text="💰 Change Currency")],
                    [KeyboardButton(text="🏠 Add New Ad")],
                    [KeyboardButton(text="📋 My Ads")],
                    [KeyboardButton(text="🔍 Search")],
                    [KeyboardButton(text="👤 Profile")],
                    [KeyboardButton(text="💳 Subscription")]
                ],
                resize_keyboard=True
            )
        else:  # ru
            return ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🔄 Сменить язык")],
                    [KeyboardButton(text="💰 Сменить валюту")],
                    [KeyboardButton(text="🏠 Добавить объявление")],
                    [KeyboardButton(text="📋 Мои объявления")],
                    [KeyboardButton(text="🔍 Поиск")],
                    [KeyboardButton(text="👤 Профиль")],
                    [KeyboardButton(text="💳 Подписка")]
                ],
                resize_keyboard=True
            )
    
    @staticmethod
    def get_language_keyboard():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz")],
                [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
                [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
            ]
        )
    
    @staticmethod
    def get_currency_keyboard():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🇺🇿 UZS", callback_data="currency_uzs")],
                [InlineKeyboardButton(text="🇺🇸 USD", callback_data="currency_usd")]
            ]
        )
    
    @staticmethod
    def get_property_type_keyboard():
        keyboard = []
        for prop_type in Config.PROPERTY_TYPES:
            keyboard.append([InlineKeyboardButton(text=prop_type, callback_data=f"type_{prop_type}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def get_roles_keyboard():
        keyboard = []
        for role in Config.ROLES:
            keyboard.append([InlineKeyboardButton(text=role, callback_data=f"role_{role}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def get_subscription_plans():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="1 месяц", callback_data="plan_1month")],
                [InlineKeyboardButton(text="3 месяца", callback_data="plan_3months")],
                [InlineKeyboardButton(text="6 месяцев", callback_data="plan_6months")],
                [InlineKeyboardButton(text="1 год", callback_data="plan_1year")],
                [InlineKeyboardButton(text="Процент от сделки", callback_data="plan_percentage")]
            ]
        )
    
    @staticmethod
    def get_admin_moderation_keyboard(ad_id: int):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{ad_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{ad_id}")
                ],
                [
                    InlineKeyboardButton(text="👀 Предпросмотр", callback_data=f"preview_{ad_id}")
                ]
            ]
        )
    
    @staticmethod
    def get_ad_preview_keyboard():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Отправить", callback_data="submit_ad"),
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_ad")
                ]
            ]
        )

# ========== NLP ОБРАБОТКА ==========
class NLPProcessor:
    @staticmethod
    def extract_info(text: str) -> Dict:
        info = {
            'type': None,
            'price': None,
            'location': None,
            'features': []
        }
        
        # Поиск цены
        price_patterns = [
            r'(\d+[\s\d]*)\s*(?:сум|usd|доллар)',
            r'цена\s*:\s*(\d+[\s\d]*)',
            r'(\d+[\s\d]*)\s*(?:₽|\$|€)'
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text.lower())
            if match:
                info['price'] = match.group(1).replace(' ', '')
                break
        
        # Определение типа
        text_lower = text.lower()
        type_keywords = {
            'аренда': ['аренда', 'снять', 'сдам'],
            'квартиры': ['квартира', 'апартаменты', 'студио'],
            'дома': ['дом', 'коттедж', 'дача'],
            'коммерческая': ['офис', 'магазин', 'коммерческая']
        }
        
        for prop_type, keywords in type_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                info['type'] = prop_type
                break
        
        # Поиск локации
        location_keywords = ['чирчик', 'ташкент', 'регион', 'район', 'улица']
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in location_keywords and i + 1 < len(words):
                info['location'] = words[i + 1]
                break
        
        return info
    
    @staticmethod
    def validate_ad(text: str) -> Dict:
        issues = []
        suggestions = []
        
        if len(text) < 20:
            issues.append("Слишком короткое описание")
            suggestions.append("Добавьте больше деталей о объекте")
        
        if not any(char.isdigit() for char in text):
            issues.append("Цена не указана")
            suggestions.append("Укажите цену в описании")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'suggestions': suggestions
        }

# ========== ОСНОВНОЙ КОД БОТА ==========
class EstateBot:
    def __init__(self):
        self.bot = Bot(token=Config.BOT_TOKEN)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.db = Database()
        self.nlp = NLPProcessor()
        
        self.setup_handlers()
    
    def setup_handlers(self):
        # Команды
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_admin, Command("admin"))
        self.dp.message.register(self.cmd_moderate, Command("moderate"))
        self.dp.message.register(self.cmd_stats, Command("stats"))
        
        # Основное меню
        self.dp.message.register(self.change_language, F.text.contains("Сменить язык") | F.text.contains("Change Language") | F.text.contains("Tilni o'zgartirish"))
        self.dp.message.register(self.change_currency, F.text.contains("Сменить валюту") | F.text.contains("Change Currency") | F.text.contains("Valyutani o'zgartirish"))
        self.dp.message.register(self.add_new_ad, F.text.contains("Добавить объявление") | F.text.contains("Add New Ad") | F.text.contains("Yangi e'lon qo'shish"))
        self.dp.message.register(self.show_my_ads, F.text.contains("Мои объявления") | F.text.contains("My Ads") | F.text.contains("Mening e'lonlarim"))
        self.dp.message.register(self.show_profile, F.text.contains("Профиль") | F.text.contains("Profile") | F.text.contains("Profil"))
        self.dp.message.register(self.show_subscription, F.text.contains("Подписка") | F.text.contains("Subscription") | F.text.contains("Obuna"))
        
        # Callback запросы
        self.dp.callback_query.register(self.process_language, F.data.startswith("lang_"))
        self.dp.callback_query.register(self.process_currency, F.data.startswith("currency_"))
        self.dp.callback_query.register(self.process_role, F.data.startswith("role_"))
        self.dp.callback_query.register(self.process_property_type, F.data.startswith("type_"))
        self.dp.callback_query.register(self.process_admin_action, F.data.startswith("approve_") | F.data.startswith("reject_"))
        self.dp.callback_query.register(self.process_ad_submission, F.data == "submit_ad")
        self.dp.callback_query.register(self.process_subscription_plan, F.data.startswith("plan_"))
        
        # Создание объявлений
        self.dp.message.register(self.process_ad_title, AdStates.waiting_for_title)
        self.dp.message.register(self.process_ad_description, AdStates.waiting_for_description)
        self.dp.message.register(self.process_ad_price, AdStates.waiting_for_price)
        self.dp.message.register(self.process_ad_location, AdStates.waiting_for_location)
        self.dp.message.register(self.process_ad_photos, AdStates.waiting_for_photos, F.photo)
        self.dp.message.register(self.finish_photos, AdStates.waiting_for_photos, F.text == "Готово")
    
    # ========== КОМАНДЫ ==========
    async def cmd_start(self, message: Message, state: FSMContext):
        user = self.db.get_user(message.from_user.id)
        
        if not user:
            await message.answer(
                "Добро пожаловать! Выберите язык:\n\n"
                "Xush kelibsiz! Tilni tanlang:\n\n"
                "Welcome! Choose language:",
                rep
