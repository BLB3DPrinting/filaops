"""
Catalog models for B2B product visibility control.

Catalogs allow admins to:
- Create product groupings (e.g., "Public", "KOA Custom", "Wholesale Partners")
- Assign products to one or more catalogs
- Assign customers to one or more catalogs
- Portal shows products from customer's assigned catalogs + public catalogs

Core owns the catalog table definitions (PR-06). PRO consumes them via
filaops_pro/routes/catalogs.py and adds tier-aware pricing on top.
"""
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Catalog(Base):
    """
    Catalog definition for product visibility grouping.

    Examples:
    - PUBLIC: Default catalog, visible to all customers
    - KOA-CUSTOM: Custom products only for KOA Kampgrounds
    - WHOLESALE: Products available to wholesale partners
    """
    __tablename__ = "catalogs"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    is_default = Column(Boolean, nullable=False, default=False)
    is_public = Column(Boolean, nullable=False, default=True, index=True)

    sort_order = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    catalog_products = relationship(
        "CatalogProduct", back_populates="catalog", cascade="all, delete-orphan"
    )
    customer_catalogs = relationship(
        "CustomerCatalog", back_populates="catalog", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Catalog(code='{self.code}', name='{self.name}', public={self.is_public})>"


class CatalogProduct(Base):
    """
    Many-to-many relationship between catalogs and products with optional
    catalog-specific price override.
    """
    __tablename__ = "catalog_products"

    id = Column(Integer, primary_key=True, index=True)
    catalog_id = Column(
        Integer,
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price_override = Column(Numeric(12, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    catalog = relationship("Catalog", back_populates="catalog_products")
    product = relationship("Product")

    def __repr__(self) -> str:
        return (
            f"<CatalogProduct(catalog_id={self.catalog_id}, "
            f"product_id={self.product_id})>"
        )

    @property
    def effective_price(self) -> Decimal:
        """Catalog-specific price override, or fall back to product selling price."""
        if self.price_override is not None:
            return Decimal(str(self.price_override))
        return Decimal(str(self.product.selling_price)) if self.product else Decimal("0")


class CustomerCatalog(Base):
    """
    Many-to-many between customer-users and catalogs.

    customer_id references users.id because Core stores customers as User
    records with account_type='customer' (not in the customers table).
    """
    __tablename__ = "customer_catalogs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    catalog_id = Column(
        Integer,
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    customer = relationship("User")
    catalog = relationship("Catalog", back_populates="customer_catalogs")

    def __repr__(self) -> str:
        return (
            f"<CustomerCatalog(customer_id={self.customer_id}, "
            f"catalog_id={self.catalog_id})>"
        )
