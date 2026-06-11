import fitz
import os
import logging

def _find_best_fontsize(page_rect, text_rect, text, max_size=10.0, min_size=6.5, step=0.5):
    """
    Uses a dummy page to find the largest font size that fits the text
    inside text_rect without overflowing.
    """
    curr_size = max_size
    while curr_size >= min_size:
        dummy_doc = fitz.open()
        dummy_page = dummy_doc.new_page(width=page_rect.width, height=page_rect.height)
        rc = dummy_page.insert_textbox(text_rect, text, fontsize=curr_size, fontname="helv")
        dummy_doc.close()
        if rc >= 0:
            return curr_size, False
        curr_size -= step
        
    return min_size, True  # returns minimum size and True for overflow

def render_pdf_cv_template(template_pdf_path: str, output_pdf_path: str, profile_text: str, skills_text: str) -> dict:
    """
    Renders generated Profile and Skills text onto an existing PDF template.
    Dynamically detects regions based on headings, masks the placeholders,
    and writes the new text with an auto-fit font size.
    """
    result = {
        "success": False,
        "output_pdf_path": output_pdf_path,
        "warnings": [],
        "profile_text_fitted": True,
        "skills_text_fitted": True,
        "profile_overflow": False,
        "skills_overflow": False
    }
    
    if not os.path.exists(template_pdf_path):
        result["warnings"].append(f"Template not found: {template_pdf_path}")
        return result
        
    try:
        doc = fitz.open(template_pdf_path)
        
        if len(doc) < 1:
            result["warnings"].append("PDF has no pages.")
            return result
            
        page = doc[0]
        
        # 1. Dynamically calculate bounding boxes based on headings
        # We take the first match as the actual heading
        profile_rects = page.search_for("PROFILE")
        skills_rects = page.search_for("SKILLS")
        edu_rects = page.search_for("EDUCATION")
        lang_rects = page.search_for("LANGUAGES")
        
        # Default fallbacks
        profile_rect = fitz.Rect(230, 145, 570, 280)
        skills_rect = fitz.Rect(18, 315, 180, 490)
        
        if profile_rects and edu_rects:
            p_rect = profile_rects[0]
            e_rect = edu_rects[0]
            # y0 = bottom of PROFILE + 5, y1 = top of EDUCATION - 5
            profile_rect = fitz.Rect(p_rect.x0, p_rect.y1 + 5, 570, e_rect.y0 - 5)
            logging.info(f"Dynamically detected profile box: {profile_rect}")
        else:
            result["warnings"].append("Could not dynamically detect Profile bounds. Using default.")

        if skills_rects and lang_rects:
            s_rect = skills_rects[0]
            l_rect = lang_rects[0]
            # y0 = bottom of SKILLS + 5, y1 = top of LANGUAGES - 5
            skills_rect = fitz.Rect(s_rect.x0, s_rect.y1 + 5, 215, l_rect.y0 - 5)
            logging.info(f"Dynamically detected skills box: {skills_rect}")
        else:
            result["warnings"].append("Could not dynamically detect Skills bounds. Using default.")
        
        # 2. Redact placeholders
        for text in ["{{PROFILE}}", "{{SKILLS}}"]:
            rects = page.search_for(text)
            for r in rects:
                page.add_redact_annot(r)
        
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        
        # 3. Insert Profile
        profile_font = "helv"
        profile_color = (0.2, 0.2, 0.2) # Dark gray
        
        p_fontsize, p_overflow = _find_best_fontsize(page.rect, profile_rect, profile_text, max_size=10.0, min_size=6.5)
        
        if p_overflow:
            result["profile_overflow"] = True
            result["profile_text_fitted"] = False
            result["warnings"].append("Profile text overflowed its bounding box even at minimum font size.")
        
        # Draw Profile text
        # If it still overflows at min_size, expand the rect down temporarily so insert_textbox doesn't silently cut it
        draw_profile_rect = profile_rect
        if p_overflow:
            draw_profile_rect = fitz.Rect(profile_rect.x0, profile_rect.y0, profile_rect.x1, profile_rect.y1 + 500)
            
        page.insert_textbox(
            draw_profile_rect, 
            profile_text, 
            fontsize=p_fontsize, 
            fontname=profile_font, 
            color=profile_color,
            align=0
        )
            
        # 4. Insert Skills
        skills_font = "helv"
        skills_color = (0.2, 0.2, 0.2)
        
        s_fontsize, s_overflow = _find_best_fontsize(page.rect, skills_rect, skills_text, max_size=10.0, min_size=6.5)
        
        if s_overflow:
            result["skills_overflow"] = True
            result["skills_text_fitted"] = False
            result["warnings"].append("Skills text overflowed its bounding box even at minimum font size.")
            
        # Draw Skills text
        draw_skills_rect = skills_rect
        if s_overflow:
            draw_skills_rect = fitz.Rect(skills_rect.x0, skills_rect.y0, skills_rect.x1, skills_rect.y1 + 500)
            
        page.insert_textbox(
            draw_skills_rect, 
            skills_text, 
            fontsize=s_fontsize, 
            fontname=skills_font, 
            color=skills_color,
            align=0
        )
            
        # Save output
        doc.save(output_pdf_path, garbage=4, deflate=True)
        doc.close()
        
        result["success"] = True
        
    except Exception as e:
        result["warnings"].append(f"Failed to render PDF: {e}")
        
    return result

if __name__ == "__main__":
    # Test execution
    template_path = 'knowledge_base/processed_sources/Mina TAhmasebi Cv Template (2).pdf'
    output_path = 'test_pdf_overlay_output.pdf'
    
    test_profile = "TEST PROFILE REPLACEMENT - This is a short profile text for layout testing only. The quick brown fox jumps over the lazy dog. This text is meant to be slightly longer so we can test wrapping correctly. Let's add more text to make sure we see how auto-fit behaves when the text is very long. We want it to decrease the font size gracefully until it fits perfectly inside the bounding box without overlapping with the EDUCATION section below it."
    test_skills = "• C# / .NET\n• Azure / Cloud\n• Python / AI\n• REST APIs\n\nDatabase:\n• SQL Server\n• PostgreSQL\n\nOther:\n• Docker\n• Git"
    
    res = render_pdf_cv_template(template_path, output_path, test_profile, test_skills)
    print("Test result:", res)
    
    if res["success"]:
        # Render to PNG
        doc_in = fitz.open(template_path)
        doc_in[0].get_pixmap(dpi=150).save('original_template_page1.png')
        doc_in.close()
        
        doc_out = fitz.open(output_path)
        doc_out[0].get_pixmap(dpi=150).save('test_pdf_overlay_output_page1.png')
        doc_out.close()
        print("Generated PNGs successfully.")
