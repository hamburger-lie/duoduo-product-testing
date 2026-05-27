from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _methods_for_path(path: str) -> set[str]:
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return set(getattr(route, "methods", set()))
    return set()


def test_frontend_required_routes_are_registered() -> None:
    assert "GET" in _methods_for_path("/api/v1/reports/pdfs")
    assert "POST" in _methods_for_path("/api/v1/whitepapers/generate")
    assert "POST" in _methods_for_path("/api/v1/surveys/generate-stream")
    assert "GET" in _methods_for_path("/api/v1/reports/by-evaluation/{evaluation_id}/business")
    assert "POST" in _methods_for_path("/api/v1/reports/by-evaluation/{evaluation_id}/pdf")
    assert "DELETE" in _methods_for_path("/api/v1/evaluations/{evaluation_id}")


def test_whitepaper_viewer_static_page_is_served() -> None:
    response = TestClient(app).get("/whitepaper-static/index.html")

    assert response.status_code == 200
    assert "白皮书导出" in response.text


def test_whitepaper_viewer_visible_copy_is_chinese() -> None:
    response = TestClient(app).get("/whitepaper-static/index.html")

    assert response.status_code == 200
    hidden_english_phrases = [
        "BASES-lite",
        "Concept Score",
        "Top2Box",
        "Purchase Intent",
        "Voice of Customer",
        "Claims Validation",
        "Decision Threshold",
    ]
    for phrase in hidden_english_phrases:
        assert phrase not in response.text


def test_whitepaper_viewer_uses_compact_report_pdf_layout() -> None:
    response = TestClient(app).get("/whitepaper-static/index.html")

    assert response.status_code == 200
    html = response.text
    assert '.content-body {\n  padding: 44px 46px;\n  font-family: "SimSun", "Songti SC", serif;\n  font-size: 12px;\n  line-height: 1.72;' in html
    assert ".content-body h2 {\n  font-size: 17px;" in html
    assert "text-align: center;" in html
    assert 'font-family: "SimHei", "Microsoft YaHei", sans-serif;' in html
    assert ".content-body h3 {\n  font-size: 12px;" in html
    assert "border-top: none;" in html
    assert "border-bottom: none;" in html
    assert ".content-body table {\n  width: 100%;\n  border-collapse: collapse;\n  margin: 10px 0;\n  font-size: 14px;" in html


def test_whitepaper_viewer_adds_numbered_headings_and_toc() -> None:
    response = TestClient(app).get("/whitepaper-static/index.html")

    assert response.status_code == 200
    html = response.text
    assert "function numberWhitepaperHeadings(contentBody)" in html
    assert "function insertWhitepaperToc(contentBody)" in html
    assert "formatChineseSectionNumber(h2Index)" in html
    assert "h3.textContent = `${h2Index}.${h3Index} ${raw}`;" in html
    assert 'toc.className = "whitepaper-toc";' in html
    assert ".whitepaper-toc-title {\n  font-family: \"SimHei\", \"Microsoft YaHei\", sans-serif;\n  font-size: 18px;\n  font-weight: 700;\n  text-align: center;" in html
    assert ".whitepaper-toc-item {\n  display: flex;\n  justify-content: space-between;\n  gap: 18px;\n  border-bottom: none;" in html
    assert ".whitepaper-toc-item--h3 {\n  padding-left: 20px;\n  font-size: 12px;" in html


def test_whitepaper_pdf_export_button_generates_pdf_without_opening_print() -> None:
    response = TestClient(app).get("/whitepaper-static/index.html")

    assert response.status_code == 200
    html = response.text
    assert "async function exportPDF()" in html
    export_body = html.split("async function exportPDF()", 1)[1].split("// =============================================================", 1)[0]
    assert "await exportPDFLegacyImageMode();" in export_body
    assert "window.print()" not in export_body
    assert "@page" in html
    assert "break-before: page;" in html


def test_whitepaper_pdf_export_flows_content_without_section_gaps() -> None:
    response = TestClient(app).get("/whitepaper-static/index.html")

    assert response.status_code == 200
    html = response.text
    assert "forceNewPage: false" in html
    assert "return false;" in html
    assert "pdf.addPage();\n    pageState.y = margin;\n    pdf.addImage" not in html
    assert "border-left: none;" in html
    assert "border-bottom: none;" in html
    assert "border: none;" in html
