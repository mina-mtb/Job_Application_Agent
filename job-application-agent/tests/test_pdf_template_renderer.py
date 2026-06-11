import os
import fitz
import pytest
from core.pdf_template_renderer import render_pdf_cv_template

def create_test_pdf(path):
    doc = fitz.open()
    # Page 1
    page1 = doc.new_page()
    page1.insert_text((230, 145), "{{PROFILE}}")
    page1.insert_text((18, 315), "{{SKILLS}}")
    # Page 2
    page2 = doc.new_page()
    page2.insert_text((100, 100), "PAGE 2 TEXT")
    
    doc.save(path)
    doc.close()

def test_pdf_template_renderer_success(tmp_path):
    template_path = str(tmp_path / "test_template.pdf")
    output_path = str(tmp_path / "test_output.pdf")
    
    create_test_pdf(template_path)
    
    profile_text = "Generated Profile Text"
    skills_text = "Generated Skills Text"
    
    result = render_pdf_cv_template(template_path, output_path, profile_text, skills_text)
    
    assert result["success"] is True
    assert os.path.exists(output_path)
    
    # Verify original not overwritten (they have different paths and original is intact)
    assert os.path.exists(template_path)
    
    doc_out = fitz.open(output_path)
    # Output PDF still has 2 pages
    assert len(doc_out) == 2
    
    # Page 2 is unchanged
    text_page2 = doc_out[1].get_text()
    assert "PAGE 2 TEXT" in text_page2
    
    # Profile text appears
    text_page1 = doc_out[0].get_text()
    assert "Generated Profile Text" in text_page1
    assert "Generated Skills Text" in text_page1
    
    # Placeholders are gone
    assert "{{PROFILE}}" not in text_page1
    assert "{{SKILLS}}" not in text_page1

def test_pdf_template_renderer_overflow(tmp_path):
    template_path = str(tmp_path / "test_template_overflow.pdf")
    output_path = str(tmp_path / "test_output_overflow.pdf")
    
    create_test_pdf(template_path)
    
    # A huge text that definitely overflows
    profile_text = "Too Long " * 1000
    skills_text = "Too Long " * 1000
    
    result = render_pdf_cv_template(template_path, output_path, profile_text, skills_text)
    
    assert result["profile_overflow"] is True
    assert result["skills_overflow"] is True
    assert len(result["warnings"]) > 0

def test_pdf_template_renderer_missing_template():
    output_path = "does_not_matter.pdf"
    result = render_pdf_cv_template("nonexistent_file.pdf", output_path, "Profile", "Skills")
    
    assert result["success"] is False
    assert len(result["warnings"]) > 0
    assert "Template not found" in result["warnings"][0]
