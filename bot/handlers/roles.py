
import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F
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

@router.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора роли пользователем с системой предупреждений
    """
    role = callback.data.split("_")[1]  # role_риэлтор -> риэлтор

    # Получаем пользователя
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.message.answer("❌ Ошибка: пользователь не найден. Используйте /start")
        await state.clear()
        return

    # Проверяем, меняет ли пользователь роль (уже есть существующая роль)
    is_role_change = user.role != 'покупатель'  # покупатель - роль по умолчанию

    # Если пользователь меняет роль на платную, проверяем возможность
    if is_role_change and role in ['риэлтор', 'арендатор', 'агентство', 'застройщик']:
        if user.has_active_subscription():
            # Пользователь уже имеет активную подписку - предупреждаем о смене
            await show_role_change_warning(callback, role, user, state)
            return
        else:
            # Пользователь не имеет активной подписки - предлагаем оплатить
            await show_subscription_required(callback, role, user)
            return

    # Обновляем роль пользователя
    success = db.update_user_role(callback.from_user.id, role)

    if not success:
        await callback.message.answer("❌ Ошибка при обновлении роли. Попробуйте снова.")
        await state.clear()
        return

    # Обновляем объект пользователя
    user = db.get_user(callback.from_user.id)

    # Показываем информацию о выбранной роли
    await show_role_confirmation(callback, role, user, is_role_change)

    await state.clear()

async def show_role_change_warning(callback: CallbackQuery, new_role: str, user: User, state: FSMContext):
    """
    Показ предупреждения при смене роли с активной подпиской
    """
    current_role = user.role
    days_left = (user.subscription_end - datetime.now()).days

    warning_texts = {
        'ru': f"""
⚠️ <b>Внимание! Смена роли</b>

Вы собираетесь сменить роль с <b>{current_role}</b> на <b>{new_role}</b>.

У вас активна подписка, которая действительна еще {days_left} дней.

<b>Что изменится:</b>
• Доступные функции будут соответствовать новой роли
• Текущая подписка останется активной
• Стоимость продления будет соответствовать новой роли

<b>Стоимость продления подписки:</b>
{Config.PRICES.get(new_role, 0):,} UZS/месяц

Вы уверены, что хотите сменить роль?
        """,
        'uz': f"""
⚠️ <b>Diqqat! Rolni o'zgartirish</b>

Siz <b>{current_role}</b> roldan <b>{new_role}</b> rolga o'zgartirmoqchisiz.

Sizda {days_left} kun amal qiladigan faol obuna mavjud.

<b>Nima o'zgaradi:</b>
• Mavfun funksiyalar yangi roliga mos keladi
• Joriy obuna faol bo'lib qoladi
• Yangilash narxi yangi roliga mos keladi

<b>Obunani yangilash narxi:</b>
{Config.PRICES.get(new_role, 0):,} UZS/oy

Rolni o'zgartirishni xohlaysizmi?
        """,
        'en': f"""
⚠️ <b>Warning! Role Change</b>

You are about to change role from <b>{current_role}</b> to <b>{new_role}</b>.

You have an active subscription valid for {days_left} more days.

<b>What will change:</b>
• Available features will match the new role
• Current subscription will remain active
• Renewal cost will match the new role

<b>Subscription renewal cost:</b>
{Config.PRICES.get(new_role, 0):,} UZS/month

Are you sure you want to change role?
        """
    }

    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="✅ Да, сменить роль", callback_data=f"confirm_role_change_{new_role}"))
    keyboard.add(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_role_change"))

    await callback.message.edit_text(
        warning_texts[user.language],
        reply_markup=keyboard.as_markup(),
        parse_mode='HTML'
    )

async def show_subscription_required(callback: CallbackQuery, role: str, user: User):
    """
    Показ информации о необходимости подписки для платных ролей
    """
    price = Config.PRICES.get(role, 0)

    subscription_texts = {
        'ru': f"""
💰 <b>Требуется подписка</b>

Для роли <b>«{role}»</b> требуется активация подписки.

<b>Стоимость подписки:</b>
{price:,} UZS в месяц

<b>Что включено:</b>
• Неограниченное количество объявлений
• Приоритет в поиске
• Расширенная аналитика
• Поддержка 24/7

Выберите период подписки:
        """,
        'uz': f"""
💰 <b>Obuna talab qilinadi</b>

<b>«{role}»</b> roli uchun obunani faollashtirish talab qilinadi.

<b>Obuna narxi:</b>
{price:,} UZS oyiga

<b>Nima kiritilgan:</b>
• Cheklanmangan e'lonlar soni
• Qidiruvda ustuvorlik
• Kengaytirilgan tahlil
• 24/7 qo'llab-quvvatlash

Obuna muddatini tanlang:
        """,
        'en': f"""
💰 <b>Subscription Required</b>

Role <b>«{role}»</b> requires subscription activation.

<b>Subscription cost:</b>
{price:,} UZS per month

<b>What's included:</b>
• Unlimited number of listings
• Priority in search
• Extended analytics
• 24/7 support

Choose subscription period:
        """
    }

    keyboard = Keyboards.get_subscription_plans_with_role(role, user.language)

    await callback.message.edit_text(
        subscription_texts[user.language],
        reply_markup=keyboard,
        parse_mode='HTML'
    )

async def show_role_confirmation(callback: CallbackQuery, role: str, user: User, is_role_change: bool = False):
    """
    Показ подтверждения выбора роли с информацией о возможностях и ограничениях
    """
    # Основное сообщение о роли
    role_messages = {
        'продавец': {
            'ru': f"""
🏠 Вы выбрали роль {hbold('Продавец')}

{bold('✅ Что вы можете делать:')}
• Размещать объявления о продаже недвижимости
• Получать уведомления о новых предложениях
• Общаться с потенциальными покупателями

{get_free_role_warning(user.language)}

{bold('🎯 Рекомендации:')}
• Добавляйте качественные фото объектов
• Указывайте точные цены и местоположение
• Подробно описывайте особенности недвижимости
            """,
            'uz': f"""
🏠 Siz {hbold('Sotuvchi')} rolini tanladingiz

{bold('✅ Nima qila olasiz:')}
• Ko'chmas mulkni sotish haqida e'lon joylashtirish
• Yangi takliflar haqida bildirishnoma olish
• Potentsial xaridorlar bilan muloqot qilish

{get_free_role_warning(user.language)}

{bold('🎯 Tavsiyalar:')}
• Ob'ektlarning sifatli fotosuratlarini qo'shing
• Aniq narxlar va joylashuvni ko'rsating
• Ko'chmas mulkning o'ziga xos xususiyatlarini batafsil tavsiflang
            """,
            'en': f"""
🏠 You selected {hbold('Seller')} role

{bold('✅ What you can do:')}
• Post listings for property sales
• Receive notifications about new offers
• Communicate with potential buyers

{get_free_role_warning(user.language)}

{bold('🎯 Recommendations:')}
• Add quality photos of properties
• Specify accurate prices and location
• Describe property features in detail
            """
        },
        'покупатель': {
            'ru': f"""
💰 Вы выбрали роль {hbold('Покупатель')}

{bold('✅ Что вы можете делать:')}
• Искать недвижимость по критериям
• Сохранять понравившиеся объекты
• Связываться с продавцами напрямую
• Получать уведомления о новых предложениях

{get_free_role_warning(user.language)}

{bold('🎯 Рекомендации:')}
• Используйте расширенный поиск для точных результатов
• Сохраняйте интересные объекты в избранное
• Задавайте продавцам уточняющие вопросы
            """,
            'uz': f"""
💰 Siz {hbold('Xaridor')} rolini tanladingiz

{bold('✅ Nima qila olasiz:')}
• Mezonlar bo'yicha ko'chmas mulkni qidirish
• Yoqgan ob'ektlarni saqlash
• Sotuvchilar bilan to'g'ridan-to'g'ri bog'lanish
• Yangi takliflar haqida bildirishnoma olish

{get_free_role_warning(user.language)}

{bold('🎯 Tavsiyalar:')}
• Aniq natijalar uchun kengaytirilgan qidiruvdan foydalaning
• Qiziqarli ob'ektlarni sevimlilarga saqlang
• Sotuvchilarga aniqlovchi savollar bering
            """,
            'en': f"""
💰 You selected {hbold('Buyer')} role

{bold('✅ What you can do:')}
• Search properties by criteria
• Save favorite listings
• Contact sellers directly
• Receive notifications about new offers

{get_free_role_warning(user.language)}

{bold('🎯 Recommendations:')}
• Use advanced search for precise results
• Save interesting properties to favorites
• Ask sellers clarifying questions
            """
        },
        'арендатор': {
            'ru': f"""
🏡 Вы выбрали роль {hbold('Арендатор')}

{bold('🎁 Бесплатный период:')} {Config.FREE_DAYS.get('арендатор', 0)} дней

{bold('✅ Что вы можете делать:')}
• Размещать объявления об аренде недвижимости
• Управлять бронированиями и просмотрами
• Получать расширенную аналитику
• Использовать шаблоны объявлений

{bold('💳 После бесплатного периода:')}
• Месячная подписка: {Config.PRICES.get('арендатор', 0):,} UZS
• Неограниченное количество объявлений
• Приоритет в поисковых результатах

{bold('🎯 Рекомендации:')}
• Используйте качественные фото для привлечения арендаторов
• Указывайте точную стоимость и условия аренды
• Оперативно отвечайте на запросы
            """,
            'uz': f"""
🏡 Siz {hbold('Ijarachi')} rolini tanladingiz

{bold('🎁 Bepul muddat:')} {Config.FREE_DAYS.get('арендатор', 0)} kun

{bold('✅ Nima qila olasiz:')}
• Ko'chmas mulkni ijaraga berish haqida e'lon joylashtirish
• Band qilish va ko'rib chiqishlarni boshqarish
• Kengaytirilgan tahlil olish
• E'lon shablonlaridan foydalanish

{bold('💳 Bepul muddat tugagandan so'ng:')}
• Oylik obuna: {Config.PRICES.get('арендатор', 0):,} UZS
• Cheklanmangan e'lonlar soni
• Qidiruv natijalarida ustuvorlik

{bold('🎯 Tavsiyalar:')}
• Ijarachilarni jalb qilish uchun sifatli fotosuratlar ishlating
• Aniq narx va ijara shartlarini ko'rsating
• So'rovlarga tez javob bering
            """,
            'en': f"""
🏡 You selected {hbold('Tenant')} role

{bold('🎁 Free trial:')} {Config.FREE_DAYS.get('арендатор', 0)} days

{bold('✅ What you can do:')}
• Post rental property listings
• Manage bookings and viewings
• Receive extended analytics
• Use listing templates

{bold('💳 After free trial:')}
• Monthly subscription: {Config.PRICES.get('арендатор', 0):,} UZS
• Unlimited number of listings
• Priority in search results

{bold('🎯 Recommendations:')}
• Use quality photos to attract tenants
• Specify exact cost and rental terms
• Respond promptly to inquiries
            """
        },
        'риэлтор': {
            'ru': f"""
👔 Вы выбрали роль {hbold('Риэлтор')}

{bold('🎁 Бесплатный период:')} {Config.FREE_DAYS.get('риэлтор', 0)} дней

{bold('✅ Что вы можете делать:')}
• Размещать неограниченное количество объявлений
• Получать расширенную аналитику по объявлениям
• Управлять лидами и клиентами
• Использовать профессиональные шаблоны
• Получать приоритет в поиске

{bold('💳 После бесплатного периода:')}
• Месячная подписка: {Config.PRICES.get('риэлтор', 0):,} UZS
• Доступ ко всем профессиональным функциям
• Техническая поддержка 24/7

{bold('🎯 Рекомендации:')}
• Регулярно обновляйте объявления
• Используйте аналитику для оптимизации
• Настраивайте уведомления о новых лидах
            """,
            'uz': f"""
👔 Siz {hbold('Rieltor')} rolini tanladingiz

{bold('🎁 Bepul muddat:')} {Config.FREE_DAYS.get('риэлтор', 0)} kun

{bold('✅ Nima qila olasiz:')}
• Cheklanmangan miqdorda e'lon joylashtirish
• E'lonlar bo'yicha kengaytirilgan tahlil olish
• Lidlar va mijozlarni boshqarish
• Professional shablonlardan foydalanish
• Qidiruvda ustuvorlik olish

{bold('💳 Bepul muddat tugagandan so'ng:')}
• Oylik obuna: {Config.PRICES.get('риэлтор', 0):,} UZS
• Barcha professional funksiyalarga kirish
• 24/7 texnik qo'llab-quvvatlash

{bold('🎯 Tavsiyalar:')}
• E'lonlarni muntazam yangilang
• Optimallashtirish uchun tahlildan foydalaning
• Yangi lidlar haqida bildirishnomalarni sozlang
            """,
            'en': f"""
👔 You selected {hbold('Realtor')} role

{bold('🎁 Free trial:')} {Config.FREE_DAYS.get('риэлтор', 0)} days

{bold('✅ What you can do:')}
• Post unlimited number of listings
• Receive extended listing analytics
• Manage leads and clients
• Use professional templates
• Get priority in search

{bold('💳 After free trial:')}
• Monthly subscription: {Config.PRICES.get('риэлтор', 0):,} UZS
• Access to all professional features
• 24/7 technical support

{bold('🎯 Recommendations:')}
• Regularly update your listings
• Use analytics for optimization
• Set up notifications for new leads
            """
        },
        'агентство': {
            'ru': f"""
🏢 Вы выбрали роль {hbold('Агентство')}

{bold('🎁 Бесплатный период:')} {Config.FREE_DAYS.get('агентство', 0)} дней

{bold('✅ Что вы можете делать:')}
• Управление командой риэлторов
• Расширенная аналитика по всем объявлениям
• Брендирование профиля агентства
• Массовое управление объявлениями
• Приоритетное размещение в канале

{bold('💳 После бесплатного периода:')}
• Месячная подписка: {Config.PRICES.get('агентство', 0):,} UZS
• Корпоративные функции управления
• Выделенная техническая поддержка

{bold('🎯 Рекомендации:')}
• Создайте профиль вашего агентства
• Настройте права доступа для сотрудников
• Используйте аналитику для бизнес-решений
            """,
            'uz': f"""
🏢 Siz {hbold('Agentlik')} rolini tanladingiz

{bold('🎁 Bepul muddat:')} {Config.FREE_DAYS.get('агентство', 0)} kun

{bold('✅ Nima qila olasiz:')}
• Rieltorlar jamoasini boshqarish
• Barcha e'lonlar bo'yicha kengaytirilgan tahlil
• Agentlik profilingizni brendlash
• E'lonlarni ommaviy boshqarish
• Kanalda ustuvor joylashtirish

{bold('💳 Bepul muddat tugagandan so'ng:')}
• Oylik obuna: {Config.PRICES.get('агентство', 0):,} UZS
• Korporativ boshqaruv funksiyalari
• Ajratilgan texnik qo'llab-quvvatlash

{bold('🎯 Tavsiyalar:')}
• Agentlik profilingizni yarating
• Xodimlar uchun kirish huquqlarini sozlang
• Biznes qarorlari uchun tahlildan foydalaning
            """,
            'en': f"""
🏢 You selected {hbold('Agency')} role

{bold('🎁 Free trial:')} {Config.FREE_DAYS.get('агентство', 0)} days

{bold('✅ What you can do:')}
• Manage team of realtors
• Extended analytics for all listings
• Agency profile branding
• Bulk listing management
• Priority placement in channel

{bold('💳 After free trial:')}
• Monthly subscription: {Config.PRICES.get('агентство', 0):,} UZS
• Corporate management features
• Dedicated technical support

{bold('🎯 Recommendations:')}
• Create your agency profile
• Set up access rights for employees
• Use analytics for business decisions
            """
        },
        'застройщик': {
            'ru': f"""
🏗️ Вы выбрали роль {hbold('Застройщик')}

{bold('🎁 Бесплатный период:')} {Config.FREE_DAYS.get('застройщик', 0)} дней

{bold('✅ Что вы можете делать:')}
• Продвижение новостроек и ЖК
• Управление этапами строительства
• Презентация объектов с фото/видео
• Прямые продажи без посредников
• Приоритет в категории "новостройки"

{bold('💳 После бесплатного периода:')}
• Месячная подписка: {Config.PRICES.get('застройщик', 0):,} UZS
• Специализированные инструменты для застройщиков
• Премиальная техническая поддержка

{bold('🎯 Рекомендации:')}
• Регулярно обновляйте ход строительства
• Используйте качественные материалы для презентаций
• Настраивайте уведомления о новых лидах
            """,
            'uz': f"""
🏗️ Siz {hbold('Quruvchi')} rolini tanladingiz

{bold('🎁 Bepul muddat:')} {Config.FREE_DAYS.get('застройщик', 0)} kun

{bold('✅ Nima qila olasiz:')}
• Yangi uy-joy va turar-joy majmualarini targ'ib qilish
• Qurilish bosqichlarini boshqarish
• Ob'ektlarni foto/video bilan taqdim etish
• Vositachilarsiz to'g'ridan-to'g'ri sotish
• "Yangi qurilish" toifasida ustuvorlik

{bold('💳 Bepul muddat tugagandan so'ng:')}
• Oylik obuna: {Config.PRICES.get('застройщик', 0):,} UZS
• Quruvchilar uchun maxsus vositalar
• Premium texnik qo'llab-quvvatlash

{bold('🎯 Tavsiyalar:')}
• Qurilish jarayonini muntazam yangilang
• Taqdimotlar uchun sifatli materiallardan foydalaning
• Yangi lidlar haqida bildirishnomalarni sozlang
            """,
            'en': f"""
🏗️ You selected {hbold('Developer')} role

{bold('🎁 Free trial:')} {Config.FREE_DAYS.get('застройщик', 0)} days

{bold('✅ What you can do:')}
• Promote new developments and residential complexes
• Manage construction stages
• Present objects with photos/videos
• Direct sales without intermediaries
• Priority in "new construction" category

{bold('💳 After free trial:')}
• Monthly subscription: {Config.PRICES.get('застройщик', 0):,} UZS
• Specialized tools for developers
• Premium technical support

{bold('🎯 Recommendations:')}
• Regularly update construction progress
• Use quality materials for presentations
• Set up notifications for new leads
            """
        }
    }

    role_message = role_messages.get(role, role_messages['покупатель'])[user.language]

    # Для смены роли добавляем соответствующее сообщение
    if is_role_change:
        change_message = {
            'ru': f"\n\n✅ Роль успешно изменена с предыдущей на {hbold(role)}",
            'uz': f"\n\n✅ Rol avvalgisidan {hbold(role)} ga muvaffaqiyatli o'zgartirildi",
            'en': f"\n\n✅ Role successfully changed from previous to {hbold(role)}"
        }
        role_message += change_message[user.language]

    await callback.message.edit_text(role_message, parse_mode='HTML')

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

    # Логируем выбор роли
    logging.info(f"👤 Пользователь {user.first_name} (@{user.username}) выбрал роль: {role}")

@router.callback_query(F.data.startswith("confirm_role_change_"))
async def confirm_role_change(callback: CallbackQuery, state: FSMContext):
    """
    Подтверждение смены роли
    """
    new_role = callback.data.split("_")[3]  # confirm_role_change_риэлтор -> риэлтор

    # Обновляем роль пользователя
    user = db.update_user_role(callback.from_user.id, new_role)

    if not user:
        await callback.message.answer("❌ Ошибка при смене роли. Попробуйте снова.")
        await state.clear()
        return

    # Показываем подтверждение
    await show_role_confirmation(callback, new_role, user, is_role_change=True)
    await state.clear()

@router.callback_query(F.data == "cancel_role_change")
async def cancel_role_change(callback: CallbackQuery, state: FSMContext):
    """
    Отмена смены роли
    """
    user = db.get_user(callback.from_user.id)

    cancel_texts = {
        'ru': "❌ Смена роли отменена. Ваша текущая роль сохранена.",
        'uz': "❌ Rolni o'zgartirish bekor qilindi. Joriy rolingiz saqlandi.",
        'en': "❌ Role change cancelled. Your current role has been preserved."
    }

    await callback.message.edit_text(cancel_texts[user.language])
    await state.clear()

def get_free_role_warning(language: str) -> str:
    """
    Возвращает предупреждение о 30-дневном ограничении для бесплатных ролей
    """
    warnings = {
        'ru': f"""
⚠️ <b>Важная информация для бесплатных ролей:</b>

• Ваши объявления будут находиться в канале <b>30 дней</b>
• После 30 дней объявления автоматически архивируются
• Для продления срока размещения необходимо повторно отправить объявление
• Ограничение: не более 5 активных объявлений одновременно

<b>Для снятия ограничений рассмотрите платные роли:</b>
• Риэлтор - {Config.PRICES.get('риэлтор', 0):,} UZS/месяц
• Арендатор - {Config.PRICES.get('арендатор', 0):,} UZS/месяц
        """,
        'uz': f"""
⚠️ <b>Bepul rollar uchun muhim ma'lumot:</b>

• Sizning e'lonlaringiz kanalda <b>30 kun</b> bo'ladi
• 30 kundan keyin e'lonlar avtomatik ravishda arxivlanadi
• Joylashtirish muddatini uzaytirish uchun e'loni qayta yuborish kerak
• Cheklov: bir vaqtning o'zida 5 tadan ortiq faol e'lon bo'lmasligi

<b>Cheklovlarni olib tashlash uchun pulli rollarni ko'rib chiqing:</b>
• Rieltor - {Config.PRICES.get('риэлтор', 0):,} UZS/oy
• Ijarachi - {Config.PRICES.get('арендатор', 0):,} UZS/oy
        """,
        'en': f"""
⚠️ <b>Important information for free roles:</b>

• Your listings will remain in the channel for <b>30 days</b>
• After 30 days, listings are automatically archived
• To extend placement period, you need to resubmit the listing
• Limit: no more than 5 active listings at the same time

<b>To remove limitations, consider paid roles:</b>
• Realtor - {Config.PRICES.get('риэлтор', 0):,} UZS/month
• Tenant - {Config.PRICES.get('арендатор', 0):,} UZS/month
        """
    }

    return warnings.get(language, warnings['ru'])

def bold(text: str) -> str:
    """
    Вспомогательная функция для жирного текста в Markdown
    """
    return f"<b>{text}</b>"

# ========== КОМАНДА ДЛЯ СМЕНЫ РОЛИ ==========

@router.message(F.text == "👤 Сменить роль")
@router.message(F.text == "👤 Change Role")
@router.message(F.text == "👤 Rolni o'zgartirish")
async def change_role_command(message: Message):
    """
    Обработчик команды смены роли через меню
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return

    change_role_texts = {
        'ru': f"👤 <b>Текущая роль: {user.role}</b>\n\nВыберите новую роль:",
        'uz': f"👤 <b>Joriy rol: {user.role}</b>\n\nYangi rol tanlang:",
        'en': f"👤 <b>Current role: {user.role}</b>\n\nChoose new role:"
    }

    await message.answer(
        change_role_texts[user.language],
        reply_markup=Keyboards.get_roles_keyboard(user.language),
        parse_mode='HTML'
    )

# ========== ИНФОРМАЦИЯ О РОЛЯХ ==========

@router.message(Command("roles"))
async def cmd_roles_info(message: Message):
    """
    Команда для просмотра информации о всех ролях
    """
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота командой /start")
        return

    roles_info_texts = {
        'ru': """
👥 <b>Информация о ролях в системе</b>

<b>🏠 Продавец (Бесплатно)</b>
• Размещение объявлений о продаже
• Ограничение: 30 дней в канале
• Максимум 5 активных объявлений

<b>💰 Покупатель (Бесплатно)</b>  
• Поиск и сохранение недвижимости
• Связь с продавцами
• Уведомления о новых предложениях

<b>🏡 Арендатор ({price_tenant:,} UZS/месяц)</b>
• Размещение объявлений об аренде
• Управление бронированиями
• Расширенная аналитика

<b>👔 Риэлтор ({price_realtor:,} UZS/месяц)</b>
• Неограниченные объявления
• Профессиональные инструменты
• Приоритет в поиске

<b>🏢 Агентство ({price_agency:,} UZS/месяц)</b>
• Управление командой
• Корпоративная аналитика
• Брендирование профиля

<b>🏗️ Застройщик ({price_developer:,} UZS/месяц)</b>
• Продвижение новостроек
• Специализированные инструменты
• Премиальная поддержка

Для смены роли используйте меню или команду /changerole
        """,
        'uz': """
👥 <b>Tizimdagi rollar haqida ma'lumot</b>

<b>🏠 Sotuvchi (Bepul)</b>
• Sotish haqida e'lon joylashtirish
• Cheklov: kanalda 30 kun
• Maksimum 5 ta faol e'lon

<b>💰 Xaridor (Bepul)</b>
• Ko'chmas mulkni qidirish va saqlash
• Sotuvchilar bilan aloqa
• Yangi takliflar haqida bildirishnoma

<b>🏡 Ijarachi ({price_tenant:,} UZS/oy)</b>
• Ijaraga berish haqida e'lon joylashtirish
• Band qilishlarni boshqarish
• Kengaytirilgan tahlil

<b>👔 Rieltor ({price_realtor:,} UZS/oy)</b>
• Cheklanmagan e'lonlar
• Professional vositalar
• Qidiruvda ustuvorlik

<b>🏢 Agentlik ({price_agency:,} UZS/oy)</b>
• Jamoa boshqaruvi
• Korporativ tahlil
• Profilni brendlash

<b>🏗️ Quruvchi ({price_developer:,} UZS/oy)</b>
• Yangi qurilishlarni targ'ib qilish
• Maxsus vositalar
• Premium qo'llab-quvvatlash

Rolni o'zgartirish uchun menyu yoki /changerole buyrug'idan foydalaning
        """,
        'en': """
👥 <b>Information about system roles</b>

<b>🏠 Seller (Free)</b>
• Posting sale listings
• Limit: 30 days in channel
• Maximum 5 active listings

<b>💰 Buyer (Free)</b>
• Search and save properties
• Contact with sellers
• Notifications about new offers

<b>🏡 Tenant ({price_tenant:,} UZS/month)</b>
• Posting rental listings
• Booking management
• Extended analytics

<b>👔 Realtor ({price_realtor:,} UZS/month)</b>
• Unlimited listings
• Professional tools
• Priority in search

<b>🏢 Agency ({price_agency:,} UZS/month)</b>
• Team management
• Corporate analytics
• Profile branding

<b>🏗️ Developer ({price_developer:,} UZS/month)</b>
• New construction promotion
• Specialized tools
• Premium support

Use menu or /changerole command to change role
        """
    }

    roles_info = roles_info_texts[user.language].format(
        price_tenant=Config.PRICES.get('арендатор', 0),
        price_realtor=Config.PRICES.get('риэлтор', 0),
        price_agency=Config.PRICES.get('агентство', 0),
        price_developer=Config.PRICES.get('застройщик', 0)
    )

    await message.answer(roles_info, parse_mode='HTML')

# Экспортируем роутер
__all__ = ['router']
