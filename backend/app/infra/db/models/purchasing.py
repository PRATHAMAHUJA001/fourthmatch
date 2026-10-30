"""Purchasing ORM: vendors, POs, GRNs, invoices, deliveries. Money = int paise."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.session import Base

if TYPE_CHECKING:
    from app.infra.db.models.perception import SamRun, Track


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    gstin: Mapped[str] = mapped_column(String(15), unique=True)
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    primary_category: Mapped[str] = mapped_column(String(32))
    contact_name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(160))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="vendor")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="open")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    total_paise: Mapped[int] = mapped_column(Integer, default=0)
    scenario_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    vendor: Mapped[Vendor] = relationship(back_populates="purchase_orders")
    lines: Mapped[list[PoLine]] = relationship(back_populates="po", cascade="all, delete-orphan")
    grns: Mapped[list[Grn]] = relationship(back_populates="po", cascade="all, delete-orphan")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="po", cascade="all, delete-orphan")
    deliveries: Mapped[list[Delivery]] = relationship(back_populates="po", cascade="all, delete-orphan")


class PoLine(Base):
    __tablename__ = "po_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(32))
    sku: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(16))
    qty_ordered: Mapped[int] = mapped_column(Integer)
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    tolerance_pct: Mapped[float] = mapped_column(Float)
    line_total_paise: Mapped[int] = mapped_column(Integer)

    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class Grn(Base):
    __tablename__ = "grns"

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    received_date: Mapped[date] = mapped_column(Date)
    storekeeper_name: Mapped[str] = mapped_column(String(120))
    signed: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="accepted")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    po: Mapped[PurchaseOrder] = relationship(back_populates="grns")
    lines: Mapped[list[GrnLine]] = relationship(back_populates="grn", cascade="all, delete-orphan")


class GrnLine(Base):
    __tablename__ = "grn_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("grns.id"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("po_lines.id"), index=True)
    qty_received: Mapped[int] = mapped_column(Integer)
    qty_damaged: Mapped[int] = mapped_column(Integer, default=0)

    grn: Mapped[Grn] = relationship(back_populates="lines")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(48), index=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    total_paise: Mapped[int] = mapped_column(Integer)
    gst_paise: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    po: Mapped[PurchaseOrder] = relationship(back_populates="invoices")
    lines: Mapped[list[InvoiceLine]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("po_lines.id"), index=True)
    qty_invoiced: Mapped[int] = mapped_column(Integer)
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    line_total_paise: Mapped[int] = mapped_column(Integer)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    grn_id: Mapped[int | None] = mapped_column(ForeignKey("grns.id"), nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    video_file_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="recorded")

    po: Mapped[PurchaseOrder] = relationship(back_populates="deliveries")
    tracks: Mapped[list[Track]] = relationship(back_populates="delivery", cascade="all, delete-orphan")
    sam_runs: Mapped[list[SamRun]] = relationship(back_populates="delivery", cascade="all, delete-orphan")

