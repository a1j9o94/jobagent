# app/tools/pdf_utils.py
import logging
from io import BytesIO
from typing import Tuple

from weasyprint import HTML
from markdown import markdown

logger = logging.getLogger(__name__)


# ------------- CONFIG -------------
MIN_FONT_PT = 8.0          # don’t go below this
START_FONT_PT = 9       # initial attempt
STEP_PT = 0.5              # decrement step
MARGIN_IN = 0.5            # left/right/top/bottom margin
# ----------------------------------


def _css_template(font_pt: float) -> str:
    """Return the CSS block with the requested base font size."""
    return f"""
    <style>
        @page {{
            size: letter;
            margin: {MARGIN_IN}in;
        }}
        html, body {{ height: 100%; margin: 0; padding: 0; overflow: hidden; }}
        body {{ font-family: 'Georgia','Times New Roman',serif;
                font-size: {font_pt}pt; line-height: 1.25; color:#111; }}
        /* headings */
        h1, h2, h3, h4, p, li {{ font-size: {font_pt}pt; margin:0; padding:0; }}
        h1 {{ text-align:center; font-weight:bold; font-size:{font_pt+5.5}pt; margin-bottom:4px; }}
        h2 {{ font-weight:bold; text-transform:uppercase; border-bottom:1px solid #333;
              margin:10px 0 6px; padding-bottom:1px; }}
        h3 {{ font-weight:bold; font-style:italic; }}
        /* lists */
        ul {{ list-style-type:disc; margin:0 0 6px 0; padding-left:18px; }}
        li {{ margin-bottom:3px; page-break-inside:avoid; }}
        /* contact line */
        h1 + p {{ text-align:center; margin:0 0 10px 0; }}
    </style>
    """


def markdown_to_html(md_content: str, font_pt: float) -> str:
    """Convert markdown to styled HTML with runtime-chosen font size."""
    html_body = markdown(md_content)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
            {_css_template(font_pt)}</head><body>{html_body}</body></html>"""


def _render_once(md_content: str, font_pt: float) -> Tuple[int, bytes]:
    """Render and return (page_count, pdf_bytes)."""
    html_obj = HTML(string=markdown_to_html(md_content, font_pt))
    doc = html_obj.render()
    return len(doc.pages), doc.write_pdf()


def render_to_pdf(content: str, is_markdown: bool = True) -> bytes:
    """Render markdown/HTML to a **one-page** PDF, auto-shrinking fonts if needed."""
    if not is_markdown:
        raise ValueError("Auto-fit only implemented for markdown input.")

    font = START_FONT_PT
    while font >= MIN_FONT_PT:
        pages, pdf_bytes = _render_once(content, font)
        if pages == 1:
            logger.debug("Rendered at %.1f pt → 1 page", font)
            return pdf_bytes
        font -= STEP_PT

    logger.warning("Hit minimum font (%.1f pt) but still >1 page; returning last render.", MIN_FONT_PT)
    return pdf_bytes   # possibly 2 pages, caller may decide how to handle


# CLI helper unchanged
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python pdf_utils.py <markdown_file> <output_file>")
        sys.exit(1)
    md_path, out_path = sys.argv[1], sys.argv[2]
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    pdf_data = render_to_pdf(md_text, is_markdown=True)
    with open(out_path, "wb") as f:
        f.write(pdf_data)
    print(f"PDF saved → {out_path}")