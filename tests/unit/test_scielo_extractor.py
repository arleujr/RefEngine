from pathlib import Path

import fitz

from refengine.domain.enums import ExtractionMethod
from refengine.domain.models import PageText
from refengine.services.metadata_extractor import MetadataExtractor


def test_scielo_original_prefers_page_content_over_bad_pdf_metadata(tmp_path: Path) -> None:
    path = tmp_path / "article.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "DOI: 10.4025/actasciagron.v31i2.396")
    page.insert_text(
        (72, 100),
        "Qualidade fisiológica de sementes de cultivares e linhagens de soja no Estado de Minas Gerais",
    )
    page.insert_text(
        (72, 128),
        "Edmar Soares de Vasconcelos; Múcio Silva Reis; Tuneo Sediyama; Cosme Damião Cruz",
    )
    page.insert_text((72, 156), "Acta Scientiarum. Agronomy Maringá, v. 31, n. 2, p. 307-312, 2009")
    document.set_metadata(
        {"title": "18_396_Vasconcelos et al_Qualidade fisiologica", "author": "mrandreussi"}
    )
    document.save(path)
    document.close()
    text = fitz.open(path)[0].get_text("text")
    pages = [
        PageText(
            page_number=1, text=text, method=ExtractionMethod.NATIVE, character_count=len(text)
        )
    ]
    result = MetadataExtractor().extract(path, pages)
    assert (
        result.title.value
        == "Qualidade fisiológica de sementes de cultivares e linhagens de soja no Estado de Minas Gerais"
    )
    assert result.journal.value == "Acta Scientiarum. Agronomy"
    assert result.volume.value == "31"
    assert result.issue.value == "2"
    assert result.pages.value == "307-312"
    assert len(result.authors) == 4
