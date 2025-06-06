# app/pdf_utils.py
import logging
from io import BytesIO
from weasyprint import HTML, CSS
from markdown import markdown

logger = logging.getLogger(__name__)


def markdown_to_html(md_content: str) -> str:
    """Convert markdown to HTML with basic styling."""
    html_content = markdown(md_content)

    # Basic CSS for professional documents
    css_style = """
    <style>
    body {
        font-family: 'Arial', sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }
    h1, h2, h3 {
        color: #2c3e50;
        margin-top: 0;
    }
    h1 {
        border-bottom: 2px solid #3498db;
        padding-bottom: 10px;
    }
    ul {
        margin: 10px 0;
        padding-left: 20px;
    }
    </style>
    """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        {css_style}
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """


def render_to_pdf(content: str, is_markdown: bool = True) -> bytes:
    """Convert markdown or HTML content to PDF bytes."""
    try:
        if is_markdown:
            html_content = markdown_to_html(content)
        else:
            html_content = content
        
        # This is the most direct way to use weasyprint and should be correct.
        return HTML(string=html_content).write_pdf()

    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        raise
