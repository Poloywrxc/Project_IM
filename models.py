from sqlalchemy import Column, Integer, String, Text, Numeric, Date, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from database import Base
import enum


# ==========================================
# ENUMS
# ==========================================


class MovementType(str, enum.Enum):
    stock_in  = "stock_in"
    stock_out = "stock_out"
    adjustment = "adjustment"
    return_in  = "return_in"

class OrderStatus(str, enum.Enum):
    pending   = "pending"
    confirmed = "confirmed"
    delivered = "delivered"
    cancelled = "cancelled"


class PaymentMethod(str, enum.Enum):
    cash   = "cash"
    gcash  = "gcash"
    credit = "credit"

# ==========================================
# 1. USER & PROFILE MODULE
# ==========================================

class User(Base):
    __tablename__ = "users"

    user_id       = Column(Integer,      primary_key=True, autoincrement=True)
    full_name     = Column(String(120),  nullable=False)
    email         = Column(String(120),  unique=True, nullable=False)
    password_hash = Column(String(255),  nullable=False)
    address       = Column(String(255),  nullable=True)
    birthdate     = Column(Date,         nullable=True)
    role          = Column(Enum(UserRole), nullable=False)
    created_at    = Column(DateTime,     nullable=True)
    updated_at    = Column(DateTime,     nullable=True)

    # Relationships
    inventory_movements = relationship("InventoryMovement", back_populates="user")
    order_transactions  = relationship("OrderTransaction",  back_populates="user")
    purchase_orders     = relationship("PurchaseOrder",     back_populates="user")

    def to_dict(self):
        return {
            "user_id":   self.user_id,
            "full_name": self.full_name,
            "email":     self.email,
            "role":      self.role.value if self.role else None,
        }

    def __repr__(self):
        return f"<User {self.full_name}>"


# ==========================================
# 2. PRODUCT & INVENTORY MODULE
# ==========================================

class Product(Base):
    __tablename__ = "products"

    product_id    = Column(Integer,       primary_key=True, autoincrement=True)
    category_name = Column(String(100), nullable=False)
    supplier_id   = Column(Integer,       ForeignKey("suppliers.supplier_id"),   nullable=True)
    model_name    = Column(String(120),   nullable=False)
    sku           = Column(String(100),   nullable=False, unique=True)
    barcode       = Column(String(100),   nullable=True)   # Fixed: was Integer
    cost_price    = Column(Numeric(10,2), nullable=False)
    selling_price = Column(Numeric(10,2), nullable=False)
    stock_qty     = Column(Integer,       default=0)
    reorder_level = Column(Integer,       default=10)
    unit          = Column(String(20),    nullable=True)
    status        = Column(String(20),    nullable=True)

    # Relationships
    supplier             = relationship("Supplier",          back_populates="products")
    inventory_movements  = relationship("InventoryMovement", back_populates="product")
    discounts            = relationship("Discount",          back_populates="product")
    purchase_order_items = relationship("PurchaseOrderItem", back_populates="product")

    def to_dict(self):
        return {
            "product_id":    self.product_id,
            "model_name":    self.model_name,
            "selling_price": str(self.selling_price),
            "stock_qty":     self.stock_qty,
        }

    def __repr__(self):
        return f"<Product {self.model_name}>"


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    movement_id = Column(Integer,          primary_key=True, autoincrement=True)
    product_id  = Column(Integer,          ForeignKey("products.product_id"), nullable=False)
    user_id     = Column(Integer,          ForeignKey("users.user_id"),       nullable=False)
    type        = Column(Enum(MovementType), nullable=False)
    quantity    = Column(Integer,          nullable=False)
    reason      = Column(String(255),      nullable=True)
    moved_at    = Column(DateTime,         nullable=True)   # Fixed: was Integer

    # Relationships
    product = relationship("Product", back_populates="inventory_movements")
    user    = relationship("User",    back_populates="inventory_movements")

    def __repr__(self):
        return f"<InventoryMovement {self.type} qty={self.quantity}>"


# ==========================================
# 3. SALES & TRANSACTION MODULE
# ==========================================

class OrderTransaction(Base):
    __tablename__ = "order_transactions"

    order_transaction_id = Column(Integer,              primary_key=True, autoincrement=True)
    user_id              = Column(Integer,              ForeignKey("users.user_id"),    nullable=False)
    product_id           = Column(Integer,              ForeignKey("products.product_id"), nullable=True)
    order_date           = Column(DateTime,             nullable=False)
    subtotal             = Column(Numeric(10,2),        nullable=False)   # Fixed: was Integer
    discount_amount      = Column(Numeric(10,2),        default=0)
    tax_amount           = Column(Numeric(10,2),        default=0)
    total_amount         = Column(Numeric(10,2),        nullable=False)
    rider_name           = Column(String(120),          nullable=True)    # Fixed: was bare name
    fulfillment_method   = Column(Enum(FulfillmentMethod), nullable=True)
    payment_method       = Column(Enum(PaymentMethod),  nullable=True)
    amount_tendered      = Column(Numeric(10,2),        nullable=True)
    change_given         = Column(Numeric(10,2),        nullable=True)
    status               = Column(Enum(OrderStatus),   nullable=False, default=OrderStatus.pending)

    # Relationships
    user    = relationship("User",    back_populates="order_transactions")
    details = relationship("OrderTransactionDetail", back_populates="order_transaction")

    def to_dict(self):
        return {
            "transaction_id": self.order_transaction_id,
            "total":          str(self.total_amount),
            "status":         self.status.value if self.status else None,
        }

    def __repr__(self):
        return f"<OrderTransaction #{self.order_transaction_id} {self.status}>"



# ==========================================
# 4. SUPPLY CHAIN & LOGISTICS
# ==========================================

class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id    = Column(Integer,     primary_key=True, autoincrement=True)
    company_name   = Column(String(120), nullable=False)
    handler        = Column(String(120), nullable=True)
    address        = Column(String(255), nullable=True)
    contact_number = Column(String(20),  nullable=True)   # Fixed: was Integer
    email          = Column(String(120), nullable=True)

    # Relationships
    products        = relationship("Product",       back_populates="supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

    def __repr__(self):
        return f"<Supplier {self.company_name}>"


