"""PDF generation service using WeasyPrint."""
import logging

from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

logger = logging.getLogger(__name__)


def render_html_to_pdf(html_content: str) -> bytes:
    """
    Convert HTML content to PDF bytes.

    Args:
        html_content: Complete HTML document string

    Returns:
        PDF file content as bytes
    """
    font_config = FontConfiguration()

    # CSS для улучшения отображения в PDF
    pdf_css = CSS(string='''
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: sans-serif;
        }
    ''', font_config=font_config)

    html = HTML(string=html_content)
    pdf_bytes = html.write_pdf(stylesheets=[pdf_css], font_config=font_config)

    logger.info("PDF generated successfully, size: %d bytes", len(pdf_bytes))
    return pdf_bytes
