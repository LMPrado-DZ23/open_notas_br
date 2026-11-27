"""Modelos ORM.

Importar este pacote registra **todas** as tabelas em `Base.metadata`. O Alembic
depende disso: um modelo que não é importado aqui simplesmente não existe para o
autogenerate nem para o `create_all` de teste, e o erro aparece só em runtime.
"""

from app.db.models.certificado_uso import CertificadoUso
from app.db.models.credencial_municipal import CredencialMunicipalTenant
from app.db.models.dlq import ItemDLQ
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
from app.db.models.municipio import MunicipioNFSe
from app.db.models.ops import BatchJob, TaxAssessment, WebhookDelivery
from app.db.models.tax import CalculoAudit
from app.db.models.tenant import Tenant, TenantCertificate, TenantFiscalConfig
from app.db.models.webservice_sefaz import WebserviceSefaz

__all__ = [
    "AmbienteFiscal",
    "BatchJob",
    "CalculoAudit",
    "CertificadoUso",
    "CredencialMunicipalTenant",
    "FiscalDocument",
    "FreteCredencial",
    "Invoice",
    "InvoiceEvent",
    "ItemDLQ",
    "MunicipioNFSe",
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
    "WebserviceSefaz",
]
