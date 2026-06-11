import fitz
import re
import yaml
import os

def extract_contact_info(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found.")
        return None

    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    
    print("--- RAW TEXT EXTRACTED ---")
    print(text[:1000]) # Print first 1000 chars to see structure
    print("--------------------------")

    # Regular expressions for extraction
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    linkedin_pattern = r'LinkedIn:\s*([^\s]+)'
    github_pattern = r'GitHub:\s*([^\s]+)'
    phone_pattern = r'Mobile:\s*(\+?\d[\d\s-]{8,}\d)'

    email = re.search(email_pattern, text)
    linkedin = re.search(linkedin_pattern, text)
    github = re.search(github_pattern, text)
    phone = re.search(phone_pattern, text)

    # For name and location
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    full_name = lines[0] if lines else "Unknown"
    
    # Location is likely the line before LinkedIn, but let's just use a regex for Sweden or standard format, or just look for the address line.
    location = ""
    for line in lines:
        if "Sweden" in line or "Gothenburg" in line:
            location = line
            break

    # Build full URLs
    ln_val = linkedin.group(1) if linkedin else ""
    gh_val = github.group(1) if github else ""
    
    if ln_val and not ln_val.startswith("http"):
        ln_val = f"https://linkedin.com/in/{ln_val}"
    if gh_val and not gh_val.startswith("http"):
        gh_val = f"https://github.com/{gh_val}"

    info = {
        "full_name": full_name,
        "location": location,
        "email": email.group(0) if email else "",
        "phone": phone.group(1) if phone else "",
        "linkedin": ln_val,
        "github": gh_val,
        "website": ""
    }

    print("--- EXTRACTED INFO ---")
    for k, v in info.items():
        print(f"{k}: {v}")

    return info

if __name__ == "__main__":
    pdf_path = 'knowledge_base/processed_sources/Mina TAhmasebi Cv Template (2).pdf'
    extract_contact_info(pdf_path)
