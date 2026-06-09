import urllib.request
import urllib.error
import re
import html
import json

def extract_from_json_ld(html_content):
    """Attempt to extract structured job data from JSON-LD blocks."""
    json_ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_content, re.IGNORECASE | re.DOTALL)
    for match in json_ld_matches:
        try:
            data = json.loads(match)
            if data.get('@type') == 'JobPosting':
                return {
                    "title": data.get("title", ""),
                    "company": data.get("hiringOrganization", {}).get("name", ""),
                    "location": data.get("jobLocation", {}).get("address", {}).get("addressLocality", ""),
                    "description": data.get("description", "")
                }
        except json.JSONDecodeError:
            continue
    return None

def extract_from_meta_tags(html_content):
    """Attempt to extract data from meta tags like og:title."""
    title_match = re.search(r'<meta property="og:title" content="(.*?)"', html_content, re.IGNORECASE)
    title = html.unescape(title_match.group(1)) if title_match else ""
    return {"title": title}

def fetch_public_job_data(url: str) -> dict:
    """
    Safely fetches public job data from a given URL without cookies, sessions, or browser automation.
    If the page is behind an auth wall or parsing fails, it fails gracefully.
    Returns a dict with 'title', 'company', 'location', 'description', 'confidence', 'warning'.
    """
    if not url.startswith("http"):
        return {"error": "Invalid URL"}
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            
            # 1. Try JSON-LD first
            data = extract_from_json_ld(content)
            
            # 2. If no JSON-LD, fallback to manual parsing
            if not data:
                data = {}
                meta_data = extract_from_meta_tags(content)
                
                # Title
                title_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
                data['title'] = html.unescape(title_match.group(1).strip()) if title_match else meta_data.get('title', '')
                
                # Company
                company_match = re.search(r'class="topcard__org-name-link[^>]*>(.*?)</a>', content, re.IGNORECASE | re.DOTALL)
                if not company_match:
                    company_match = re.search(r'<a[^>]*data-tracking-control-name="public_jobs_topcard-org-name"[^>]*>(.*?)</a>', content, re.IGNORECASE | re.DOTALL)
                data['company'] = html.unescape(company_match.group(1).strip()) if company_match else ""
                
                # Location
                location_match = re.search(r'class="topcard__flavor topcard__flavor--bullet"[^>]*>(.*?)</span>', content, re.IGNORECASE | re.DOTALL)
                data['location'] = html.unescape(location_match.group(1).strip()) if location_match else ""
                
                # Description
                desc_match = re.search(r'class="show-more-less-html__markup[^>]*>(.*?)</div>', content, re.IGNORECASE | re.DOTALL)
                if desc_match:
                    raw_desc = desc_match.group(1).strip()
                    # Clean up HTML tags
                    clean_desc = re.sub(r'<[^>]+>', '\n', raw_desc)
                    data['description'] = html.unescape(re.sub(r'\n\s*\n', '\n\n', clean_desc).strip())
                else:
                    data['description'] = ""

            # Clean HTML from JSON-LD description just in case
            if data.get('description'):
                data['description'] = html.unescape(re.sub(r'<[^>]+>', '\n', data['description']).strip())

            # Check confidence
            missing_fields = [k for k in ['title', 'company', 'location', 'description'] if not data.get(k)]
            
            # Auth wall check
            if "authwall" in content.lower() or "sign in to linkedin" in content.lower():
                data['warning'] = "Page might be partially blocked by an auth wall."
                
            if missing_fields:
                data['confidence'] = "low"
                warn_msg = f"Could not confidently extract: {', '.join(missing_fields)}. Please fill manually."
                data['warning'] = f"{data.get('warning', '')} {warn_msg}".strip()
            else:
                data['confidence'] = "high"
                
            return data
            
    except urllib.error.URLError as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error parsing URL: {str(e)}"}
