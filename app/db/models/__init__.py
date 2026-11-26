"""Modelos ORM.

Importar este pacote registra **todas** as tabelas em `Base.metadata`. O Alembic
depende disso: um modelo que não é importado aqui simplesmente não existe para o
autogenerate nem para o `create_all` de teste, e o erro aparece só em runtime.
"""

from app.db.models.enums import (
    AmbienteFiscal,
    OrigemFatura,
    ProvedorFiscal,
    ProvedorGuia,
    StatusApuracao,
    StatusFatura,
    StatusLote,
    StatusTenant,
    StatusWebhook,
    TipoDocumento,
)
from app.db.models.frete import FreteCredencial
from app.db.models.invoice import FiscalDocument, Invoice, InvoiceEvent
from app.db.models.ops import BatchJob, TaxAssessment, WebhookDelivery
from app.db.models.tenant import Tenant, TenantCertificate, TenantFiscalConfig

__all__ = [
    "AmbienteFiscal",
    "BatchJob",
    "FiscalDocument",
    "FreteCredencial",
    "Invoice",
    "InvoiceEvent",
    "OrigemFatura",
    "ProvedorFiscal",
    "ProvedorGuia",
    "StatusApuracao",
    "StatusFatura",
    "StatusLote",
    "StatusTenant",
    "StatusWebhook",
    "TaxAssessment",
    "Tenant",
    "TenantCertificate",
    "TenantFiscalConfig",
    "TipoDocumento",
    "WebhookDelivery",
]
