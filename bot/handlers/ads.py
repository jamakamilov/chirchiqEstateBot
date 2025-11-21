import logging
import re
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database, User, Ad
from keyboards import Keyboards
from states import AdStates
from config import Config
from utils.nlp_processor import NLPProcessor

# Создаем роутер
router = Router()
db = Database()
nlp = NLPProcessor()

# ========== СОЗДАНИЕ ОБЪЯВЛЕНИЙ ==========

@router.message(F.text == "🏠 Добавить объявление")
@router.message(F.text == "🏠 Add New Ad")
@router.message(F.text == "🏠 Yangi e'lon qo'shish")
async def start_ad_creation(message: Message, state: FSMContext):
    """
    Начало процесса создания объявления
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите бота командой /start")
        return

    # Проверяем подписку для платных ролей
    if user.role in ['риэлтор', 'арендатор', 'агентство', 'застройщик']:
        if not user.has_active_subscription():
            subscription_texts = {
                'ru': f"""
❌ <b>Требуется активная подписка</b>

Для размещения объявлений с ролью <b>«{user.role}»</b> необходима активная подписка.

<b>Стоимость подписки:</b> {Config.PRICES.get(user.role, 0):,} UZS/месяц

Используйте меню «Подписка» для активации.
                """,
                'uz': f"""
❌ <b>Faol obuna talab qilinadi</b>

<b>«{user.role}»</b> roli bilan e'lon joylashtirish uchun faol obuna talab qilinadi.

<b>Obuna narxi:</b> {Config.PRICES.get(user.role, 0):,} UZS/oy

Faollashtirish uchun «Obuna» menyusidan foydalaning.
                """,
                'en': f"""
❌ <b>Active subscription required</b>

Active subscription is required to post listings with <b>«{user.role}»</b> role.

<b>Subscription cost:</b> {Config.PRICES.get(user.role, 0):,} UZS/month

Use «Subscription» menu to activate.
                """
            }
            await message.answer(subscription_texts[user.language], parse_mode='HTML')
            return

    # Проверяем ограничения для бесплатных ролей
    if user.role in ['продавец', 'покупатель']:
        active_ads = db.get_active_user_ads(user.id)
        if len(active_ads) >= 5:
            limit_texts = {
                'ru': f"""
❌ <b>Достигнут лимит объявлений</b>

Для бесплатной роли <b>«{user.role}»</b> действует ограничение: 
не более <b>5 активных объявлений</b> одновременно.

<b>Ваши варианты:</b>
• Дождаться истечения срока текущих объявлений (30 дней)
• Удалить одно из текущих объявлений
• Перейти на платную роль для снятия ограничений

Текущие активные объявления: {len(active_ads)}/5
                """,
                'uz': f"""
❌ <b>E'lonlar chegarasiga erishildi</b>

Bepul <b>«{user.role}»</b> roli uchun cheklov mavjud:
bir vaqtning o'zida <b>5 tadan ortiq faol e'lon</b> bo'lmasligi kerak.

<b>Sizning variantlaringiz:</b>
• Joriy e'lonlarning muddati tugashini kutish (30 kun)
• Joriy e'lonlardan birini o'chirish
• Cheklovlarni olib tashlash uchun pulli roliga o'tish

Joriy faol e'lonlar: {len(active_ads)}/5
                """,
                'en': f"""
❌ <b>Listing limit reached</b>

For free role <b>«{user.role}»</b> there is a limit:
no more than <b>5 active listings</b> at the same time.

<b>Your options:</b>
• Wait for current listings to expire (30 days)
• Delete one of current listings
• Upgrade to paid role to remove limitations

Current active listings: {len(active_ads)}/5
                """
            }
            await message.answer(limit_texts[user.language], parse_mode='HTML')
            return

    # Показываем информацию о сроке размещения
    if user.role in ['продавец', 'покупатель']:
        duration_info = {
            'ru': "⚠️ <b>Внимание:</b> Для бесплатной роли объявления размещаются на 30 дней",
            'uz': "⚠️ <b>Diqqat:</b> Bepul rol uchun e'lonlar 30 kun joylashtiriladi",
            'en': "⚠️ <b>Note:</b> For free role listings are posted for 30 days"
        }
        await message.answer(duration_info[user.language], parse_mode='HTML')

    start_texts = {
        'ru': "🏠 <b>Создание нового объявления</b>\n\nВыберите тип недвижимости:",
        'uz': "🏠 <b>Yangi e'lon yaratish</b>\n\nKo'chmas mulk turini tanlang:",
        'en': "🏠 <b>Creating new listing</b>\n\nChoose property type:"
    }

    await message.answer(
        start_texts[user.language],
        reply_markup=Keyboards.get_property_type_keyboard(user.language),
        parse_mode='HTML'
    )
    await state.set_state(AdStates.waiting_for_type)
    await state.update_data(user_id=user.id)

@router.callback_query(AdStates.waiting_for_type, F.data.startswith("type_"))
async def process_ad_type(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора типа недвижимости
    """
    prop_type = callback.data[5:]  # type_аренда -> аренда

    await state.update_data(property_type=prop_type)

    user = db.get_user(callback.from_user.id)

    title_texts = {
        'ru': f"🏷️ Выбран тип: <b>{prop_type}</b>\n\nВведите заголовок объявления (максимум 100 символов):",
        'uz': f"🏷️ Tanlangan tur: <b>{prop_type}</b>\n\nE'lon sarlavhasini kiriting (maksimum 100 belgi):",
        'en': f"🏷️ Selected type: <b>{prop_type}</b>\n\nEnter listing title (maximum 100 characters):"
    }

    await callback.message.edit_text(
        title_texts[user.language],
        parse_mode='HTML'
    )
    await state.set_state(AdStates.waiting_for_title)

@router.message(AdStates.waiting_for_title)
async def process_ad_title(message: Message, state: FSMContext):
    """
    Обработка заголовка объявления
    """
    if len(message.text) > 100:
        error_texts = {
            'ru': "❌ Заголовок слишком длинный. Максимум 100 символов. Введите снова:",
            'uz': "❌ Sarlavha juda uzun. Maksimum 100 belgi. Qayta kiriting:",
            'en': "❌ Title is too long. Maximum 100 characters. Enter again:"
        }
        user = db.get_user(message.from_user.id)
        await message.answer(error_texts[user.language])
        return

    await state.update_data(title=message.text)

    description_texts = {
        'ru': "📝 Введите подробное описание объявления:\n\n<em>Рекомендуем указать:\n• Площадь и планировку\n• Состояние и ремонт\n• Удобства и инфраструктуру\n• Контактную информацию</em>",
        'uz': "📝 E'lonning batafsil tavsifini kiriting:\n\n<em>Tavsiya etiladi:\n• Maydon va reja\n• Holat va ta'mirlash\n• Qulayliklar va infratuzilma\n• Aloqa ma'lumotlari</em>",
        'en': "📝 Enter detailed listing description:\n\n<em>We recommend specifying:\n• Area and layout\n• Condition and renovation\n• Amenities and infrastructure\n• Contact information</em>"
    }

    user = db.get_user(message.from_user.id)
    await message.answer(description_texts[user.language], parse_mode='HTML')
    await state.set_state(AdStates.waiting_for_description)

@router.message(AdStates.waiting_for_description)
async def process_ad_description(message: Message, state: FSMContext):
    """
    Обработка описания объявления с NLP анализом
    """
    user = db.get_user(message.from_user.id)

    # NLP анализ описания
    analysis_result = nlp.analyze_description(message.text)
    extracted_price = analysis_result.get('price')

    if analysis_result['issues']:
        issues_text = "\n".join([f"• {issue}" for issue in analysis_result['issues']])
        suggestions_text = "\n".join([f"• {suggestion}" for suggestion in analysis_result['suggestions']])

        analysis_message = {
            'ru': f"""
🔍 <b>Анализ описания:</b>

<b>Выявленные проблемы:</b>
{issues_text}

<b>Рекомендации:</b>
{suggestions_text}

Хотите исправить описание или продолжить?
            """,
            'uz': f"""
🔍 <b>Tavsif tahlili:</b>

<b>Aniqlangan muammolar:</b>
{issues_text}

<b>Tavsiyalar:</b>
{suggestions_text}

Tavsifni tuzatmoqchimisiz yoki davom ettirmoqchimisiz?
            """,
            'en': f"""
🔍 <b>Description analysis:</b>

<b>Identified issues:</b>
{issues_text}

<b>Recommendations:</b>
{suggestions_text}

Do you want to fix description or continue?
            """
        }

        keyboard = InlineKeyboardBuilder()
        keyboard.add(types.InlineKeyboardButton(text="✏️ Исправить", callback_data="edit_description"))
        keyboard.add(types.InlineKeyboardButton(text="➡️ Продолжить", callback_data="continue_description"))

        await message.answer(
            analysis_message[user.language],
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )

        await state.update_data(
            description=message.text,
            extracted_price=extracted_price,
            analysis_result=analysis_result
        )
        return

    await state.update_data(description=message.text)

    # Если цена была извлечена из описания, предлагаем использовать ее
    if extracted_price:
        price_texts = {
            'ru': f"""
💰 В описании найдена цена: <b>{extracted_price:,} {user.currency.upper()}</b>

Хотите использовать эту цену?
            """,
            'uz': f"""
💰 Tavsifda narx topildi: <b>{extracted_price:,} {user.currency.upper()}</b>

Ushbu narxdan foydalanmoqchimisiz?
            """,
            'en': f"""
💰 Price found in description: <b>{extracted_price:,} {user.currency.upper()}</b>

Do you want to use this price?
            """
        }

        keyboard = InlineKeyboardBuilder()
        keyboard.add(types.InlineKeyboardButton(text="✅ Да", callback_data="use_extracted_price"))
        keyboard.add(types.InlineKeyboardButton(text="✏️ Ввести другую", callback_data="enter_custom_price"))

        await message.answer(
            price_texts[user.language],
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )
    else:
        price_texts = {
            'ru': "💰 Введите цену (только числа):",
            'uz': "💰 Narxni kiriting (faqat raqamlar):",
            'en': "💰 Enter price (numbers only):"
        }
        await message.answer(price_texts[user.language])
        await state.set_state(AdStates.waiting_for_price)

@router.callback_query(F.data == "edit_description")
async def process_edit_description(callback: CallbackQuery, state: FSMContext):
    """
    Редактирование описания после анализа
    """
    user = db.get_user(callback.from_user.id)

    edit_texts = {
        'ru': "✏️ Введите исправленное описание:",
        'uz': "✏️ Tuzatilgan tavsifni kiriting:",
        'en': "✏️ Enter corrected description:"
    }

    await callback.message.edit_text(edit_texts[user.language])
    await state.set_state(AdStates.waiting_for_description)

@router.callback_query(F.data == "continue_description")
async def process_continue_description(callback: CallbackQuery, state: FSMContext):
    """
    Продолжение без редактирования описания
    """
    data = await state.get_data()
    extracted_price = data.get('extracted_price')
    user = db.get_user(callback.from_user.id)

    if extracted_price:
        price_texts = {
            'ru': f"💰 Используем найденную цену: <b>{extracted_price:,} {user.currency.upper()}</b>\n\nВведите местоположение:",
            'uz': f"💰 Topilgan narxdan foydalanamiz: <b>{extracted_price:,} {user.currency.upper()}</b>\n\nJoylashuvni kiriting:",
            'en': f"💰 Using found price: <b>{extracted_price:,} {user.currency.upper()}</b>\n\nEnter location:"
        }
        await callback.message.edit_text(price_texts[user.language], parse_mode='HTML')
        await state.update_data(price=extracted_price)
        await state.set_state(AdStates.waiting_for_location)
    else:
        price_texts = {
            'ru': "💰 Введите цену (только числа):",
            'uz': "💰 Narxni kiriting (faqat raqamlar):",
            'en': "💰 Enter price (numbers only):"
        }
        await callback.message.edit_text(price_texts[user.language])
        await state.set_state(AdStates.waiting_for_price)

@router.callback_query(F.data == "use_extracted_price")
async def process_use_extracted_price(callback: CallbackQuery, state: FSMContext):
    """
    Использование цены, извлеченной из описания
    """
    data = await state.get_data()
    extracted_price = data.get('extracted_price')
    user = db.get_user(callback.from_user.id)

    await state.update_data(price=extracted_price)

    location_texts = {
        'ru': f"✅ Цена установлена: <b>{extracted_price:,} {user.currency.upper()}</b>\n\n📍 Введите местоположение (адрес или район):",
        'uz': f"✅ Narx o'rnatildi: <b>{extracted_price:,} {user.currency.upper()}</b>\n\n📍 Joylashuvni kiriting (manzil yoki tuman):",
        'en': f"✅ Price set: <b>{extracted_price:,} {user.currency.upper()}</b>\n\n📍 Enter location (address or district):"
    }

    await callback.message.edit_text(location_texts[user.language], parse_mode='HTML')
    await state.set_state(AdStates.waiting_for_location)

@router.callback_query(F.data == "enter_custom_price")
async def process_enter_custom_price(callback: CallbackQuery, state: FSMContext):
    """
    Ввод собственной цены
    """
    user = db.get_user(callback.from_user.id)

    price_texts = {
        'ru': "💰 Введите цену (только числа):",
        'uz': "💰 Narxni kiriting (faqat raqamlar):",
        'en': "💰 Enter price (numbers only):"
    }

    await callback.message.edit_text(price_texts[user.language])
    await state.set_state(AdStates.waiting_for_price)

@router.message(AdStates.waiting_for_price)
async def process_ad_price(message: Message, state: FSMContext):
    """
    Обработка ввода цены
    """
    try:
        # Очищаем цену от пробелов и запятых
        price_text = message.text.replace(' ', '').replace(',', '')
        price = float(price_text)

        if price <= 0:
            raise ValueError("Price must be positive")

        await state.update_data(price=price)

        user = db.get_user(message.from_user.id)

        location_texts = {
            'ru': f"✅ Цена установлена: <b>{price:,} {user.currency.upper()}</b>\n\n📍 Введите местоположение (адрес или район):",
            'uz': f"✅ Narx o'rnatildi: <b>{price:,} {user.currency.upper()}</b>\n\n📍 Joylashuvni kiriting (manzil yoki tuman):",
            'en': f"✅ Price set: <b>{price:,} {user.currency.upper()}</b>\n\n📍 Enter location (address or district):"
        }

        await message.answer(location_texts[user.language], parse_mode='HTML')
        await state.set_state(AdStates.waiting_for_location)

    except ValueError:
        error_texts = {
            'ru': "❌ Неверный формат цены. Введите только числа (например: 50000 или 1500000):",
            'uz': "❌ Noto'g'ri narx formati. Faqat raqamlarni kiriting (masalan: 50000 yoki 1500000):",
            'en': "❌ Invalid price format. Enter numbers only (e.g.: 50000 or 1500000):"
        }
        user = db.get_user(message.from_user.id)
        await message.answer(error_texts[user.language])

@router.message(AdStates.waiting_for_location)
async def process_ad_location(message: Message, state: FSMContext):
    """
    Обработка ввода местоположения
    """
    await state.update_data(location=message.text)

    user = db.get_user(message.from_user.id)

    photos_texts = {
        'ru': "📸 Теперь отправьте фотографии объекта (максимум 10):\n\nНапишите «Готово» когда закончите.",
        'uz': "📸 Endi ob'ektning fotosuratlarini yuboring (maksimum 10):\n\nTugatganingizda «Tayyor» deb yozing.",
        'en': "📸 Now send property photos (maximum 10):\n\nWrite «Done» when finished."
    }

    # Инициализируем список фото в состоянии
    await state.update_data(photos=[])

    await message.answer(photos_texts[user.language])
    await state.set_state(AdStates.waiting_for_photos)

@router.message(AdStates.waiting_for_photos, F.photo)
async def process_ad_photos(message: Message, state: FSMContext):
    """
    Обработка загрузки фотографий
    """
    data = await state.get_data()
    photos = data.get('photos', [])

    # Сохраняем file_id самого большого фото (последний элемент в списке размеров)
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)

    user = db.get_user(message.from_user.id)

    if len(photos) >= 10:
        limit_texts = {
            'ru': "✅ Достигнут лимит в 10 фото. Создаем предпросмотр...",
            'uz': "✅ 10 ta fotosurat chegarasiga erishildi. Oldindan ko'rish yaratilmoqda...",
            'en': "✅ Reached limit of 10 photos. Creating preview..."
        }
        await message.answer(limit_texts[user.language])
        await show_ad_preview(message, state)
    else:
        count_texts = {
            'ru': f"✅ Фото добавлено ({len(photos)}/10). Отправьте еще или напишите «Готово».",
            'uz': f"✅ Fotosurat qo'shildi ({len(photos)}/10). Yana yuboring yoki «Tayyor» deb yozing.",
            'en': f"✅ Photo added ({len(photos)}/10). Send more or write «Done»."
        }
        await message.answer(count_texts[user.language])

@router.message(AdStates.waiting_for_photos, F.text.in_(["Готово", "Tayyor", "Done"]))
async def finish_ad_photos(message: Message, state: FSMContext):
    """
    Завершение загрузки фотографий
    """
    data = await state.get_data()
    photos = data.get('photos', [])
    user = db.get_user(message.from_user.id)

    if not photos:
        no_photos_texts = {
            'ru': "⚠️ Фото не добавлены. Продолжаем без фото.",
            'uz': "⚠️ Fotosuratlar qo'shilmadi. Fotosuratsiz davom etamiz.",
            'en': "⚠️ No photos added. Continuing without photos."
        }
        await message.answer(no_photos_texts[user.language])

    await show_ad_preview(message, state)

async def show_ad_preview(message: Message, state: FSMContext):
    """
    Показ предпросмотра объявления перед отправкой
    """
    data = await state.get_data()
    user = db.get_user(message.from_user.id)

    # Формируем текст предпросмотра
    preview_text = f"""
📋 <b>Предпросмотр объявления</b>

🏷️ <b>Тип:</b> {data['property_type']}
📝 <b>Заголовок:</b> {data['title']}
📄 <b>Описание:</b> {data['description']}
💰 <b>Цена:</b> {data['price']:,.0f} {user.currency.upper()}
📍 <b>Местоположение:</b> {data['location']}
📸 <b>Фото:</b> {len(data.get('photos', []))} шт.

👤 <b>Ваша роль:</b> {user.role}
    """

    # Добавляем информацию о сроке размещения для бесплатных ролей
    if user.role in ['продавец', 'покупатель']:
        preview_text += "\n\n⚠️ <b>Для бесплатной роли:</b> Объявление будет размещено на 30 дней"

    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="✅ Отправить на модерацию", callback_data="submit_ad"))
    keyboard.add(types.InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_ad"))
    keyboard.add(types.InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_ad"))
    keyboard.adjust(1)

    photos = data.get('photos', [])

    if photos:
        # Отправляем первое фото с подписью
        await message.answer_photo(
            photos[0],
            caption=preview_text,
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )
    else:
        await message.answer(
            preview_text,
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )

    await state.set_state(AdStates.preview)

@router.callback_query(AdStates.preview, F.data == "submit_ad")
async def process_ad_submission(callback: CallbackQuery, state: FSMContext):
    """
    Отправка объявления на модерацию
    """
    data = await state.get_data()
    user = db.get_user(callback.from_user.id)

    # Создаем объявление в базе данных
    ad_id = db.create_ad(user.id, {
        'type': data['property_type'],
        'title': data['title'],
        'description': data['description'],
        'price': data['price'],
        'currency': user.currency,
        'location': data['location'],
        'photos': data.get('photos', [])
    })

    submission_texts = {
        'ru': f"""
✅ <b>Объявление отправлено на модерацию!</b>

🏠 <b>{data['title']}</b>
💰 {data['price']:,.0f} {user.currency.upper()}
📍 {data['location']}

Мы проверим ваше объявление и уведомим вас о результате. Обычно это занимает до 24 часов.
        """,
        'uz': f"""
✅ <b>E'lon moderatsiya uchun yuborildi!</b>

🏠 <b>{data['title']}</b>
💰 {data['price']:,.0f} {user.currency.upper()}
📍 {data['location']}

Sizning e'loningizni tekshiramiz va natija haqida sizni xabardor qilamiz. Odatda 24 soatgacha vaqt oladi.
        """,
        'en': f"""
✅ <b>Listing submitted for moderation!</b>

🏠 <b>{data['title']}</b>
💰 {data['price']:,.0f} {user.currency.upper()}
📍 {data['location']}

We will check your listing and notify you about the result. It usually takes up to 24 hours.
        """
    }

    await callback.message.edit_text(submission_texts[user.language], parse_mode='HTML')

    # Уведомляем администратора о новом объявлении
    await notify_admin_about_new_ad(ad_id)

    await state.clear()

@router.callback_query(AdStates.preview, F.data == "edit_ad")
async def process_edit_ad(callback: CallbackQuery, state: FSMContext):
    """
    Редактирование объявления перед отправкой
    """
    user = db.get_user(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="🏷️ Тип", callback_data="edit_field_type"))
    keyboard.add(types.InlineKeyboardButton(text="📝 Заголовок", callback_data="edit_field_title"))
    keyboard.add(types.InlineKeyboardButton(text="📄 Описание", callback_data="edit_field_description"))
    keyboard.add(types.InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price"))
    keyboard.add(types.InlineKeyboardButton(text="📍 Местоположение", callback_data="edit_field_location"))
    keyboard.add(types.InlineKeyboardButton(text="📸 Фото", callback_data="edit_field_photos"))
    keyboard.add(types.InlineKeyboardButton(text="↩️ Назад к предпросмотру", callback_data="back_to_preview"))
    keyboard.adjust(2)

    edit_texts = {
        'ru': "✏️ <b>Что вы хотите отредактировать?</b>",
        'uz': "✏️ <b>Nimani tahrir qilmoqchisiz?</b>",
        'en': "✏️ <b>What do you want to edit?</b>"
    }

    await callback.message.edit_text(
        edit_texts[user.language],
        reply_markup=keyboard.as_markup(),
        parse_mode='HTML'
    )

@router.callback_query(AdStates.preview, F.data == "cancel_ad")
async def process_cancel_ad(callback: CallbackQuery, state: FSMContext):
    """
    Отмена создания объявления
    """
    user = db.get_user(callback.from_user.id)

    cancel_texts = {
        'ru': "❌ <b>Создание объявления отменено</b>",
        'uz': "❌ <b>E'lon yaratish bekor qilindi</b>",
        'en': "❌ <b>Listing creation cancelled</b>"
    }

    await callback.message.edit_text(cancel_texts[user.language], parse_mode='HTML')
    await state.clear()

# ========== УПРАВЛЕНИЕ ОБЪЯВЛЕНИЯМИ ==========

@router.message(F.text == "📋 Мои объявления")
@router.message(F.text == "📋 My Ads")
@router.message(F.text == "📋 Mening e'lonlarim")
async def show_user_ads(message: Message):
    """
    Показ объявлений пользователя
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите бота командой /start")
        return

    ads = db.get_user_ads(user.id)

    if not ads:
        no_ads_texts = {
            'ru': "📭 У вас пока нет объявлений.\n\nИспользуйте «Добавить объявление» чтобы создать первое!",
            'uz': "📭 Hozircha sizda e'lonlar yo'q.\n\nBirinchi e'lonni yaratish uchun «Yangi e'lon qo'shish» dan foydalaning!",
            'en': "📭 You don't have any listings yet.\n\nUse «Add New Ad» to create your first one!"
        }
        await message.answer(no_ads_texts[user.language])
        return

    # Показываем статистику
    active_ads = [ad for ad in ads if ad.status == 'approved']
    pending_ads = [ad for ad in ads if ad.status == 'pending']
    expired_ads = [ad for ad in ads if ad.status == 'expired']

    stats_texts = {
        'ru': f"""
📊 <b>Ваши объявления</b>

✅ Активные: {len(active_ads)}
⏳ На модерации: {len(pending_ads)}
📁 Архив: {len(expired_ads)}
        """,
        'uz': f"""
📊 <b>Sizning e'lonlaringiz</b>

✅ Faol: {len(active_ads)}
⏳ Moderatsiyada: {len(pending_ads)}
📁 Arxiv: {len(expired_ads)}
        """,
        'en': f"""
📊 <b>Your Listings</b>

✅ Active: {len(active_ads)}
⏳ Pending: {len(pending_ads)}
📁 Archive: {len(expired_ads)}
        """
    }

    await message.answer(stats_texts[user.language], parse_mode='HTML')

    # Показываем последние 5 объявлений
    for ad in ads[:5]:
        await show_ad_preview_to_user(message, ad, user)

async def show_ad_preview_to_user(message: Message, ad: Ad, user: User):
    """
    Показ предпросмотра объявления пользователю
    """
    status_icons = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌',
        'expired': '📁'
    }

    status_texts = {
        'pending': 'На модерации',
        'approved': 'Активно',
        'rejected': 'Отклонено',
        'expired': 'Архив'
    }

    status_texts_uz = {
        'pending': 'Moderatsiyada',
        'approved': 'Faol',
        'rejected': 'Rad etilgan',
        'expired': 'Arxiv'
    }

    status_texts_en = {
        'pending': 'Pending',
        'approved': 'Active',
        'rejected': 'Rejected',
        'expired': 'Archive'
    }

    status_dict = status_texts if user.language == 'ru' else (
        status_texts_uz if user.language == 'uz' else status_texts_en
    )

    ad_text = f"""
{status_icons.get(ad.status, '📋')} <b>{ad.title}</b>

💰 {ad.price:,.0f} {ad.currency.upper()}
📍 {ad.location}
📊 Статус: {status_dict.get(ad.status, ad.status)}
👀 Просмотры: {ad.views}
📅 Создано: {ad.created_at.strftime('%d.%m.%Y')}
    """

    # Добавляем информацию об истечении срока для бесплатных ролей
    if user.role in ['продавец', 'покупатель'] and ad.status == 'approved' and ad.expires_at:
        days_left = (ad.expires_at - datetime.now()).days
        if days_left > 0:
            expires_texts = {
                'ru': f"⏰ Осталось дней: {days_left}",
                'uz': f"⏰ Qolgan kunlar: {days_left}",
                'en': f"⏰ Days left: {days_left}"
            }
            ad_text += f"\n{expires_texts[user.language]}"
        else:
            expired_texts = {
                'ru': "⏰ Срок размещения истек",
                'uz': "⏰ Joylashtirish muddati tugadi",
                'en': "⏰ Placement period expired"
            }
            ad_text += f"\n{expired_texts[user.language]}"

    keyboard = InlineKeyboardBuilder()

    if ad.status == 'approved':
        keyboard.add(types.InlineKeyboardButton(text="👀 Посмотреть", callback_data=f"view_ad_{ad.id}"))
        keyboard.add(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_ad_{ad.id}"))
    elif ad.status == 'pending':
        keyboard.add(types.InlineKeyboardButton(text="🗑️ Отменить", callback_data=f"cancel_pending_ad_{ad.id}"))
    elif ad.status == 'rejected':
        keyboard.add(types.InlineKeyboardButton(text="✏️ Исправить", callback_data=f"edit_rejected_ad_{ad.id}"))
        keyboard.add(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_ad_{ad.id}"))
    elif ad.status == 'expired':
        keyboard.add(types.InlineKeyboardButton(text="🔄 Обновить", callback_data=f"renew_ad_{ad.id}"))
        keyboard.add(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_ad_{ad.id}"))

    keyboard.adjust(2)

    if ad.photos:
        await message.answer_photo(
            ad.photos[0],
            caption=ad_text,
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )
    else:
        await message.answer(
            ad_text,
            reply_markup=keyboard.as_markup(),
            parse_mode='HTML'
        )

@router.callback_query(F.data.startswith("delete_ad_"))
async def process_delete_ad(callback: CallbackQuery):
    """
    Удаление объявления
    """
    ad_id = int(callback.data.split('_')[2])
    user = db.get_user(callback.from_user.id)

    # Проверяем, что объявление принадлежит пользователю
    ad = db.get_ad_by_id(ad_id)
    if not ad or ad.user_id != user.id:
        error_texts = {
            'ru': "❌ Ошибка: объявление не найдено или у вас нет прав для его удаления",
            'uz': "❌ Xato: e'lon topilmadi yoki uni o'chirish huquqingiz yo'q",
            'en': "❌ Error: listing not found or you don't have permission to delete it"
        }
        await callback.message.answer(error_texts[user.language])
        return

    # Удаляем объявление
    db.delete_ad(ad_id)

    delete_texts = {
        'ru': "✅ Объявление удалено",
        'uz': "✅ E'lon o'chirildi",
        'en': "✅ Listing deleted"
    }

    await callback.message.edit_text(delete_texts[user.language])

@router.callback_query(F.data.startswith("renew_ad_"))
async def process_renew_ad(callback: CallbackQuery, state: FSMContext):
    """
    Обновление истекшего объявления
    """
    ad_id = int(callback.data.split('_')[2])
    user = db.get_user(callback.from_user.id)

    ad = db.get_ad_by_id(ad_id)
    if not ad or ad.user_id != user.id:
        error_texts = {
            'ru': "❌ Ошибка: объявление не найдено",
            'uz': "❌ Xato: e'lon topilmadi",
            'en': "❌ Error: listing not found"
        }
        await callback.message.answer(error_texts[user.language])
        return

    # Для бесплатных ролей проверяем лимит активных объявлений
    if user.role in ['продавец', 'покупатель']:
        active_ads = db.get_active_user_ads(user.id)
        if len(active_ads) >= 5:
            limit_texts = {
                'ru': "❌ Достигнут лимит активных объявлений (5). Удалите одно из текущих объявлений чтобы обновить это.",
                'uz': "❌ Faol e'lonlar chegarasiga erishildi (5). Buni yangilash uchun joriy e'lonlardan birini o'chiring.",
                'en': "❌ Active listings limit reached (5). Delete one of current listings to renew this one."
            }
            await callback.message.answer(limit_texts[user.language])
            return

    # Обновляем объявление (сбрасываем срок действия)
    db.renew_ad(ad_id)

    renew_texts = {
        'ru': "✅ Объявление обновлено! Оно снова активно на 30 дней.",
        'uz': "✅ E'lon yangilandi! U yana 30 kun faol.",
        'en': "✅ Listing renewed! It's active again for 30 days."
    }

    await callback.message.edit_text(renew_texts[user.language])

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def notify_admin_about_new_ad(ad_id: int):
    """
    Уведомление администратора о новом объявлении
    """
    try:
        from main import bot

        ad = db.get_ad_by_id(ad_id)
        if not ad:
            return

        user = db.get_user_by_id(ad.user_id)

        admin_text = f"""
📥 <b>Новое объявление на модерацию</b>

ID: <code>{ad.id}</code>
🏷️ Тип: {ad.type}
👤 Автор: {user.first_name} (@{user.username})
📝 Заголовок: {ad.title}

Используйте /moderate для просмотра
        """

        await bot.send_message(
            chat_id=Config.ADMIN_ID,
            text=admin_text,
            parse_mode='HTML'
        )

    except Exception as e:
        logging.error(f"Ошибка уведомления админа: {e}")

# ========== NLP ПРОЦЕССОР ==========

class NLPProcessor:
    """
    Процессор для NLP анализа описаний объявлений
    """
    def __init__(self):
        self.price_patterns = [
            r'(\d+[\s\d]*)\s*(?:сум|usd|доллар)',
            r'цена\s*:\s*(\d+[\s\d]*)',
            r'(\d+[\s\d]*)\s*(?:₽|\$|€)',
            r'стоимость\s*(\d+[\s\d]*)'
        ]

    def analyze_description(self, text: str) -> dict:
        """
        Анализ описания на наличие проблем и извлечение информации
        """
        issues = []
        suggestions = []
        extracted_price = None

        # Проверка длины
        if len(text) < 50:
            issues.append("Слишком короткое описание")
            suggestions.append("Добавьте больше деталей об объекте")
        elif len(text) > 2000:
            issues.append("Слишком длинное описание")
            suggestions.append("Сократите описание до 2000 символов")

        # Проверка на наличие цифр (возможно, цены)
        if not any(char.isdigit() for char in text):
            issues.append("Отсутствует цена")
            suggestions.append("Укажите цену объекта")
        else:
            # Попытка извлечь цену
            extracted_price = self.extract_price(text)
            if not extracted_price:
                issues.append("Цена не распознана")
                suggestions.append("Укажите цену явно, например: 'Цена: 50000'")

        # Проверка на ключевые слова
        important_keywords = ['комнат', 'площад', 'метр', 'этаж', 'район']
        found_keywords = [kw for kw in important_keywords if kw in text.lower()]
        if len(found_keywords) < 2:
            issues.append("Мало деталей об объекте")
            suggestions.append("Укажите количество комнат, площадь, этаж, район")

        return {
            'issues': issues,
            'suggestions': suggestions,
            'price': extracted_price,
            'is_valid': len(issues) == 0
        }

    def extract_price(self, text: str) -> float:
        """
        Извлечение цены из текста
        """
        for pattern in self.price_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    price_str = match.group(1).replace(' ', '')
                    return float(price_str)
                except ValueError:
                    continue
        return None

# Экспортируем роутер
__all__ = ['router']
