import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database, User, Subscription, Payment
from keyboards import Keyboards
from states import PaymentStates
from config import Config

# Создаем роутер
router = Router()
db = Database()

# ========== СИСТЕМА ПОДПИСОК ==========


@router.message(F.text == "💳 Подписка")
@router.message(F.text == "💳 Subscription")
@router.message(F.text == "💳 Obuna")
async def show_subscription_info(message: Message):
    """
    Показ информации о подписке пользователя
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите бота командой /start")
        return

    # Для бесплатных ролей показываем информацию о переходе на платную
    if user.role in ['покупатель', 'продавец']:
        await show_free_role_upgrade(message, user)
        return

    # Для платных ролей показываем статус подписки
    subscription = db.get_user_subscription(user.id)

    if not subscription or not user.has_active_subscription():
        await show_subscription_required(message, user)
    else:
        await show_active_subscription(message, user, subscription)


async def show_free_role_upgrade(message: Message, user: User):
    """
    Показ информации о переходе с бесплатной на платную роль
    """
    upgrade_texts = {
        'ru':
        f"""
🎯 <b>Преимущества платных подписок</b>

Ваша текущая роль: <b>«{user.role}»</b> (бесплатная)

<b>Ограничения бесплатной роли:</b>
• Максимум 5 активных объявлений
• Срок размещения: 30 дней
• Базовые функции поиска
• Нет приоритета в результатах

<b>Что дают платные подписки:</b>
• Неограниченное количество объявлений
• Постоянное размещение (без срока)
• Расширенная аналитика
• Приоритет в поиске
• Профессиональные инструменты

<b>Доступные платные роли:</b>
        """,
        'uz':
        f"""
🎯 <b>Pulli obunalarning afzalliklari</b>

Joriy rolingiz: <b>«{user.role}»</b> (bepul)

<b>Bepul rol cheklovlari:</b>
• Maksimum 5 ta faol e'lon
• Joylashtirish muddati: 30 kun
• Asosiy qidiruv funksiyalari
• Natijalarda ustuvorlik yo'q

<b>Pulli obunalar nima beradi:</b>
• Cheklanmagan miqdorda e'lon
• Doimiy joylashtirish (muddatsiz)
• Kengaytirilgan tahlil
• Qidiruvda ustuvorlik
• Professional vositalar

<b>Mavjud pulli rollar:</b>
        """,
        'en':
        f"""
🎯 <b>Benefits of Paid Subscriptions</b>

Your current role: <b>«{user.role}»</b> (free)

<b>Free role limitations:</b>
• Maximum 5 active listings
• Placement period: 30 days
• Basic search functions
• No priority in results

<b>What paid subscriptions provide:</b>
• Unlimited number of listings
• Permanent placement (no time limit)
• Extended analytics
• Priority in search
• Professional tools

<b>Available paid roles:</b>
        """
    }

    text = upgrade_texts[user.language]

    # Добавляем информацию о платных ролях
    paid_roles = {
        'риэлтор': Config.PRICES['риэлтор'],
        'арендатор': Config.PRICES['арендатор'],
        'агентство': Config.PRICES['агентство'],
        'застройщик': Config.PRICES['застройщик']
    }

    for role, price in paid_roles.items():
        role_names = {
            'ru': {
                'риэлтор': '👔 Риэлтор',
                'арендатор': '🏡 Арендатор',
                'агентство': '🏢 Агентство',
                'застройщик': '🏗️ Застройщик'
            },
            'uz': {
                'риэлтор': '👔 Rieltor',
                'арендатор': '🏡 Ijarachi',
                'агентство': '🏢 Agentlik',
                'застройщик': '🏗️ Quruvchi'
            },
            'en': {
                'риэлтор': '👔 Realtor',
                'арендатор': '🏡 Tenant',
                'агентство': '🏢 Agency',
                'застройщик': '🏗️ Developer'
            }
        }

        text += f"\n• {role_names[user.language][role]} - {price:,} UZS/месяц"

    text += "\n\n💡 <b>Выберите роль для перехода:</b>"

    keyboard = InlineKeyboardBuilder()
    for role in paid_roles.keys():
        role_buttons = {
            'ru': {
                'риэлтор': '👔 Риэлтор',
                'арендатор': '🏡 Арендатор',
                'агентство': '🏢 Агентство',
                'застройщик': '🏗️ Застройщик'
            },
            'uz': {
                'риэлтор': '👔 Rieltor',
                'арендатор': '🏡 Ijarachi',
                'агентство': '🏢 Agentlik',
                'застройщик': '🏗️ Quruvchi'
            },
            'en': {
                'риэлтор': '👔 Realtor',
                'арендатор': '🏡 Tenant',
                'агентство': '🏢 Agency',
                'застройщик': '🏗️ Developer'
            }
        }
        keyboard.add(
            types.InlineKeyboardButton(text=role_buttons[user.language][role],
                                       callback_data=f"upgrade_to_{role}"))

    keyboard.adjust(2)

    await message.answer(text,
                         reply_markup=keyboard.as_markup(),
                         parse_mode='HTML')


async def show_subscription_required(message: Message, user: User):
    """
    Показ информации о необходимости подписки для платных ролей
    """
    price = Config.PRICES.get(user.role, 0)
    free_days = Config.FREE_DAYS.get(user.role, 0)

    subscription_texts = {
        'ru':
        f"""
💳 <b>Подписка не активна</b>

Ваша роль: <b>«{user.role}»</b>
Стоимость подписки: <b>{price:,} UZS/месяц</b>

🎁 <b>Бесплатный период:</b> {free_days} дней
💎 <b>После бесплатного периода:</b> {price:,} UZS/месяц

<b>Что включено в подписку:</b>
• Неограниченное количество объявлений
• Приоритет в поисковых результатах
• Расширенная аналитика и статистика
• Профессиональные шаблоны объявлений
• Поддержка 24/7

Выберите период подписки:
        """,
        'uz':
        f"""
💳 <b>Obuna faol emas</b>

Sizning rolingiz: <b>«{user.role}»</b>
Obuna narxi: <b>{price:,} UZS/oy</b>

🎁 <b>Bepul muddat:</b> {free_days} kun
💎 <b>Bepul muddat tugagandan so'ng:</b> {price:,} UZS/oy

<b>Obunaga nima kiritilgan:</b>
• Cheklanmagan miqdorda e'lon
• Qidiruv natijalarida ustuvorlik
• Kengaytirilgan tahlil va statistika
• E'lonlar uchun professional shablonlar
• 24/7 qo'llab-quvvatlash

Obuna muddatini tanlang:
        """,
        'en':
        f"""
💳 <b>Subscription not active</b>

Your role: <b>«{user.role}»</b>
Subscription cost: <b>{price:,} UZS/month</b>

🎁 <b>Free trial:</b> {free_days} days
💎 <b>After free trial:</b> {price:,} UZS/month

<b>What's included in subscription:</b>
• Unlimited number of listings
• Priority in search results
• Extended analytics and statistics
• Professional listing templates
• 24/7 support

Choose subscription period:
        """
    }

    await message.answer(subscription_texts[user.language],
                         reply_markup=Keyboards.get_subscription_plans(
                             user.role, user.language),
                         parse_mode='HTML')


async def show_active_subscription(message: Message, user: User,
                                   subscription: Subscription):
    """
    Показ информации об активной подписке
    """
    days_left = (user.subscription_end - datetime.now()).days
    total_days = (user.subscription_end - user.subscription_start).days
    used_days = total_days - days_left

    # Расчет прогресса использования подписки
    progress_percent = min(100, int((used_days / total_days) * 100))
    progress_bar = "🟩" * (progress_percent //
                          10) + "⬜" * (10 - (progress_percent // 10))

    active_texts = {
        'ru':
        f"""
✅ <b>Подписка активна</b>

👤 Роль: <b>{user.role}</b>
📅 Начало: {user.subscription_start.strftime('%d.%m.%Y')}
⏳ Окончание: {user.subscription_end.strftime('%d.%m.%Y')}
📊 Прогресс: {progress_bar} {progress_percent}%

⏰ <b>Осталось дней:</b> {days_left}
📈 <b>Использовано:</b> {used_days} из {total_days} дней

💳 <b>Тарифный план:</b> {subscription.plan}
💰 <b>Стоимость продления:</b> {Config.PRICES.get(user.role, 0):,} UZS/месяц

<b>Доступные действия:</b>
        """,
        'uz':
        f"""
✅ <b>Obuna faol</b>

👤 Rol: <b>{user.role}</b>
📅 Boshlanish: {user.subscription_start.strftime('%d.%m.%Y')}
⏳ Tugash: {user.subscription_end.strftime('%d.%m.%Y')}
📊 Progress: {progress_bar} {progress_percent}%

⏰ <b>Qolgan kunlar:</b> {days_left}
📈 <b>Ishlatilgan:</b> {used_days} dan {total_days} kun

💳 <b>Tarif rejasi:</b> {subscription.plan}
💰 <b>Yangi narx:</b> {Config.PRICES.get(user.role, 0):,} UZS/oy

<b>Mavjud amallar:</b>
        """,
        'en':
        f"""
✅ <b>Subscription active</b>

👤 Role: <b>{user.role}</b>
📅 Start: {user.subscription_start.strftime('%d.%m.%Y')}
⏳ End: {user.subscription_end.strftime('%d.%m.%Y')}
📊 Progress: {progress_bar} {progress_percent}%

⏰ <b>Days left:</b> {days_left}
📈 <b>Used:</b> {used_days} of {total_days} days

💳 <b>Plan:</b> {subscription.plan}
💰 <b>Renewal cost:</b> {Config.PRICES.get(user.role, 0):,} UZS/month

<b>Available actions:</b>
        """
    }

    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="🔄 Продлить",
                                   callback_data="renew_subscription"))
    keyboard.add(
        types.InlineKeyboardButton(text="📊 История платежей",
                                   callback_data="payment_history"))
    keyboard.add(
        types.InlineKeyboardButton(text="ℹ️ Информация",
                                   callback_data="subscription_info"))

    if days_left <= 7:  # Если осталось меньше недели
        keyboard.add(
            types.InlineKeyboardButton(text="⚠️ Срочное продление",
                                       callback_data="urgent_renew"))

    keyboard.adjust(2)

    await message.answer(active_texts[user.language],
                         reply_markup=keyboard.as_markup(),
                         parse_mode='HTML')


# ========== ВЫБОР ПЛАНА ПОДПИСКИ ==========


@router.callback_query(F.data.startswith("upgrade_to_"))
async def process_upgrade_to_paid_role(callback: CallbackQuery):
    """
    Обработка перехода на платную роль
    """
    role = callback.data.split('_')[2]  # upgrade_to_риэлтор -> риэлтор
    user = db.get_user(callback.from_user.id)

    # Обновляем роль пользователя
    success = db.update_user_role(callback.from_user.id, role)

    if not success:
        error_texts = {
            'ru': "❌ Ошибка при смене роли. Попробуйте снова.",
            'uz': "❌ Rolni o'zgartirishda xato. Qayta urinib ko'ring.",
            'en': "❌ Error changing role. Please try again."
        }
        await callback.message.answer(error_texts[user.language])
        return

    # Обновляем объект пользователя
    user = db.get_user(callback.from_user.id)
    price = Config.PRICES.get(role, 0)

    upgrade_texts = {
        'ru':
        f"""
✅ <b>Роль успешно изменена!</b>

Теперь вы: <b>«{role}»</b>

🎁 <b>Бесплатный период:</b> {Config.FREE_DAYS.get(role, 0)} дней
💎 <b>После бесплатного периода:</b> {price:,} UZS/месяц

Выберите период подписки для активации всех функций:
        """,
        'uz':
        f"""
✅ <b>Rol muvaffaqiyatli o'zgartirildi!</b>

Endi siz: <b>«{role}»</b>

🎁 <b>Bepul muddat:</b> {Config.FREE_DAYS.get(role, 0)} kun
💎 <b>Bepul muddat tugagandan so'ng:</b> {price:,} UZS/oy

Barcha funksiyalarni faollashtirish uchun obuna muddatini tanlang:
        """,
        'en':
        f"""
✅ <b>Role successfully changed!</b>

Now you are: <b>«{role}»</b>

🎁 <b>Free trial:</b> {Config.FREE_DAYS.get(role, 0)} days
💎 <b>After free trial:</b> {price:,} UZS/month

Choose subscription period to activate all features:
        """
    }

    await callback.message.edit_text(
        upgrade_texts[user.language],
        reply_markup=Keyboards.get_subscription_plans(role, user.language),
        parse_mode='HTML')


@router.callback_query(F.data.startswith("sub_"))
async def process_subscription_plan(callback: CallbackQuery,
                                    state: FSMContext):
    """
    Обработка выбора плана подписки
    """
    # sub_риэлтор_1month -> риэлтор, 1month
    parts = callback.data.split('_')
    role = parts[1]
    plan = parts[2]

    user = db.get_user(callback.from_user.id)

    # Проверяем, совпадает ли роль пользователя с выбранной
    if user.role != role:
        error_texts = {
            'ru':
            "❌ Ошибка: ваша текущая роль не соответствует выбранной подписке.",
            'uz': "❌ Xato: joriy rolingiz tanlangan obunaga mos kelmaydi.",
            'en':
            "❌ Error: your current role doesn't match selected subscription."
        }
        await callback.message.answer(error_texts[user.language])
        return

    price = Config.PRICES.get(role, 0)

    # Расчет стоимости в зависимости от плана
    plan_prices = {
        '1month': price,
        '3months': price * 3 * 0.9,  # 10% скидка
        '6months': price * 6 * 0.8,  # 20% скидка
        '1year': price * 12 * 0.7,  # 30% скидка
        'percentage': 0  # Процент от сделки - отдельная логика
    }

    plan_durations = {
        '1month': 30,
        '3months': 90,
        '6months': 180,
        '1year': 365,
        'percentage': 30  # Для процентного плана - базовый период
    }

    if plan == 'percentage':
        await handle_percentage_plan(callback, user)
        return

    amount = plan_prices[plan]
    duration_days = plan_durations[plan]

    # Сохраняем данные о платеже в состоянии
    await state.update_data(role=role,
                            plan=plan,
                            amount=amount,
                            duration_days=duration_days)

    # Показываем подтверждение и реквизиты для оплаты
    await show_payment_instructions(callback, user, role, plan, amount,
                                    duration_days)


async def handle_percentage_plan(callback: CallbackQuery, user: User):
    """
    Обработка выбора плана "Процент от сделки"
    """
    percentage_texts = {
        'ru':
        f"""
🤝 <b>Тариф «Процент от сделки»</b>

Для роли <b>«{user.role}»</b> доступен специальный тарифный план.

<b>Как это работает:</b>
• Вы платите только при успешной сделке
• Стандартная комиссия: 2% от суммы сделки
• Минимальная комиссия: 50,000 UZS
• Максимальная комиссия: 500,000 UZS

<b>Условия:</b>
• Сделка должна быть заключена через нашу платформу
• Обе стороны подтверждают факт сделки
• Комиссия списывается после получения платежа

Для подключения этого тарифа свяжитесь с администратором: @Jamshid
        """,
        'uz':
        f"""
🤝 <b>«Bitim foizi» tarifi</b>

<b>«{user.role}»</b> roli uchun maxsus tarif rejasi mavjud.

<b>Bu qanday ishlaydi:</b>
• Faqat muvaffaqiyatli bitim bo'lganda to'laysiz
• Standart komissiya: bitim summasi 2%
• Minimal komissiya: 50,000 UZS
• Maksimal komissiya: 500,000 UZS

<b>Shartlar:</b>
• Bitim platformamiz orqali tuzilishi kerak
• Ikkala tomon bitim faktini tasdiqlaydi
• Komissiya to'lov qabul qilingandan keyin hisobdan chiqariladi

Ushbu tarifni ulash uchun administrator bilan bog'laning: @Jamshid
        """,
        'en':
        f"""
🤝 <b>«Percentage of Deal» Plan</b>

Special tariff plan available for <b>«{user.role}»</b> role.

<b>How it works:</b>
• You pay only for successful deals
• Standard commission: 2% of deal amount
• Minimum commission: 50,000 UZS
• Maximum commission: 500,000 UZS

<b>Conditions:</b>
• Deal must be made through our platform
• Both parties confirm the deal fact
• Commission is deducted after payment receipt

To connect this tariff, contact administrator: @Jamshid
        """
    }

    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="💬 Написать админу",
                                   url=f"tg://user?id={Config.ADMIN_ID}"))
    keyboard.add(
        types.InlineKeyboardButton(text="↩️ Назад",
                                   callback_data="back_to_subscription"))

    await callback.message.edit_text(percentage_texts[user.language],
                                     reply_markup=keyboard.as_markup(),
                                     parse_mode='HTML')


async def show_payment_instructions(callback: CallbackQuery, user: User,
                                    role: str, plan: str, amount: float,
                                    duration_days: int):
    """
    Показ инструкций по оплате
    """
    plan_names = {
        '1month': {
            'ru': '1 месяц',
            'uz': '1 oy',
            'en': '1 month'
        },
        '3months': {
            'ru': '3 месяца',
            'uz': '3 oy',
            'en': '3 months'
        },
        '6months': {
            'ru': '6 месяцев',
            'uz': '6 oy',
            'en': '6 months'
        },
        '1year': {
            'ru': '1 год',
            'uz': '1 yil',
            'en': '1 year'
        }
    }

    payment_texts = {
        'ru':
        f"""
💳 <b>Оплата подписки</b>

👤 Роль: <b>{role}</b>
📅 План: <b>{plan_names[plan]['ru']}</b>
💰 Сумма: <b>{amount:,.0f} UZS</b>
⏳ Срок: <b>{duration_days} дней</b>

<b>Реквизиты для перевода:</b>

🏦 <b>Банк:</b> Kapital Bank
💳 <b>Номер карты:</b> <code>8600 12** **** 1234</code>
👤 <b>Получатель:</b> Jamshid
📝 <b>Назначение:</b> Подписка {role}

<b>Инструкция:</b>
1. Выполните перевод на указанные реквизиты
2. Сохраните скриншот чека или квитанции
3. Отправьте скриншот в этот чат
4. Ожидайте подтверждения администратора

Обычно подтверждение занимает до 24 часов.
        """,
        'uz':
        f"""
💳 <b>Obunani to'lash</b>

👤 Rol: <b>{role}</b>
📅 Reja: <b>{plan_names[plan]['uz']}</b>
💰 Summa: <b>{amount:,.0f} UZS</b>
⏳ Muddati: <b>{duration_days} kun</b>

<b>O'tkazma uchun rekvizitlar:</b>

🏦 <b>Bank:</b> Kapital Bank
💳 <b>Karta raqami:</b> <code>8600 12** **** 1234</code>
👤 <b>Qabul qiluvchi:</b> Jamshid
📝 <b>Maqsadi:</b> Obuna {role}

<b>Ko'rsatma:</b>
1. Ko'rsatilgan rekvizitlarga o'tkazma bajaring
2. Chek yoki kvitansiya skrinshotini saqlang
3. Skrinshotni ushbu chatga yuboring
4. Administrator tasdigini kuting

Odatda tasdiqlash 24 soatgacha vaqt oladi.
        """,
        'en':
        f"""
💳 <b>Subscription Payment</b>

👤 Role: <b>{role}</b>
📅 Plan: <b>{plan_names[plan]['en']}</b>
💰 Amount: <b>{amount:,.0f} UZS</b>
⏳ Duration: <b>{duration_days} days</b>

<b>Transfer details:</b>

🏦 <b>Bank:</b> Kapital Bank
💳 <b>Card number:</b> <code>8600 12** **** 1234</code>
👤 <b>Recipient:</b> Jamshid
📝 <b>Purpose:</b> Subscription {role}

<b>Instructions:</b>
1. Make transfer to specified details
2. Save screenshot of receipt or check
3. Send screenshot to this chat
4. Wait for administrator confirmation

Confirmation usually takes up to 24 hours.
        """
    }

    # Создаем запись о платеже в базе данных
    payment_id = db.create_payment(user_id=user.id,
                                   amount=amount,
                                   description=f"Подписка {role} - {plan}",
                                   plan=plan,
                                   role=role)

    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(
            text="📸 Отправить скриншот",
            callback_data=f"upload_receipt_{payment_id}"))
    keyboard.add(
        types.InlineKeyboardButton(text="💬 Помощь",
                                   callback_data="payment_help"))
    keyboard.add(
        types.InlineKeyboardButton(text="↩️ Отмена",
                                   callback_data="cancel_payment"))

    await callback.message.edit_text(payment_texts[user.language],
                                     reply_markup=keyboard.as_markup(),
                                     parse_mode='HTML')


# ========== ОБРАБОТКА ПЛАТЕЖЕЙ ==========


@router.callback_query(F.data.startswith("upload_receipt_"))
async def process_upload_receipt(callback: CallbackQuery, state: FSMContext):
    """
    Начало процесса загрузки скриншота чека
    """
    payment_id = int(callback.data.split('_')[2])
    user = db.get_user(callback.from_user.id)

    await state.update_data(payment_id=payment_id)

    upload_texts = {
        'ru': "📸 Пожалуйста, отправьте скриншот чека или квитанции об оплате:",
        'uz':
        "📸 Iltimos, to'lov cheki yoki kvitansiyasining skrinshotini yuboring:",
        'en': "📸 Please send screenshot of payment receipt or check:"
    }

    await callback.message.edit_text(upload_texts[user.language])
    await state.set_state(PaymentStates.waiting_for_receipt)


@router.message(PaymentStates.waiting_for_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext):
    """
    Обработка загруженного скриншота чека
    """
    data = await state.get_data()
    payment_id = data.get('payment_id')
    user = db.get_user(message.from_user.id)

    if not payment_id:
        error_texts = {
            'ru':
            "❌ Ошибка: данные платежа не найдены. Начните процесс заново.",
            'uz':
            "❌ Xato: to'lov ma'lumotlari topilmadi. Jarayoni qayta boshlang.",
            'en': "❌ Error: payment data not found. Start the process again."
        }
        await message.answer(error_texts[user.language])
        await state.clear()
        return

    # Сохраняем фото чека
    receipt_photo_id = message.photo[-1].file_id
    db.update_payment_receipt(payment_id, receipt_photo_id)

    # Уведомляем администратора
    await notify_admin_about_payment(payment_id, user, receipt_photo_id)

    confirmation_texts = {
        'ru':
        """
✅ <b>Скриншот чека получен!</b>

Мы отправили уведомление администратору для проверки платежа.

Обычно проверка занимает до 24 часов. Мы уведомим вас, как только подписка будет активирована.

<b>Что делать дальше:</b>
• Ожидайте подтверждения платежа
• После подтверждения ваша подписка будет автоматически активирована
• Вы получите уведомление о успешной активации

Спасибо за ваш платеж! 💫
        """,
        'uz':
        """
✅ <b>Chek skrinshoti qabul qilindi!</b>

Biz to'lovni tekshirish uchun administratorga bildirishnoma yubordik.

Odatda tekshirish 24 soatgacha vaqt oladi. Obuna faollashtirilganda sizni xabardor qilamiz.

<b>Keyin nima qilish kerak:</b>
• To'lov tasdiqlanishini kuting
• Tasdiqlangandan so'ng obunangiz avtomatik ravishda faollashtiriladi
• Muvaffaqiyatli faollashtirish haqida bildirishnoma olasiz

To'lovingiz uchun rahmat! 💫
        """,
        'en':
        """
✅ <b>Receipt screenshot received!</b>

We have sent notification to administrator for payment verification.

Verification usually takes up to 24 hours. We will notify you once subscription is activated.

<b>What to do next:</b>
• Wait for payment confirmation
• After confirmation your subscription will be automatically activated
• You will receive notification about successful activation

Thank you for your payment! 💫
        """
    }

    await message.answer(confirmation_texts[user.language], parse_mode='HTML')
    await state.clear()


@router.callback_query(F.data == "payment_help")
async def process_payment_help(callback: CallbackQuery):
    """
    Помощь по оплате
    """
    user = db.get_user(callback.from_user.id)

    help_texts = {
        'ru':
        """
🆘 <b>Помощь по оплате</b>

<b>Частые вопросы:</b>

❓ <b>Как сделать перевод?</b>
• Откройте приложение вашего банка
• Выберите перевод по номеру карты
• Введите номер карты: <code>8600 12** **** 1234</code>
• Укажите сумму и назначение платежа

❓ <b>Что делать если перевод не проходит?</b>
• Проверьте правильность номера карты
• Убедитесь, что на карте достаточно средств
• Попробуйте сделать перевод через несколько минут

❓ <b>Скриншот не отправляется?</b>
• Убедитесь, что отправляете именно фото (не файл)
• Размер фото не должен превышать 10MB
• Можно отправить несколько фото если чек не помещается в одном

❓ <b>Долго нет подтверждения?</b>
• Обычно проверка занимает до 24 часов
• В выходные дни проверка может занять больше времени
• Если прошло более 24 часов, свяжитесь с администратором

<b>Техническая поддержка:</b> @Jamshid
        """,
        'uz':
        """
🆘 <b>To'lov bo'yicha yordam</b>

<b>Tez-tez beriladigan savollar:</b>

❓ <b>O'tkazma qanday qilish kerak?</b>
• Bank ilovangizni oching
• Karta raqami bo'yicha o'tkazmani tanlang
• Karta raqamini kiriting: <code>8600 12** **** 1234</code>
• Summa va to'lov maqsadini ko'rsating

❓ <b>Agar o'tkazma amalga oshmasa nima qilish kerak?</b>
• Karta raqami to'g'riligini tekshiring
• Kartada yetarli mablag' borligiga ishonch hosil qiling
• Bir necha daqiqadan keyin o'tkazma qilishni urinib ko'ring

❓ <b>Skrinshot yuborilmayaptimi?</b>
• Aynan fotosurat yuborayotganingizga ishonch hosil qiling (fayl emas)
• Fotosurat hajmi 10MB dan oshmasligi kerak
• Agar chek bittaga sig'masa, bir nechta fotosurat yuborishingiz mumkin

❓ <b>Tasdiq uzoq vaqt kutilyaptimi?</b>
• Odatda tekshirish 24 soatgacha vaqt oladi
• Dam olish kunlarida tekshirish ko'proq vaqt olishi mumkin
• Agar 24 soatdan oshib ketgan bo'lsa, administrator bilan bog'laning

<b>Texnik qo'llab-quvvatlash:</b> @Jamshid
        """,
        'en':
        """
🆘 <b>Payment Help</b>

<b>Frequently asked questions:</b>

❓ <b>How to make transfer?</b>
• Open your bank application
• Choose transfer by card number
• Enter card number: <code>8600 12** **** 1234</code>
• Specify amount and payment purpose

❓ <b>What if transfer fails?</b>
• Check card number correctness
• Make sure there are sufficient funds on the card
• Try to make transfer after few minutes

❓ <b>Screenshot not sending?</b>
• Make sure you are sending photo (not file)
• Photo size should not exceed 10MB
• You can send multiple photos if receipt doesn't fit in one

❓ <b>No confirmation for long time?</b>
• Verification usually takes up to 24 hours
• On weekends verification may take more time
• If more than 24 hours passed, contact administrator

<b>Technical support:</b> @Jamshid
        """
    }

    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="💬 Написать админу",
                                   url=f"tg://user?id={Config.ADMIN_ID}"))
    keyboard.add(
        types.InlineKeyboardButton(text="↩️ Назад",
                                   callback_data="back_to_payment"))

    await callback.message.edit_text(help_texts[user.language],
                                     reply_markup=keyboard.as_markup(),
                                     parse_mode='HTML')


# ========== УВЕДОМЛЕНИЯ АДМИНИСТРАТОРУ ==========


async def notify_admin_about_payment(payment_id: int, user: User,
                                     receipt_photo_id: str):
    """
    Уведомление администратора о новом платеже
    """
    try:
        from main import bot

        payment = db.get_payment_by_id(payment_id)

        admin_text = f"""
💸 <b>Новый платеж на проверку</b>

ID платежа: <code>{payment_id}</code>
👤 Пользователь: {user.first_name} (@{user.username})
💰 Сумма: {payment.amount:,.0f} UZS
👤 Роль: {payment.role}
📅 План: {payment.plan}
📝 Описание: {payment.description}

Для проверки используйте команду /payments
        """

        # Отправляем фото чека администратору
        await bot.send_photo(chat_id=Config.ADMIN_ID,
                             photo=receipt_photo_id,
                             caption=admin_text,
                             parse_mode='HTML')

    except Exception as e:
        logging.error(f"Ошибка уведомления админа о платеже: {e}")


# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========


@router.callback_query(F.data == "payment_history")
async def show_payment_history(callback: CallbackQuery):
    """
    Показ истории платежей пользователя
    """
    user = db.get_user(callback.from_user.id)
    payments = db.get_user_payments(user.id)

    if not payments:
        no_history_texts = {
            'ru':
            "📊 <b>История платежей пуста</b>\n\nУ вас еще не было платежей.",
            'uz':
            "📊 <b>To'lovlar tarixi bo'sh</b>\n\nHali sizda to'lovlar bo'lmagan.",
            'en':
            "📊 <b>Payment history is empty</b>\n\nYou haven't had any payments yet."
        }
        await callback.message.answer(no_history_texts[user.language],
                                      parse_mode='HTML')
        return

    history_texts = {
        'ru':
        f"📊 <b>История платежей</b>\n\nВсего платежей: {len(payments)}\n\n",
        'uz':
        f"📊 <b>To'lovlar tarixi</b>\n\nJami to'lovlar: {len(payments)}\n\n",
        'en':
        f"📊 <b>Payment History</b>\n\nTotal payments: {len(payments)}\n\n"
    }

    text = history_texts[user.language]

    for payment in payments[:10]:  # Показываем последние 10 платежей
        status_icons = {
            'pending': '⏳',
            'confirmed': '✅',
            'rejected': '❌',
            'canceled': '🚫'
        }

        status_texts = {
            'pending': 'Ожидает',
            'confirmed': 'Подтвержден',
            'rejected': 'Отклонен',
            'canceled': 'Отменен'
        }

        status_texts_uz = {
            'pending': 'Kutilmoqda',
            'confirmed': 'Tasdiqlangan',
            'rejected': 'Rad etilgan',
            'canceled': 'Bekor qilingan'
        }

        status_texts_en = {
            'pending': 'Pending',
            'confirmed': 'Confirmed',
            'rejected': 'Rejected',
            'canceled': 'Canceled'
        }

        status_dict = status_texts if user.language == 'ru' else (
            status_texts_uz if user.language == 'uz' else status_texts_en)

        text += f"{status_icons.get(payment.status, '📋')} {payment.amount:,.0f} UZS - {status_dict.get(payment.status, payment.status)}\n"
        text += f"📅 {payment.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"📝 {payment.description}\n\n"

    await callback.message.answer(text, parse_mode='HTML')


@router.callback_query(F.data == "subscription_info")
async def show_subscription_info_detailed(callback: CallbackQuery):
    """
    Подробная информация о подписке
    """
    user = db.get_user(callback.from_user.id)

    info_texts = {
        'ru':
        f"""
ℹ️ <b>Информация о подписке</b>

👤 <b>Ваша роль:</b> {user.role}
💰 <b>Стоимость:</b> {Config.PRICES.get(user.role, 0):,} UZS/месяц

<b>Что включено в подписку:</b>
• Неограниченное количество объявлений
• Приоритет в поисковых результатах
• Расширенная аналитика по просмотрам и лидам
• Профессиональные шаблоны объявлений
• Управление бронированиями и показами
• Техническая поддержка 24/7

<b>Автопродление:</b>
• Подписка не продлевается автоматически
• За 7 дней до окончания вы получите уведомление
• Для продления используйте меню «Подписка»

<b>Возврат средств:</b>
• Возврат возможен в течение 3 дней после оплаты
• Для возврата свяжитесь с администратором
• Возврат осуществляется на ту же карту, с которой была оплата

По вопросам работы подписки: @Jamshid
        """,
        'uz':
        f"""
ℹ️ <b>Obuna haqida ma'lumot</b>

👤 <b>Sizning rolingiz:</b> {user.role}
💰 <b>Narx:</b> {Config.PRICES.get(user.role, 0):,} UZS/oy

<b>Obunaga nima kiritilgan:</b>
• Cheklanmagan miqdorda e'lon
• Qidiruv natijalarida ustuvorlik
• Ko'rishlar va lidlar bo'yicha kengaytirilgan tahlil
• E'lonlar uchun professional shablonlar
• Band qilish va ko'rib chiqishlarni boshqarish
• 24/7 texnik qo'llab-quvvatlash

<b>Avtomatik yangilash:</b>
• Obuna avtomatik ravishda yangilanmaydi
• Tugashidan 7 kun oldin siz bildirishnoma olasiz
• Yangilash uchun «Obuna» menyusidan foydalaning

<b>Mablag'larni qaytarish:</b>
• To'lovdan keyin 3 kun ichida mablag'larni qaytarish mumkin
• Qaytarish uchun administrator bilan bog'laning
• To'lov amalga oshirilgan xuddi shu karta orqali qaytariladi

Obuna ishlashi bilan bog'liq savollar: @Jamshid
        """,
        'en':
        f"""
ℹ️ <b>Subscription Information</b>

👤 <b>Your role:</b> {user.role}
💰 <b>Cost:</b> {Config.PRICES.get(user.role, 0):,} UZS/month

<b>What's included in subscription:</b>
• Unlimited number of listings
• Priority in search results
• Extended analytics for views and leads
• Professional listing templates
• Booking and viewing management
• 24/7 technical support

<b>Auto-renewal:</b>
• Subscription doesn't renew automatically
• You will receive notification 7 days before expiration
• Use «Subscription» menu for renewal

<b>Refund:</b>
• Refund is possible within 3 days after payment
• Contact administrator for refund
• Refund is made to the same card used for payment

For subscription issues: @Jamshid
        """
    }

    await callback.message.answer(info_texts[user.language], parse_mode='HTML')


# Экспортируем роутер
__all__ = ['router']

