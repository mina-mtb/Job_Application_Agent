import sys

try:
    from weasyprint import HTML
    html = HTML(string="<h1>Test</h1>")
    html.write_pdf("weasyprint_test.pdf")
    print("WEASYPRINT_SUCCESS")
except Exception as e:
    print("WEASYPRINT_FAILED")
    print(str(e))
