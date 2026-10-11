from datetime import datetime
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    BoxContent,
    Expense,
    Inventory,
    Product,
    Refund,
    Sale,
    StorageBox,
)


class ShopService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_products(self, exclude_boxes: bool = False):
        query = select(Product).order_by(Product.id)
        if exclude_boxes:
            query = query.where(Product.name != "Коробки")
        res = await self.session.execute(query)
        return res.scalars().all()

    async def add_product(self, name: str) -> Product:
        product = Product(name=name)
        self.session.add(product)
        await self.session.flush()

        inv = Inventory(product_name=name, quantity=0)
        self.session.add(inv)
        await self.session.commit()
        return product

    async def get_inventory(self):
        query = (
            select(Product.name, func.coalesce(Inventory.quantity, 0))
            .outerjoin(Inventory, Product.name == Inventory.product_name)
            .order_by(Product.id)
        )
        res = await self.session.execute(query)
        return res.all()

    async def set_inventory_quantity(self, product_name: str, quantity: int):
        stmt = (
            update(Inventory)
            .where(Inventory.product_name == product_name)
            .values(quantity=quantity)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_inventory_delta(self, product_name: str, delta: int):
        stmt = (
            update(Inventory)
            .where(Inventory.product_name == product_name)
            .values(quantity=Inventory.quantity + delta)
        )
        await self.session.execute(stmt)

    async def register_sale(self, product_name: str, price: float) -> int:
        sale = Sale(product_name=product_name, quantity=1, price=price)
        self.session.add(sale)

        await self.update_inventory_delta(product_name, -1)
        if product_name != "Коробки":
            await self.update_inventory_delta("Коробки", -1)

        await self.session.commit()

        res = await self.session.execute(
            select(Inventory.quantity).where(
                Inventory.product_name == product_name
            )
        )
        return res.scalar_one_or_none() or 0

    async def get_sales_history(self, limit: int | None = None):
        subq = select(
            func.row_number().over(order_by=Sale.id.asc()).label("rn"),
            Sale.id,
            Sale.product_name,
            Sale.price,
            Sale.sale_date,
        ).subquery()

        query = select(subq).order_by(subq.c.id.desc())
        if limit:
            query = query.limit(limit)

        res = await self.session.execute(query)
        return res.all()

    async def get_sales_count(self) -> int:
        res = await self.session.execute(select(func.count(Sale.id)))
        return res.scalar_one()

    async def delete_sale(self, sale_id: int):
        res = await self.session.execute(select(Sale).where(Sale.id == sale_id))
        sale = res.scalar_one_or_none()
        if not sale:
            return False

        await self.update_inventory_delta(sale.product_name, 1)
        if sale.product_name != "Коробки":
            await self.update_inventory_delta("Коробки", 1)

        await self.session.delete(sale)
        await self.session.commit()
        return True

    async def register_refund(self, product_name: str, price: float):
        refund = Refund(product_name=product_name, price=price)
        self.session.add(refund)
        await self.update_inventory_delta(product_name, 1)
        if product_name != "Коробки":
            await self.update_inventory_delta("Коробки", 1)
        await self.session.commit()

    async def get_profit(self, period: str) -> float:
        now = datetime.now()
        if period == "day":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_date = (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                - datetime.resolution * now.weekday()
            )
        else:
            start_date = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

        sales_sum = (
            await self.session.execute(
                select(func.coalesce(func.sum(Sale.price), 0)).where(
                    Sale.sale_date >= start_date
                )
            )
        ).scalar_one()

        refunds_sum = (
            await self.session.execute(
                select(func.coalesce(func.sum(Refund.price), 0)).where(
                    Refund.refund_date >= start_date
                )
            )
        ).scalar_one()

        expenses_sum = 0
        if period == "month":
            expenses_sum = (
                await self.session.execute(
                    select(func.coalesce(func.sum(Expense.amount), 0)).where(
                        Expense.expense_date >= start_date
                    )
                )
            ).scalar_one()

        return float(sales_sum - refunds_sum - expenses_sum)

    # Управление складом (коробками)
    async def get_boxes(self):
        res = await self.session.execute(
            select(StorageBox).order_by(StorageBox.id)
        )
        return res.scalars().all()

    async def create_box(self, name: str) -> StorageBox:
        box = StorageBox(name=name)
        self.session.add(box)
        await self.session.commit()
        return box

    async def delete_box(self, box_id: int):
        await self.session.execute(
            delete(StorageBox).where(StorageBox.id == box_id)
        )
        await self.session.commit()

    async def get_box_items(self, box_id: int):
        res = await self.session.execute(
            select(BoxContent)
            .where(BoxContent.box_id == box_id, BoxContent.quantity > 0)
            .order_by(BoxContent.product_name)
        )
        return res.scalars().all()

    async def update_box_content(
        self, box_id: int, product_name: str, delta: int
    ):
        res = await self.session.execute(
            select(BoxContent).where(
                BoxContent.box_id == box_id,
                BoxContent.product_name == product_name,
            )
        )
        item = res.scalar_one_or_none()

        if item:
            item.quantity += delta
            if item.quantity <= 0:
                await self.session.delete(item)
        elif delta > 0:
            item = BoxContent(
                box_id=box_id, product_name=product_name, quantity=delta
            )
            self.session.add(item)

        await self.session.commit()
