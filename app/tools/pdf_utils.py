# app/tools/pdf_utils.py
import logging
from io import BytesIO
from weasyprint import HTML, CSS
from markdown import markdown

logger = logging.getLogger(__name__)


def markdown_to_html(md_content: str) -> str:
    """Convert markdown to HTML with styling optimized for a single-page PDF."""
    html_content = markdown(md_content)

    # Enhanced CSS for a compact, professional, single-page resume
    css_style = """
    <style>
        @page {
            size: A4; /* Standard A4 paper size */
            margin: 0.5in; /* Set reasonable margins for the page */
        }
        html, body {
            height: 100%; /* Ensure html and body take full height */
            margin: 0;
            padding: 0;
            overflow: hidden; /* Prevent content from flowing to a new page */
        }
        body {
            font-family: 'Arial', sans-serif;
            font-size: 10pt; /* Slightly smaller font size for compactness */
            line-height: 1.4; /* Adjust line height for readability */
            color: #333;
        }
        h1, h2, h3 {
            color: #2c3e50;
            margin: 0.5em 0 0.2em 0; /* Compact margins */
            page-break-after: avoid; /* Prevent page breaks after headings */
        }
        h1 {
            font-size: 22pt;
            border-bottom: 2px solid #3498db;
            padding-bottom: 4px;
            margin-bottom: 0.4em;
        }
        h2 {
            font-size: 14pt;
            border-bottom: 1px solid #e0e0e0;
            padding-bottom: 2px;
            margin-top: 0.8em;
        }
        ul {
            margin: 4px 0;
            padding-left: 20px;
            list-style-position: outside;
        }
        li {
            margin-bottom: 4px; /* Space out list items a bit */
            page-break-inside: avoid; /* Try to keep list items on the same page */
        }
        p {
            margin: 0 0 8px 0;
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


def render_to_pdf(content: str, is_markdown: bool = True, is_resume: bool = False) -> bytes:
    """
    Convert markdown or HTML content to PDF bytes.
    If is_resume is True, applies single-page optimized styling.
    """
    try:
        if is_markdown:
            # For resumes, we use our single-page optimized HTML conversion
            if is_resume:
                html_content = markdown_to_html(content)
            else:
                # Basic conversion for other documents like cover letters
                html_content = f"<html><body>{markdown(content)}</body></html>"
        else:
            html_content = content

        return HTML(string=html_content).write_pdf()

    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        raise