import os
import logging

logger = logging.getLogger(__name__)

def export_markdown(cv_data: str, output_path: str):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cv_data)
    return True

def export_html(markdown_path: str, html_path: str = None):
    if not html_path:
        html_path = markdown_path.replace('.md', '.html')
        
    try:
        import markdown
        with open(markdown_path, 'r', encoding='utf-8') as f:
            text = f.read()
        html = markdown.markdown(text, extensions=['tables', 'sane_lists'])
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return True
    except ImportError:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write("<html><body><p>HTML Export requires 'markdown' package.</p></body></html>")
        return False

def export_pdf(html_path: str, pdf_path: str = None):
    if not pdf_path:
        pdf_path = html_path.replace('.html', '.pdf')
        
    try:
        from playwright.sync_api import sync_playwright
        abs_html_path = os.path.abspath(html_path)
        file_url = f"file:///{abs_html_path.replace(os.sep, '/')}"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(file_url, wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", print_background=True, margin={"top": "0cm", "right": "0cm", "bottom": "0cm", "left": "0cm"})
            browser.close()
        return True
    except Exception as e:
        logger.error(f"Playwright PDF generation failed: {e}")
        return False
