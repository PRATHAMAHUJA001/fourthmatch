"""Legacy shim — canonical ORM is app.infra.db.models. Kept for seed imports.

Money is integer paise everywhere. Counts in tracks come only from SAM 3.1.
Verdicts: approve | hold_payment | human_review (weak evidence -> human_review).
"""
from app.infra.db.models import (  # noqa: F401
    DamageFlag,
    Decision,
    Delivery,
    EvidencePack,
    Grn,
    GrnLine,
    Invoice,
    InvoiceLine,
    Job,
    JobEvent,
    ModelCall,
    PerceptionResult,
    PoLine,
    PurchaseOrder,
    Rule,
    SamRun,
    Track,
    Vendor,
)
