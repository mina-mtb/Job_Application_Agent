import fitz
import os

def test_dynamic_layout():
    template_path = 'knowledge_base/processed_sources/Mina TAhmasebi Cv Template (2).pdf'
    
    if not os.path.exists(template_path):
        print("Template not found!")
        return

    doc = fitz.open(template_path)
    page = doc[0]

    # Search for headings
    profile_rects = page.search_for("PROFILE")
    skills_rects = page.search_for("SKILLS")
    edu_rects = page.search_for("EDUCATION")
    lang_rects = page.search_for("LANGUAGES")

    print(f"PROFILE: {profile_rects}")
    print(f"SKILLS: {skills_rects}")
    print(f"EDUCATION: {edu_rects}")
    print(f"LANGUAGES: {lang_rects}")

    # Calculate Profile Bounding Box
    if profile_rects and edu_rects:
        p_rect = profile_rects[0]
        e_rect = edu_rects[0]
        profile_box = fitz.Rect(p_rect.x0, p_rect.y1 + 5, 570, e_rect.y0 - 5)
        print(f"Calculated Profile Box: {profile_box}")
    else:
        print("Could not calculate Profile Box")

    # Calculate Skills Bounding Box
    if skills_rects and lang_rects:
        s_rect = skills_rects[0]
        l_rect = lang_rects[0]
        skills_box = fitz.Rect(s_rect.x0, s_rect.y1 + 5, 215, l_rect.y0 - 5)
        print(f"Calculated Skills Box: {skills_box}")
    else:
        print("Could not calculate Skills Box")

if __name__ == "__main__":
    test_dynamic_layout()
