from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#0066FF"


class CategoryResponse(BaseModel):
    id: int
    client_id: int
    name: str
    description: Optional[str]
    color: str
    is_active: bool


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None

    product_type: str = "physical"
    track_inventory: bool = True
    inventory_mode: str = "pos_legacy"
    stock_item_id: Optional[int] = None

    sale_price: float = 0.0
    cost: float = 0.0
    sku: Optional[str] = None
    barcode: Optional[str] = None
    category_id: Optional[int] = None
    stock_quantity: float = 0.0
    min_stock: float = 0.0


class ProductResponse(BaseModel):
    id: int
    client_id: int
    name: str
    description: Optional[str]
    sale_price: float

    product_type: str
    track_inventory: bool
    inventory_mode: str
    stock_item_id: Optional[int]

    cost: float
    sku: Optional[str]
    barcode: Optional[str]
    category_id: Optional[int]
    category_name: Optional[str]

    # IMPORTANTE: inventario legacy POS = entero
    stock_quantity: int
    min_stock: int

    is_active: bool
    image_url: Optional[str]


class PosClientSettingsUpsert(BaseModel):
    company_display_name: Optional[str] = None
    ticket_footer_text: Optional[str] = None

    catalog_source: str = "pos"
    catalog_integration_url: Optional[str] = None

    print_document_type: Literal["ticket", "sales_note"] = "ticket"
    ticket_template_name: Optional[str] = None
    sales_note_template_name: Optional[str] = None

    default_tax_percent: float = 0.0
    default_ticket_cfdi_use: str = "S01"
    default_ticket_tax_regime: str = "616"

    sales_note_text_default: Optional[str] = None
    sales_note_extra_text: Optional[str] = None
    sales_note_services_label: Optional[str] = None


class PosClientSettingsResponse(BaseModel):
    id: int
    client_id: int

    company_display_name: Optional[str]
    ticket_footer_text: Optional[str]

    catalog_source: str
    catalog_integration_url: Optional[str]

    print_document_type: str
    ticket_template_name: Optional[str]
    sales_note_template_name: Optional[str]

    default_tax_percent: float
    default_ticket_cfdi_use: str
    default_ticket_tax_regime: str

    sales_note_text_default: Optional[str]
    sales_note_extra_text: Optional[str]
    sales_note_services_label: Optional[str]


class PosPriceCreate(BaseModel):
    catalog_source: str
    catalog_item_id: int

    display_name_snapshot: str
    sku_snapshot: Optional[str] = None
    category_name_snapshot: Optional[str] = None

    product_type_snapshot: str = "physical"
    inventory_mode_snapshot: str = "pos_legacy"
    stock_item_id_snapshot: Optional[int] = None

    sale_price: float = 0.0
    tax_percent: float = 0.0
    is_active: bool = True


class PosPriceUpdate(BaseModel):
    display_name_snapshot: Optional[str] = None
    sku_snapshot: Optional[str] = None
    category_name_snapshot: Optional[str] = None

    product_type_snapshot: Optional[str] = None
    inventory_mode_snapshot: Optional[str] = None
    stock_item_id_snapshot: Optional[int] = None

    sale_price: Optional[float] = None
    tax_percent: Optional[float] = None
    is_active: Optional[bool] = None


class PosPriceResponse(BaseModel):
    id: int
    client_id: int

    catalog_source: str
    catalog_item_id: int

    display_name_snapshot: str
    sku_snapshot: Optional[str]
    category_name_snapshot: Optional[str]

    product_type_snapshot: str
    inventory_mode_snapshot: str
    stock_item_id_snapshot: Optional[int]

    sale_price: float
    tax_percent: float
    is_active: bool


class SaleItemCreate(BaseModel):
    pos_price_id: int
    quantity: float
    

class SaleCreatePrintData(BaseModel):
    document_type: Literal["ticket", "sales_note"]
    template_name: Optional[str] = None

    pos_customer_id: Optional[int] = None

    attended_by: Optional[str] = None
    payment_method_label: Optional[str] = None
    sales_note_text: Optional[str] = None
    ticket_footer_text: Optional[str] = None
    sales_note_extra_text: Optional[str] = None
    services_label: Optional[str] = None


class SaleCreate(BaseModel):
    items: List[SaleItemCreate]
    payment_method: str = "cash"
    notes: Optional[str] = None
    customer_name: Optional[str] = None
    print_data: Optional[SaleCreatePrintData] = None


class SaleItemResponse(BaseModel):
    id: int
    pos_price_id: int
    catalog_source: str
    catalog_item_id: int
    product_name: str
    quantity: float
    unit_price: float
    tax_percent: float
    total_price: float

    catalog_source_snapshot: str
    catalog_item_id_snapshot: int
    sku_snapshot: Optional[str] = None
    category_name_snapshot: Optional[str] = None
    product_type_snapshot: Optional[str] = None
    inventory_mode_snapshot: Optional[str] = None
    stock_item_id_snapshot: Optional[int] = None
    unit_price_snapshot: float
    line_total_snapshot: float


class SaleResponse(BaseModel):
    id: int
    sale_number: str
    client_id: Optional[int] = None
    app_id: Optional[int] = None
    created_by: Optional[str] = None
    catalog_source_snapshot: str
    catalog_integration_url_snapshot: Optional[str] = None

    subtotal_snapshot: float
    discount_snapshot: float
    total_snapshot: float

    total_amount: float
    tax_amount: float
    discount_amount: float
    payment_method: str
    status: str
    notes: Optional[str]
    created_at: datetime
    items: List[SaleItemResponse]
    
class PosCustomerCreate(BaseModel):
    rfc: str
    business_name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    tax_regime: Optional[str] = None
    cfdi_use: Optional[str] = None


class PosCustomerUpdate(BaseModel):
    rfc: Optional[str] = None
    business_name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    tax_regime: Optional[str] = None
    cfdi_use: Optional[str] = None
    is_active: Optional[bool] = None


class PosCustomerResponse(BaseModel):
    id: int
    client_id: int
    rfc: str
    business_name: str
    contact_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    postal_code: Optional[str]
    tax_regime: Optional[str]
    cfdi_use: Optional[str]
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    
class SalePrintContextResponse(BaseModel):
    sale_id: int
    client_id: int
    sale_number: str

    document_type_default: Literal["ticket", "sales_note"]
    ticket_template_name: Optional[str]
    sales_note_template_name: Optional[str]

    company_display_name: Optional[str]
    ticket_footer_text: Optional[str]
    sales_note_text_default: Optional[str]
    sales_note_extra_text: Optional[str]
    sales_note_services_label: Optional[str]

    default_ticket_cfdi_use: str
    default_ticket_tax_regime: str

    payment_method: str
    payment_method_label: Optional[str]

    subtotal: float
    tax_amount: float
    total: float

    customer_name_snapshot: Optional[str]
    cashier_name_snapshot: Optional[str]

    items: List[SaleItemResponse]
    
class SalePrintDataUpsert(BaseModel):
    document_type: Literal["ticket", "sales_note"]
    template_name: Optional[str] = None

    pos_customer_id: Optional[int] = None

    attended_by: Optional[str] = None
    payment_method_label: Optional[str] = None
    sales_note_text: Optional[str] = None
    ticket_footer_text: Optional[str] = None
    sales_note_extra_text: Optional[str] = None
    services_label: Optional[str] = None
    

class SalePrintDataResponse(BaseModel):
    id: int
    sale_id: int
    client_id: int

    document_type: Literal["ticket", "sales_note"]
    template_name: str

    pos_customer_id: Optional[int]

    customer_rfc: Optional[str]
    customer_business_name: Optional[str]
    customer_contact_name: Optional[str]
    customer_phone: Optional[str]
    customer_email: Optional[str]
    customer_address: Optional[str]
    customer_postal_code: Optional[str]
    customer_tax_regime: Optional[str]
    customer_cfdi_use: Optional[str]

    attended_by: Optional[str]
    payment_method_label: Optional[str]
    sales_note_text: Optional[str]
    ticket_footer_text: Optional[str]
    sales_note_extra_text: Optional[str]
    services_label: Optional[str]

    subtotal: float
    tax_amount: float
    total: float

    created_by: str
    created_at: datetime
    updated_at: datetime