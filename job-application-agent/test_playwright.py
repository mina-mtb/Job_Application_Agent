from playwright.sync_api import sync_playwright

def generate_pdf():
    html_content = "<h1>Playwright Test</h1><p>It works!</p>"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content)
        page.pdf(path="playwright_test.pdf", format="A4", print_background=True)
        browser.close()

if __name__ == "__main__":
    generate_pdf()
    print("PLAYWRIGHT_SUCCESS")
