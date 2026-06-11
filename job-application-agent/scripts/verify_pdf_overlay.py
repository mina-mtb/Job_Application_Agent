import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import fitz

def verify_pdf_overlay():
    template_path = os.path.join(project_root, "templates", "cv", "Mina_Tahmasebi_CV_Template.pdf")
    output_path = os.path.join(project_root, "outputs", "test_pdf_overlay_output.pdf")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if not os.path.exists(template_path):
        print(f"Error: Template not found at {template_path}")
        return False
        
    doc = fitz.open(template_path)
    
    if len(doc) != 2:
        print(f"Warning: Expected 2 pages, found {len(doc)} pages.")
        
    page1 = doc[0]
    
    # User coordinates
    profile_rect = fitz.Rect(230, 145, 570, 280)
    skills_rect = fitz.Rect(18, 315, 180, 490)
    
    # Draw boxes for visual debugging
    page1.draw_rect(profile_rect, color=(1, 0, 0), width=1)
    page1.draw_rect(skills_rect, color=(0, 0, 1), width=1)
    
    # Insert Dummy Text
    dummy_profile = "This is a dynamically generated PROFILE.\n\nI am a highly skilled Backend Developer with extensive experience in modern cloud architecture, .NET core, and Azure. I thrive in challenging environments and enjoy building scalable distributed systems."
    dummy_skills = "• C#, .NET Core\n• Azure, AWS\n• Python, Go\n• Kubernetes, Docker\n• SQL Server, PostgreSQL\n• React, Angular"
    
    page1.insert_textbox(profile_rect, dummy_profile, fontsize=10, fontname="helv", color=(0, 0, 0))
    page1.insert_textbox(skills_rect, dummy_skills, fontsize=10, fontname="helv", color=(0, 0, 0))
    
    doc.save(output_path)
    doc.close()
    
    print(f"Overlay applied successfully!")
    print(f"Saved test output to: {output_path}")
    print("Please review the PDF visually to ensure no text overlaps with immutable elements.")
    return True

if __name__ == "__main__":
    verify_pdf_overlay()
