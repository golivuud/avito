from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import async_session
from services import ShopService

router = Router()


class BotStates(StatesGroup):
    waiting_sale_price = State()
    waiting_refund_price = State()
    waiting_new_product = State()
    waiting_inv_qty = State()
    waiting_box_name = State()
    waiting_box_put_qty = State()
    waiting_box_take_qty = State()


def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить продажу", callback_data="btn_add_sale"
        ),
        InlineKeyboardButton(
            text="📜 История продаж", callback_data="btn_sales_history"
        ),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Прибыль", callback_data="btn_profit"),
        InlineKeyboardButton(text="↩️ Возврат", callback_data="btn_refund"),
    )
    builder.row(
        InlineKeyboardButton(
            text="📦 Остатки", callback_data="btn_inventory"
        ),
        InlineKeyboardButton(
            text="🏭 Коробки на складе", callback_data="btn_boxes_menu"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🛠️ Управление БД", callback_data="btn_db_manage"
        )
    )
    return builder.as_markup()


@router.message(Command("start", "menu"))
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📦 Главное меню", reply_markup=get_main_menu())


@router.callback_query(F.data == "btn_menu")
async def menu_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("📦 Главное меню", reply_markup=get_main_menu())
    await call.answer()


# === ПРОДАЖИ ===
@router.callback_query(F.data == "btn_add_sale")
async def add_sale_init(call: CallbackQuery):
    async with async_session() as session:
        service = ShopService(session)
        products = await service.get_products(exclude_boxes=True)

    if not products:
        await call.answer("❌ Товаров нет.")
        return

    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(text=p.name, callback_data=f"sale_sel_{p.name}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="📦 Меню", callback_data="btn_menu"))

    await call.message.edit_text(
        "📦 Выбери товар:", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data.startswith("sale_sel_"))
async def sale_pick_product(call: CallbackQuery, state: FSMContext):
    p_name = call.data.split("sale_sel_", 1)[1]
    await state.update_data(product_name=p_name)
    await state.set_state(BotStates.waiting_sale_price)

    await call.message.answer(f"✅ {p_name}\nВведи цену (RUB):")
    await call.answer()


@router.message(BotStates.waiting_sale_price)
async def process_sale_price(message: Message, state: FSMContext):
    text = (message.text or "").replace(",", ".").strip()
    try:
        price = float(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи нормальное число больше 0!")
        return

    data = await state.get_data()
    p_name = data["product_name"]

    async with async_session() as session:
        service = ShopService(session)
        rem = await service.register_sale(p_name, price)

    await state.clear()
    await message.answer(
        f"✅ Продажа добавлена!\n{p_name} | {price} RUB\n📦 Остаток под рукой: {rem} шт.",
        reply_markup=get_main_menu(),
    )


# === ИСТОРИЯ ПРОДАЖ ===
@router.callback_query(F.data == "btn_sales_history")
async def sales_history_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Последняя", callback_data="show_sales_1"
        ),
        InlineKeyboardButton(
            text="Последние 5", callback_data="show_sales_5"
        ),
        InlineKeyboardButton(
            text="Последние 10", callback_data="show_sales_10"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Всего продано", callback_data="show_sales_count"
        ),
        InlineKeyboardButton(text="📦 Меню", callback_data="btn_menu"),
    )
    await call.message.edit_text(
        "📊 Сколько продаж показать:", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data == "show_sales_count")
async def sales_count_cb(call: CallbackQuery):
    async with async_session() as session:
        service = ShopService(session)
        cnt = await service.get_sales_count()
    await call.message.answer(
        f"📊 Всего продаж: <b>{cnt} шт.</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("show_sales_"))
async def show_sales_list(call: CallbackQuery):
    limit = int(call.data.split("_")[2])
    async with async_session() as session:
        service = ShopService(session)
        sales = await service.get_sales_history(limit)

    if not sales:
        await call.message.answer(
            "📭 Продаж нет", reply_markup=get_main_menu()
        )
        await call.answer()
        return

    for s in sales:
        dt = s.sale_date.strftime("%d.%m.%Y %H:%M") if s.sale_date else ""
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"❌ Удалить чек #{s.rn}", callback_data=f"del_sale_{s.id}"
        )
        await call.message.answer(
            f"🧾 Чек #{s.rn}\n📦 {s.product_name}\n💰 {s.price}₽\n🕒 {dt}",
            reply_markup=builder.as_markup(),
        )

    await call.message.answer("📦 Меню", reply_markup=get_main_menu())
    await call.answer()


@router.callback_query(F.data.startswith("del_sale_"))
async def del_sale_cb(call: CallbackQuery):
    sale_id = int(call.data.split("_")[2])
    async with async_session() as session:
        service = ShopService(session)
        await service.delete_sale(sale_id)

    await call.message.edit_text("✅ Продажа удалена, товар возвращен на склад")
    await call.answer()


# === ОСТАТКИ И ПРИБЫЛЬ ===
@router.callback_query(F.data == "btn_inventory")
async def inventory_cb(call: CallbackQuery):
    async with async_session() as session:
        service = ShopService(session)
        inv = await service.get_inventory()

    text = "📦 <b>Остатки на полке:</b>\n\n"
    if not inv:
        text += "📭 Пусто"
    else:
        text += "\n".join(f"• {item[0]}: {item[1]} шт." for item in inv)

    builder = InlineKeyboardBuilder().button(
        text="📦 Меню", callback_data="btn_menu"
    )
    await call.message.edit_text(
        text, parse_mode="HTML", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data == "btn_profit")
async def profit_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Сутки", callback_data="profit_day"),
        InlineKeyboardButton(text="Неделя", callback_data="profit_week"),
        InlineKeyboardButton(text="Месяц", callback_data="profit_month"),
    )
    builder.row(InlineKeyboardButton(text="📦 Меню", callback_data="btn_menu"))
    await call.message.edit_text("📅 Период:", reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("profit_"))
async def profit_calc(call: CallbackQuery):
    period = call.data.split("_")[1]
    async with async_session() as session:
        service = ShopService(session)
        res = await service.get_profit(period)

    builder = InlineKeyboardBuilder().button(
        text="📦 Меню", callback_data="btn_menu"
    )
    await call.message.edit_text(
        f"💰 <b>Прибыль ({period}): {res} RUB</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


# === ВОЗВРАТЫ ===
@router.callback_query(F.data == "btn_refund")
async def refund_init(call: CallbackQuery):
    async with async_session() as session:
        service = ShopService(session)
        products = await service.get_products(exclude_boxes=True)

    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(text=p.name, callback_data=f"ref_sel_{p.name}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="📦 Меню", callback_data="btn_menu"))

    await call.message.edit_text(
        "↩️ Товар для возврата:", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data.startswith("ref_sel_"))
async def refund_pick(call: CallbackQuery, state: FSMContext):
    name = call.data.split("ref_sel_", 1)[1]
    await state.update_data(product_name=name)
    await state.set_state(BotStates.waiting_refund_price)
    await call.message.answer(f"↩️ {name}\nСумма возврата (RUB):")
    await call.answer()


@router.message(BotStates.waiting_refund_price)
async def process_refund(message: Message, state: FSMContext):
    text = (message.text or "").replace(",", ".").strip()
    try:
        price = float(text)
    except ValueError:
        await message.answer("❌ Введи число!")
        return

    data = await state.get_data()
    p_name = data["product_name"]

    async with async_session() as session:
        service = ShopService(session)
        await service.register_refund(p_name, price)

    await state.clear()
    await message.answer(
        f"✅ Возврат оформлен: {p_name} | {price} RUB",
        reply_markup=get_main_menu(),
    )


# === СКЛАД (КОРОБКИ) ===
@router.callback_query(F.data == "btn_boxes_menu")
async def boxes_menu_cb(call: CallbackQuery):
    async with async_session() as session:
        service = ShopService(session)
        boxes = await service.get_boxes()

    builder = InlineKeyboardBuilder()
    for b in boxes:
        builder.button(text=f"📦 {b.name}", callback_data=f"box_v_{b.id}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить коробку", callback_data="box_c_start"
        )
    )
    builder.row(InlineKeyboardButton(text="📦 Меню", callback_data="btn_menu"))

    await call.message.edit_text(
        "🏭 Коробки на складе:", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data == "box_c_start")
async def box_create_init(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_box_name)
    await call.message.answer("Введи название коробки:")
    await call.answer()


@router.message(BotStates.waiting_box_name)
async def process_box_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if name:
        async with async_session() as session:
            service = ShopService(session)
            await service.create_box(name)
        await state.clear()
        await message.answer(
            f"✅ Коробка <b>{name}</b> создана!",
            parse_mode="HTML",
            reply_markup=get_main_menu(),
        )


@router.callback_query(F.data.startswith("box_v_"))
async def box_view_cb(call: CallbackQuery):
    box_id = int(call.data.split("_")[2])
    async with async_session() as session:
        service = ShopService(session)
        items = await service.get_box_items(box_id)

    text = "📦 <b>Содержимое коробки:</b>\n\n"
    if not items:
        text += "<i>(пусто)</i>"
    else:
        text += "\n".join(f"• {it.product_name}: {it.quantity} шт." for it in items)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Положить", callback_data=f"b_put_{box_id}"
        ),
        InlineKeyboardButton(
            text="➖ Забрать", callback_data=f"b_take_{box_id}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Удалить коробку", callback_data=f"b_del_{box_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="btn_boxes_menu")
    )

    await call.message.edit_text(
        text, parse_mode="HTML", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data.startswith("b_put_"))
async def box_put_item_select(call: CallbackQuery):
    box_id = int(call.data.split("_")[2])
    async with async_session() as session:
        service = ShopService(session)
        products = await service.get_products(exclude_boxes=True)

    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(text=p.name, callback_data=f"b_putp_{box_id}_{p.name}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"box_v_{box_id}")
    )

    await call.message.edit_text("Что положить:", reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("b_putp_"))
async def box_put_qty_req(call: CallbackQuery, state: FSMContext):
    _, _, box_id, p_name = call.data.split("_", 3)
    await state.update_data(box_id=int(box_id), product_name=p_name)
    await state.set_state(BotStates.waiting_box_put_qty)
    await call.message.answer(
        f"Сколько штук <b>{p_name}</b> положить?", parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_box_put_qty)
async def process_box_put_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0!")
        return

    data = await state.get_data()
    async with async_session() as session:
        service = ShopService(session)
        await service.update_box_content(
            data["box_id"], data["product_name"], qty
        )

    await state.clear()
    await message.answer(
        f"✅ Положено {qty} шт. ({data['product_name']})",
        reply_markup=get_main_menu(),
    )


@router.callback_query(F.data.startswith("b_take_"))
async def box_take_item_select(call: CallbackQuery):
    box_id = int(call.data.split("_")[2])
    async with async_session() as session:
        service = ShopService(session)
        items = await service.get_box_items(box_id)

    if not items:
        await call.answer("Коробка пуста")
        return

    builder = InlineKeyboardBuilder()
    for it in items:
        builder.button(
            text=f"{it.product_name} ({it.quantity})",
            callback_data=f"b_takep_{box_id}_{it.product_name}",
        )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"box_v_{box_id}")
    )

    await call.message.edit_text("Что забрать:", reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("b_takep_"))
async def box_take_qty_req(call: CallbackQuery, state: FSMContext):
    _, _, box_id, p_name = call.data.split("_", 3)
    await state.update_data(box_id=int(box_id), product_name=p_name)
    await state.set_state(BotStates.waiting_box_take_qty)
    await call.message.answer(
        f"Сколько штук <b>{p_name}</b> забрать?", parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_box_take_qty)
async def process_box_take_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0!")
        return

    data = await state.get_data()
    async with async_session() as session:
        service = ShopService(session)
        await service.update_box_content(
            data["box_id"], data["product_name"], -qty
        )

    await state.clear()
    await message.answer(
        f"✅ Списано {qty} шт. ({data['product_name']})",
        reply_markup=get_main_menu(),
    )


@router.callback_query(F.data.startswith("b_del_"))
async def box_delete_cb(call: CallbackQuery):
    box_id = int(call.data.split("_")[2])
    async with async_session() as session:
        service = ShopService(session)
        await service.delete_box(box_id)
    await call.message.edit_text("✅ Коробка удалена", reply_markup=get_main_menu())
    await call.answer()


# === УПРАВЛЕНИЕ БД ===
@router.callback_query(F.data == "btn_db_manage")
async def db_manage_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить товар", callback_data="prod_add_new"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📦 Редактировать остаток", callback_data="inv_edit_select"
        )
    )
    builder.row(InlineKeyboardButton(text="📦 Меню", callback_data="btn_menu"))
    await call.message.edit_text(
        "🛠️ Управление БД:", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data == "prod_add_new")
async def prod_add_init(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_new_product)
    await call.message.answer("Введи название нового товара:")
    await call.answer()


@router.message(BotStates.waiting_new_product)
async def process_prod_add(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if name:
        async with async_session() as session:
            service = ShopService(session)
            await service.add_product(name)
        await state.clear()
        await message.answer(
            f'✅ Товар "{name}" добавлен!', reply_markup=get_main_menu()
        )


@router.callback_query(F.data == "inv_edit_select")
async def inv_edit_select(call: CallbackQuery):
    async with async_session() as session:
        service = ShopService(session)
        products = await service.get_products()

    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(text=p.name, callback_data=f"inv_set_{p.name}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🛠️ Назад", callback_data="btn_db_manage")
    )

    await call.message.edit_text(
        "Выбери товар для правки остатка:", reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data.startswith("inv_set_"))
async def inv_edit_input(call: CallbackQuery, state: FSMContext):
    p_name = call.data.split("inv_set_", 1)[1]
    await state.update_data(product_name=p_name)
    await state.set_state(BotStates.waiting_inv_qty)
    await call.message.answer(
        f"Товар: <b>{p_name}</b>\nВведи новый точный остаток (шт):",
        parse_mode="HTML",
    )
    await call.answer()


@router.message(BotStates.waiting_inv_qty)
async def process_inv_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи целое число!")
        return

    data = await state.get_data()
    p_name = data["product_name"]

    async with async_session() as session:
        service = ShopService(session)
        await service.set_inventory_quantity(p_name, qty)

    await state.clear()
    await message.answer(
        f"✅ Остаток {p_name} установлен: {qty} шт.",
        reply_markup=get_main_menu(),
    )
