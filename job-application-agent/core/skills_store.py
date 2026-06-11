import os
import re

def load_candidate_skills() -> list[str]:
    skills = []
    
    # 1. Parse from base CV
    base_cv_path = os.path.join("profile", "mina_base_cv.md")
    if os.path.exists(base_cv_path):
        with open(base_cv_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract the "## Skills" section
        skills_section_match = re.search(r'^##\s+Skills\s*(.*?)(?:^##\s|\Z)', content, re.MULTILINE | re.DOTALL)
        if skills_section_match:
            skills_text = skills_section_match.group(1).strip()
            for line in skills_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                # Drop bold categories that are on their own lines like "**Programming**"
                if line.startswith('**') and line.endswith('**'):
                    continue
                    
                # Drop markdown bullets
                line = re.sub(r'^[-*]\s*', '', line)
                # Drop bold category labels inline (text before a ":")
                if ':' in line:
                    line = line.split(':', 1)[1]
                
                # Split remaining text on commas
                parts = line.split(',')
                for p in parts:
                    clean_p = p.strip()
                    if clean_p:
                        skills.append(clean_p)

    # 2. Parse from confirmed_skills.md
    confirmed_path = os.path.join("profile", "confirmed_skills.md")
    if os.path.exists(confirmed_path):
        with open(confirmed_path, 'r', encoding='utf-8') as f:
            for line in f:
                clean_line = line.strip()
                if clean_line:
                    skills.append(clean_line)
                    
    # Return de-duplicated list of non-empty skill strings
    # Preserve order somewhat
    seen = set()
    result = []
    for s in skills:
        if s.lower() not in seen:
            seen.add(s.lower())
            result.append(s)
            
    return result

def add_confirmed_skill(skill: str) -> None:
    skill = skill.strip()
    if not skill:
        return
        
    confirmed_path = os.path.join("profile", "confirmed_skills.md")
    
    # Check if already exists
    existing = set()
    if os.path.exists(confirmed_path):
        with open(confirmed_path, 'r', encoding='utf-8') as f:
            existing = {line.strip().lower() for line in f if line.strip()}
            
    if skill.lower() not in existing:
        with open(confirmed_path, 'a', encoding='utf-8') as f:
            f.write(skill + '\n')
