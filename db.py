import os
import time
from sqlalchemy import (
    create_engine,
    text,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func

# =========================
# Configuración DB de negocio (POS)
# =========================
POS_MYSQL_HOST = os.getenv("POS_MYSQL_HOST", "mysql")
POS_MYSQL_PORT = int(os.getenv("POS_MYSQL_PORT", "3306"))
POS_MYSQL_USER = os.getenv("POS_MYSQL_USER", "proyecto_user")
POS_MYSQL_PASSWORD = os.getenv("POS_MYSQL_PASSWORD")
POS_MYSQL_DATABASE = os.getenv("POS_MYSQL_DATABASE", "pos_db")

POS_DATABASE_URL = (
    f"mysql+pymysql://{POS_MYSQL_USER}:{POS_MYSQL_PASSWORD}"
    f"@{POS_MYSQL_HOST}:{POS_MYSQL_PORT}/{POS_MYSQL_DATABASE}"
)

MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", "30"))
RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", "2"))

# Stocks external app

STOCKS_TIMEOUT = float(os.getenv("STOCKS_TIMEOUT", "8"))

# =========================
# Engine POS
# =========================
pos_engine = create_engine(
    POS_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)

engine = pos_engine


def wait_for_db(engine_to_check, label: str):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with engine_to_check.connect() as conn:
                conn.execute(text("SELECT 1"))
            #print(f"[DB:{label}] Conexión OK en intento {attempt}")
            return
        except Exception as e:
            last_error = e
            #print(f"[DB:{label}] Intento {attempt}/{MAX_RETRIES} falló: {e}")
            time.sleep(RETRY_DELAY)

    raise RuntimeError(f"No se pudo conectar a MySQL ({label}) tras {MAX_RETRIES} intentos: {last_error}")


wait_for_db(pos_engine, "POS")

PosSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=pos_engine, future=True)

Base = declarative_base()


def get_pos_db():
    db = PosSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    yield from get_pos_db()


class Category(Base):
    __tablename__ = "pos_categories"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False, default=1)

    parent_id = Column(
        Integer,
        ForeignKey("pos_categories.id", ondelete="SET NULL"),
        nullable=True
    )

    sort_order = Column(
        Integer,
        nullable=False,
        default=0
    )

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=False, default="#0066FF")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    parent = relationship(
        "Category",
        remote_side=[id],
        backref="children",
        passive_deletes=True
    )
    
    products = relationship(
        "Product",
        back_populates="category"
    )

    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "name",
            name="uq_pos_categories_client_name"
        ),
        Index(
            "idx_pos_categories_client",
            "client_id"
        ),
        Index(
            "idx_pos_categories_client_active",
            "client_id",
            "is_active"
        ),
        Index(
            "idx_pos_categories_parent",
            "parent_id"
        ),
        Index(
            "idx_pos_categories_client_parent",
            "client_id",
            "parent_id"
        ),
    )

class Product(Base):
    __tablename__ = "pos_products"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False, default=1, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    product_type = Column(String(20), nullable=False, default="physical")
    track_inventory = Column(Boolean, nullable=False, default=True)
    inventory_mode = Column(String(20), nullable=False, default="pos_legacy")
    stock_item_id = Column(Integer, nullable=True)

    cost = Column(Float, nullable=False, default=0.0)
    sku = Column(String(50), unique=False, nullable=True)
    barcode = Column(String(50), unique=False, nullable=True)
    category_id = Column(Integer, ForeignKey("pos_categories.id"), nullable=True)

    stock_quantity = Column(Integer, nullable=False, default=0)
    min_stock = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, nullable=False, default=True)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="products")


class PosClientSettings(Base):
    __tablename__ = "pos_client_settings"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False, index=True, unique=True)

    company_display_name = Column(String(200), nullable=True)
    ticket_footer_text = Column(Text, nullable=True)

    catalog_source = Column(String(20), nullable=False, default="pos")
    catalog_integration_url = Column(String(500), nullable=True)

    # INV-5A documental
    print_document_type = Column(String(20), nullable=False, default="ticket")
    ticket_template_name = Column(String(150), nullable=True)
    sales_note_template_name = Column(String(150), nullable=True)

    default_tax_percent = Column(Float, nullable=False, default=0.0)
    default_ticket_cfdi_use = Column(String(10), nullable=False, default="S01")
    default_ticket_tax_regime = Column(String(10), nullable=False, default="616")
    default_customer_id = Column(Integer, nullable=True)

    sales_note_text_default = Column(Text, nullable=True)
    sales_note_extra_text = Column(Text, nullable=True)
    sales_note_services_label = Column(String(150), nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class PosPrice(Base):
    __tablename__ = "pos_prices"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False, index=True)

    catalog_source = Column(String(20), nullable=False, index=True)
    catalog_item_id = Column(Integer, nullable=False, index=True)

    display_name_snapshot = Column(String(200), nullable=False)
    sku_snapshot = Column(String(50), nullable=True)
    category_name_snapshot = Column(String(150), nullable=True)

    product_type_snapshot = Column(String(20), nullable=False, default="physical")
    inventory_mode_snapshot = Column(String(20), nullable=False, default="pos_legacy")
    stock_item_id_snapshot = Column(Integer, nullable=True)

    sale_price = Column(Float, nullable=False)
    tax_percent = Column(Float, nullable=False, default=0.0)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    sale_items = relationship("SaleItem", back_populates="pos_price")

class PosCustomer(Base):
    __tablename__ = "pos_customers"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False, index=True)

    rfc = Column(String(20), nullable=False)
    business_name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    postal_code = Column(String(20), nullable=True)
    tax_regime = Column(String(10), nullable=True)
    cfdi_use = Column(String(10), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Sale(Base):
    __tablename__ = "pos_sales"

    id = Column(Integer, primary_key=True, index=True)

    sale_number = Column(String(50), nullable=False, unique=True, index=True)

    client_id = Column(Integer, nullable=False, index=True)
    app_id = Column(Integer, nullable=False, index=True)
    created_by = Column(String(100), nullable=False, index=True)

    subtotal_snapshot = Column(Float, nullable=False, default=0.0)
    discount_snapshot = Column(Float, nullable=False, default=0.0)
    total_snapshot = Column(Float, nullable=False, default=0.0)
    customer_name_snapshot = Column(String(200), nullable=True)
    cashier_name_snapshot = Column(String(200), nullable=True)
    catalog_source_snapshot = Column(String(20), nullable=False, default="pos")
    catalog_integration_url_snapshot = Column(String(500), nullable=True)

    total_amount = Column(Float, nullable=False)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    payment_method = Column(String(50), default="cash")
    status = Column(String(20), default="completed")
    notes = Column(Text, nullable=True)

    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(String(100), nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    inventory_reverted_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    events = relationship("SaleEvent", back_populates="sale", cascade="all, delete-orphan")
    print_data = relationship("PosSalePrintData", back_populates="sale", uselist=False, cascade="all, delete-orphan")
    

class SaleItem(Base):
    __tablename__ = "pos_sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("pos_sales.id"), nullable=False)
    pos_price_id = Column(Integer, ForeignKey("pos_prices.id"), nullable=False)

    catalog_source = Column(String(20), nullable=False, default="pos")
    catalog_item_id = Column(Integer, nullable=False, default=0)

    catalog_source_snapshot = Column(String(20), nullable=False)
    catalog_item_id_snapshot = Column(Integer, nullable=False)

    product_name_snapshot = Column(String(200), nullable=False)
    sku_snapshot = Column(String(50), nullable=True)
    category_name_snapshot = Column(String(150), nullable=True)
    category_path_snapshot = Column(String(500), nullable=True)
    
    product_type_snapshot = Column(String(20), nullable=False, default="physical")
    inventory_mode_snapshot = Column(String(20), nullable=False, default="pos_legacy")
    stock_item_id_snapshot = Column(Integer, nullable=True)

    quantity = Column(Float, nullable=False)
    unit_price_snapshot = Column(Float, nullable=False)
    line_total_snapshot = Column(Float, nullable=False)

    unit_price = Column(Float, nullable=False)
    tax_percent = Column(Float, nullable=False, default=0.0)
    total_price = Column(Float, nullable=False)

    created_at = Column(DateTime, default=func.now())

    sale = relationship("Sale", back_populates="items")
    pos_price = relationship("PosPrice", back_populates="sale_items")

class PosSalePrintData(Base):
    __tablename__ = "pos_sale_print_data"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(Integer, ForeignKey("pos_sales.id"), nullable=False, unique=True)
    client_id = Column(Integer, nullable=False, index=True)

    document_type = Column(String(20), nullable=False)
    template_name = Column(String(150), nullable=False)

    pos_customer_id = Column(Integer, nullable=True, index=True)

    customer_rfc = Column(String(20), nullable=True)
    customer_business_name = Column(String(255), nullable=True)
    customer_contact_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_address = Column(Text, nullable=True)
    customer_postal_code = Column(String(20), nullable=True)
    customer_tax_regime = Column(String(10), nullable=True)
    customer_cfdi_use = Column(String(10), nullable=True)

    attended_by = Column(String(150), nullable=True)
    payment_method_label = Column(String(200), nullable=True)
    sales_note_text = Column(Text, nullable=True)
    ticket_footer_text = Column(Text, nullable=True)
    sales_note_extra_text = Column(Text, nullable=True)
    services_label = Column(String(150), nullable=True)

    subtotal = Column(Float, nullable=False, default=0.0)
    tax_amount = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False, default=0.0)

    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    sale = relationship("Sale", back_populates="print_data")
    
class SaleEvent(Base):
    __tablename__ = "pos_sale_events"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(Integer, ForeignKey("pos_sales.id"), nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)

    event_type = Column(String(50), nullable=False, index=True)
    event_status = Column(String(20), nullable=False, default="ok")

    notes = Column(Text, nullable=True)

    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)

    payload_json = Column(JSON, nullable=True)

    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.now())

    sale = relationship("Sale", back_populates="events")