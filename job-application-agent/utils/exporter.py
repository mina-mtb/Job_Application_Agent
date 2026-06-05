import os

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
        html = markdown.markdown(text)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return True
    except ImportError:
        # Graceful fallback if markdown package is not installed
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write("<html><body><p>HTML Export requires 'markdown' package.</p></body></html>")
        return False

def export_pdf(html_path: str, pdf_path: str = None):
    if not pdf_path:
        pdf_path = html_path.replace('.html', '.pdf')
        
    try:
        import pdfkit
        pdfkit.from_file(html_path, pdf_path)
        return True
    except (ImportError, Exception) as e:
        # Graceful fallback if pdfkit or wkhtmltopdf is not installed
        with open(pdf_path, 'w', encoding='utf-8') as f:
            f.write(f"PDF Export Gracefully Skipped. Dependency missing or error: {e}")
        return False
