from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.markdown import hbold

from database import Database, User
from keyboards import Keyboards
from states import UserStates
from config import Config

# Создаем роутер
router = Router()
db = Database()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Обработчик команды /start
    Проверяет существование пользователя и запускает процесс регистрации
    """
    user = db.get_user(message.from_user.id)
    
    if not user:
        # Новый пользователь - предлагаем выбрать язык
        welcome_text = """
👋 Добро пожаловать в {hbold("Chirchiq Estate")}!

🏠 Платформа недвижимости Чирчика с умными функциями:

• 🤖 ИИ-помощник для создания объявлений
• 🔍 Умный поиск недвижимости  
• 📊 Аналитика рынка
• 💳 Гибкая система подписок
• 👥 Сообщество профессионалов

Выберите язык / Tilni tanlang / Choose language:
        """.format(hbold=hbold)

        await message.answer(welcome_text, reply_markup=Keyboards.get_language_keyboard())
        await state.set_state(UserStates.waiting_for_language)
        
        # Логируем нового пользователя
        print(f"🆕 Новый пользователь: {message.from_user.full_name} (@{message.from_user.username})")
        
    else:
        # Существующий пользователь - показываем главное меню
        welcome_back_texts = {
            'ru': f"🎉 С возвращением, {hbold(user.first_name)}!",
            'uz': f"🎉 Xush kelibsiz, {hbold(user.first_name)}!",
            'en': f"🎉 Welcome back, {hbold(user.first_name)}!"
        }
        
        welcome_text = welcome_back_texts.get(user.language, welcome_back_texts['ru'])
        
        # Добавляем информацию о подписке для платных ролей
        if user.role in ['риэлтор', 'арендатор', 'агентство', 'застройщик']:
            if user.has_active_subscription():
                days_left = (user.subscription_end - datetime.now()).days
                subscription_info = {
                    'ru': f"\n\n✅ Ваша подписка активна\nОсталось дней: {days_left}",
                    'uz': f"\n\n✅ Obunangiz faol\nQolgan kunlar: {days_left}",
                    'en': f"\n\n✅ Your subscription is active\nDays left: {days_left}"
                }
                welcome_text += subscription_info.get(user.language, subscription_info['ru'])
            else:
                subscription_info = {
                    'ru': f"\n\n❌ Подписка не активна\nИспользуйте меню 'Подписка' для продления",
                    'uz': f"\n\n❌ Obuna faol emas\nObunani uzaytirish uchun 'Obuna' menyusidan foydalaning",
                    'en': f"\n\n❌ Subscription not active\nUse 'Subscription' menu to renew"
                }
                welcome_text += subscription_info.get(user.language, subscription_info['ru'])
        
        await message.answer(welcome_text, reply_markup=Keyboards.get_main_menu(user.language))
        await state.clear()

@router.callback_query(F.data.startswith("lang_"))
async def process_language_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора языка пользователем
    """
    language = callback.data.split("_")[1]  # lang_ru -> ru
    
    # Создаем или обновляем пользователя
    user = db.get_user(callback.from_user.id)
    if not user:
        user = db.create_user(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name,
            username=callback.from_user.username
        )
    
    # Обновляем язык пользователя
    db.update_user_language(callback.from_user.id, language)
    
    # Подтверждаем выбор языка
    confirmation_texts = {
        'ru': "✅ Язык установлен! Теперь выберите вашу роль:",
        'uz': "✅ Til o'rnatildi! Endi rolizingizni tanlang:",
        'en': "✅ Language set! Now choose your role:"
    }
    
    await callback.message.edit_text(confirmation_texts[language])
    
    # Показываем клавиатуру выбора роли
    role_keyboard = Keyboards.get_roles_keyboard(language)
    await callback.message.answer("👤 Выберите вашу роль:", reply_markup=role_keyboard)
    await state.set_state(UserStates.waiting_for_role)

@router.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора роли пользователем
    """
    role = callback.data.split("_")[1]  # role_риэлтор -> риэлтор
    
    # Обновляем роль пользователя
    user = db.update_user_role(callback.from_user.id, role)
    
    if not user:
        await callback.message.answer("❌ Ошибка при обновлении роли. Попробуйте снова /start")
        await state.clear()
        return
    
    # Формируем сообщение в зависимости от роли
    role_messages = {
        'продавец': {
            'ru': "🏠 Вы выбрали роль {hbold('Продавец')}\n\nВы можете бесплатно размещать объявления о продаже недвижимости.",
            'uz': "🏠 Siz {hbold('Sotuvchi')} rolini tanladingiz\n\nKo'chmas mulkni sotish haqida e'lonlarni bepul joylashtirishingiz mumkin.",
            'en': "🏠 You selected {hbold('Seller')} role\n\nYou can post real estate listings for free."
        },
        'покупатель': {
            'ru': "💰 Вы выбрали роль {hbold('Покупатель')}\n\nВы можете бесплатно искать недвижимость и связываться с продавцами.",
            'uz': "💰 Siz {hbold('Xaridor')} rolini tanladingiz\n\nKo'chmas mulkni qidirishingiz va sotuvchilar bilan bog'lanishingiz mumkin.",
            'en': "💰 You selected {hbold('Buyer')} role\n\nYou can search for properties and contact sellers for free."
        },
        'арендатор': {
            'ru': "🏡 Вы выбрали роль {hbold('Арендатор')}\n\nВы можете сдавать недвижимость в аренду. Доступен бесплатный период на {free_days} дней.",
            'uz': "🏡 Siz {hbold('Ijarachi')} rolini tanladingiz\n\nKo'chmas mulkni ijaraga berishingiz mumkin. {free_days} kunlik bepul muddat mavjud.",
            'en': "🏡 You selected {hbold('Tenant')} role\n\nYou can rent out properties. Free trial for {free_days} days available."
        },
        'риэлтор': {
            'ru': "👔 Вы выбрали роль {hbold('Риэлтор')}\n\nПрофессиональные инструменты для работы с недвижимостью. Доступен бесплатный период на {free_days} дней.",
            'uz': "👔 Siz {hbold('Rieltor')} rolini tanladingiz\n\nKo'chmas mulk bilan ishlash uchun professional vositalar. {free_days} kunlik bepul muddat mavjud.",
            'en': "👔 You selected {hbold('Realtor')} role\n\nProfessional tools for real estate work. Free trial for {free_days} days available."
        },
        'агентство': {
            'ru': "🏢 Вы выбрали роль {hbold('Агентство')}\n\nРасширенные возможности для агентств недвижимости. Доступен бесплатный период на {free_days} дней.",
            'uz': "🏢 Siz {hbold('Agentlik')} rolini tanladingiz\n\nKo'chmas mulk agentliklari uchun kengaytirilgan imkoniyatlar. {free_days} kunlik bepul muddat mavjud.",
            'en': "🏢 You selected {hbold('Agency')} role\n\nExtended features for real estate agencies. Free trial for {free_days} days available."
        },
        'застройщик': {
            'ru': "🏗️ Вы выбрали роль {hbold('Застройщик')}\n\nСпециальные инструменты для застройщиков. Доступен бесплатный период на {free_days} дней.",
            'uz': "🏗️ Siz {hbold('Quruvchi')} rolini tanladingiz\n\nQuruvchilar uchun maxsus vositalar. {free_days} kunlik bepul muddat mavjud.",
            'en': "🏗️ You selected {hbold('Developer')} role\n\nSpecial tools for developers. Free trial for {free_days} days available."
        }
    }
    
    # Получаем сообщение для выбранной роли
    role_message_template = role_messages.get(role, role_messages['покупатель'])
    free_days = Config.FREE_DAYS.get(role, 0)
    
    role_message = role_message_template[user.language].format(
        hbold=hbold,
        free_days=free_days
    )
    
    # Добавляем информацию о подписке для платных ролей
    if role in ['риэлтор', 'арендатор', 'агентство', 'застройщик']:
        subscription_info = {
            'ru': f"\n\n💳 После окончания бесплатного периода:\nМесячная подписка: {Config.PRICES.get(role, 0):,} UZS",
            'uz': f"\n\n💳 Bepul muddat tugagandan so'ng:\nOylik obuna: {Config.PRICES.get(role, 0):,} UZS",
            'en': f"\n\n💳 After free trial ends:\nMonthly subscription: {Config.PRICES.get(role, 0):,} UZS"
        }
        role_message += subscription_info[user.language]
    
    await callback.message.edit_text(role_message)
    
    # Показываем главное меню
    main_menu_texts = {
        'ru': "🎯 Теперь вы можете использовать все функции бота:",
        'uz': "🎯 Endi botning barcha funksiyalaridan foydalanishingiz mumkin:",
        'en': "🎯 Now you can use all bot features:"
    }
    
    await callback.message.answer(
        main_menu_texts[user.language],
        reply_markup=Keyboards.get_main_menu(user.language)
    )
    
    # Отправляем приветственное сообщение с инструкциями
    welcome_instructions = {
        'ru': """
📋 {hbold("Основные функции:")}

🏠 {hbold("Добавить объявление")} - Разместить новое объявление
📋 {hbold("Мои объявления")} - Управление вашими объявлениями  
🔍 {hbold("Поиск")} - Поиск недвижимости
👤 {hbold("Профиль")} - Информация о вашем аккаунте
💳 {hbold("Подписка")} - Управление подпиской

🆘 Помощь: /help
        """,
        'uz': """
📋 {hbold("Asosiy funksiyalar:")}

🏠 {hbold("Yangi e'lon qo'shish")} - Yangi e'lon joylashtirish
📋 {hbold("Mening e'lonlarim")} - Sizning e'lonlaringizni boshqarish
🔍 {hbold("Qidiruv")} - Ko'chmas mulkni qidirish
👤 {hbold("Profil")} - Hisobingiz haqida ma'lumot
💳 {hbold("Obuna")} - Obunani boshqarish

🆘 Yordam: /help
        """,
        'en': """
📋 {hbold("Main features:")}

🏠 {hbold("Add New Ad")} - Post a new listing
📋 {hbold("My Ads")} - Manage your listings
🔍 {hbold("Search")} - Search for properties
👤 {hbold("Profile")} - Your account information  
💳 {hbold("Subscription")} - Subscription management

🆘 Help: /help
        """
    }
    
    await callback.message.answer(
        welcome_instructions[user.language].format(hbold=hbold)
    )
    
    await state.clear()
    
    # Логируем выбор роли
    print(f"👤 Пользователь {user.first_name} выбрал роль: {role}")

@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Обработчик команды /help
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return
    
    help_texts = {
        'ru': """
🆘 {hbold("Помощь по использованию бота")}

{hbold("Основные команды:")}
/start - Перезапустить бота
/help - Показать эту справку
/profile - Информация о профиле

{hbold("Основные функции через меню:")}
🏠 {hbold("Добавить объявление")} - Создать новое объявление о недвижимости
📋 {hbold("Мои объявления")} - Просмотр и управление вашими объявлениями
🔍 {hbold("Поиск")} - Поиск недвижимости по критериям
👤 {hbold("Профиль")} - Информация о вашем аккаунте и подписке
💳 {hbold("Подписка")} - Управление подпиской (для платных ролей)

{hbold("Для администраторов:")}
/admin - Панель администратора
/moderate - Модерация объявлений
/stats - Статистика системы

{hbold("Поддержка:")}
По вопросам работы бота обращайтесь к @Jamshid
        """,
        'uz': """
🆘 {hbold("Botdan foydalanish bo'yicha yordam")}

{hbold("Asosiy buyruqlar:")}
/start - Botni qayta ishga tushirish
/help - Ushbu yordamni ko'rsatish
/profile - Profil haqida ma'lumot

{hbold("Menyu orqali asosiy funksiyalar:")}
🏠 {hbold("Yangi e'lon qo'shish")} - Ko'chmas mulk haqida yangi e'lon yaratish
📋 {hbold("Mening e'lonlarim")} - Sizning e'lonlaringizni ko'rish va boshqarish
🔍 {hbold("Qidiruv")} - Mezonlar bo'yicha ko'chmas mulkni qidirish
👤 {hbold("Profil")} - Hisobingiz va obunangiz haqida ma'lumot
💳 {hbold("Obuna")} - Obunani boshqarish (pulli rollar uchun)

{hbold("Administratorlar uchun:")}
/admin - Administrator paneli
/moderate - E'lonlarni moderatsiya qilish
/stats - Tizim statistikasi

{hbold("Qo'llab-quvvatlash:")}
Bot ishlashi bilan bog'liq savollar uchun @Jamshid ga murojaat qiling
        """,
        'en': """
🆘 {hbold("Bot Usage Help")}

{hbold("Main commands:")}
/start - Restart the bot
/help - Show this help
/profile - Profile information

{hbold("Main features via menu:")}
🏠 {hbold("Add New Ad")} - Create new property listing
📋 {hbold("My Ads")} - View and manage your listings
🔍 {hbold("Search")} - Search properties by criteria
👤 {hbold("Profile")} - Your account and subscription info
💳 {hbold("Subscription")} - Subscription management (for paid roles)

{hbold("For administrators:")}
/admin - Admin panel
/moderate - Ads moderation
/stats - System statistics

{hbold("Support:")}
For bot operation questions contact @Jamshid
        """
    }
    
    await message.answer(
        help_texts[user.language].format(hbold=hbold)
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """
    Обработчик команды /profile
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return
    
    # Основная информация о профиле
    profile_texts = {
        'ru': """
👤 {hbold("Ваш профиль")}

📝 Имя: {first_name}
👤 Роль: {role}
🌐 Язык: {language}
💱 Валюта: {currency}
📅 Регистрация: {registration_date}
        """,
        'uz': """
👤 {hbold("Sizning profilingiz")}

📝 Ism: {first_name}
👤 Rol: {role}
🌐 Til: {language}
💱 Valyuta: {currency}
📅 Ro'yxatdan o'tish: {registration_date}
        """,
        'en': """
👤 {hbold("Your Profile")}

📝 Name: {first_name}
👤 Role: {role}
🌐 Language: {language}
💱 Currency: {currency}
📅 Registration: {registration_date}
        """
    }
    
    profile_text = profile_texts[user.language].format(
        hbold=hbold,
        first_name=user.first_name,
        role=user.role,
        language=user.language.upper(),
        currency=user.currency.upper(),
        registration_date=user.created_at.strftime("%d.%m.%Y") if user.created_at else "Неизвестно"
    )
    
    # Добавляем информацию о подписке для платных ролей
    if user.role in ['риэлтор', 'арендатор', 'агентство', 'застройщик']:
        if user.has_active_subscription():
            days_left = (user.subscription_end - datetime.now()).days
            subscription_texts = {
                'ru': f"\n💳 {hbold('Подписка')}\n✅ Активна\n⏳ Осталось дней: {days_left}",
                'uz': f"\n💳 {hbold('Obuna')}\n✅ Faol\n⏳ Qolgan kunlar: {days_left}",
                'en': f"\n💳 {hbold('Subscription')}\n✅ Active\n⏳ Days left: {days_left}"
            }
        else:
            price = Config.PRICES.get(user.role, 0)
            subscription_texts = {
                'ru': f"\n💳 {hbold('Подписка')}\n❌ Не активна\n💰 Стоимость: {price:,} UZS/месяц",
                'uz': f"\n💳 {hbold('Obuna')}\n❌ Faol emas\n💰 Narx: {price:,} UZS/oy",
                'en': f"\n💳 {hbold('Subscription')}\n❌ Not active\n💰 Price: {price:,} UZS/month"
            }
        
        profile_text += subscription_texts[user.language]
    
    # Добавляем статистику
    user_ads = db.get_user_ads(user.id)
    active_ads = len([ad for ad in user_ads if ad.status == 'approved'])
    total_views = sum(ad.views for ad in user_ads)
    
    stats_texts = {
        'ru': f"\n\n📊 {hbold('Статистика')}\n📋 Объявления: {len(user_ads)}\n✅ Активные: {active_ads}\n👀 Просмотры: {total_views}",
        'uz': f"\n\n📊 {hbold('Statistika')}\n📋 E'lonlar: {len(user_ads)}\n✅ Faol: {active_ads}\n👀 Ko'rishlar: {total_views}",
        'en': f"\n\n📊 {hbold('Statistics')}\n📋 Ads: {len(user_ads)}\n✅ Active: {active_ads}\n👀 Views: {total_views}"
    }
    
    profile_text += stats_texts[user.language]
    
    await message.answer(profile_text)

@router.message(F.text == "🔄 Сменить язык")
@router.message(F.text == "🔄 Change Language") 
@router.message(F.text == "🔄 Tilni o'zgartirish")
async def change_language_handler(message: Message, state: FSMContext):
    """
    Обработчик смены языка через меню
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return
    
    change_language_texts = {
        'ru': "Выберите новый язык:",
        'uz': "Yangi tilni tanlang:",
        'en': "Choose new language:"
    }
    
    await message.answer(
        change_language_texts[user.language],
        reply_markup=Keyboards.get_language_keyboard()
    )
    await state.set_state(UserStates.waiting_for_language)

@router.message(F.text == "💰 Сменить валюту")
@router.message(F.text == "💰 Change Currency")
@router.message(F.text == "💰 Valyutani o'zgartirish")
async def change_currency_handler(message: Message):
    """
    Обработчик смены валюты через меню
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return
    
    change_currency_texts = {
        'ru': "Выберите валюту для отображения цен:",
        'uz': "Narxlarni ko'rsatish uchun valyutani tanlang:",
        'en': "Choose currency for price display:"
    }
    
    await message.answer(
        change_currency_texts[user.language],
        reply_markup=Keyboards.get_currency_keyboard()
    )

@router.callback_query(F.data.startswith("currency_"))
async def process_currency_selection(callback: CallbackQuery):
    """
    Обработка выбора валюты
    """
    currency = callback.data.split("_")[1]  # currency_uzs -> uzs
    
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.message.answer("Сначала запустите бота командой /start")
        return
    
    # Обновляем валюту пользователя
    db.update_user_currency(callback.from_user.id, currency)
    
    confirmation_texts = {
        'uzs': {
            'ru': "✅ Валюта изменена на UZS (узбекский сум)",
            'uz': "✅ Valyuta UZS (o'zbek so'mi) ga o'zgartirildi",
            'en': "✅ Currency changed to UZS (Uzbekistani Som)"
        },
        'usd': {
            'ru': "✅ Валюта изменена на USD (доллар США)",
            'uz': "✅ Valyuta USD (AQSh dollari) ga o'zgartirildi",
            'en': "✅ Currency changed to USD (US Dollar)"
        }
    }
    
    await callback.message.edit_text(
        confirmation_texts[currency][user.language]
    )

# Экспортируем роутер
__all__ = ['router']
