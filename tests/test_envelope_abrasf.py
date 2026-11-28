"""Envelope ABRASF: uma única declaração XML, em qualquer encoding.

O código prependava `<?xml ...?>` e o `etree.tostring(..., encoding=...)` emitia outra. Em UTF-8 o
`tostring` não declara por padrão e o envelope saía válido **por acidente**; em ISO-8859-1 (provedores
legados GINFES/DSF, citados no próprio docstring do módulo) saíam **duas** declarações e o envelope era
XML malformado — o provedor recusaria com erro de parse, não de negócio.
"""

from __future__ import annotations

import pytest
from app.nfse.drivers_abrasf import ErroAbrasf, envelopar
from lxml import etree

XML = b"<Dados><x>1</x></Dados>"


@pytest.mark.parametrize("encoding", ["UTF-8", "ISO-8859-1"])
def test_envelope_tem_uma_unica_declaracao(encoding: str) -> None:
    envelope = envelopar(XML, namespace="http://exemplo", encoding=encoding)

    assert envelope.count(b"<?xml") == 1, "duas declarações tornam o XML malformado"
    assert encoding.encode() in envelope


@pytest.mark.parametrize("encoding", ["UTF-8", "ISO-8859-1"])
def test_envelope_e_xml_valido(encoding: str) -> None:
    """O teste que faltava: fazer o parse do envelope gerado, não só procurar substring."""
    envelope = envelopar(XML, namespace="http://exemplo", encoding=encoding)

    raiz = etree.fromstring(envelope)

    assert etree.QName(raiz).localname == "Envelope"
    assert any(etree.QName(e).localname == "x" for e in raiz.iter())


def test_xml_fiscal_invalido_recusa() -> None:
    with pytest.raises(ErroAbrasf):
        envelopar(b"<nao-fechado>", namespace="http://exemplo")
