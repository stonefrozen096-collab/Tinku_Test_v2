"""
Tinku Resume Builder — Interview Ready
Single column, ATS-friendly, clean professional layout
"""
import io
import re

def enhance_text(text):
    """Clean up text — capitalize first letter, strip extra spaces."""
    return text.strip().capitalize() if text else ""

def split_items(text):
    """Split comma or semicolon separated items."""
    return [i.strip() for i in re.split(r'[,;]', text) if i.strip()]

def build_resume_pdf(name, title, email, phone, skills, experience,
                     education, achievements, summary=""):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    HRFlowable, KeepTogether, Table, TableStyle)

    # ── Colors ──
    INDIGO     = colors.HexColor('#4F46E5')
    DARK       = colors.HexColor('#111827')
    GRAY       = colors.HexColor('#6B7280')
    LIGHT      = colors.HexColor('#F3F4F6')
    TEXT       = colors.HexColor('#1F2937')
    SUBTEXT    = colors.HexColor('#9CA3AF')
    WHITE      = colors.white

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer,
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        title=f"{name} - Resume",
        author="Tinku AI")

    story = []

    # ── Styles ──
    name_style = ParagraphStyle('Name',
        fontName='Helvetica-Bold', fontSize=26,
        textColor=DARK, leading=30,
        alignment=TA_LEFT, spaceAfter=2)

    title_style = ParagraphStyle('Title',
        fontName='Helvetica', fontSize=13,
        textColor=INDIGO, leading=16,
        alignment=TA_LEFT, spaceAfter=4)

    contact_style = ParagraphStyle('Contact',
        fontName='Helvetica', fontSize=9,
        textColor=GRAY, leading=12,
        alignment=TA_LEFT, spaceAfter=0)

    section_style = ParagraphStyle('Section',
        fontName='Helvetica-Bold', fontSize=10,
        textColor=INDIGO, leading=14,
        spaceBefore=14, spaceAfter=4,
        alignment=TA_LEFT)

    body_style = ParagraphStyle('Body',
        fontName='Helvetica', fontSize=10,
        textColor=TEXT, leading=15,
        spaceAfter=4, alignment=TA_JUSTIFY)

    bullet_style = ParagraphStyle('Bullet',
        fontName='Helvetica', fontSize=10,
        textColor=TEXT, leading=15,
        spaceAfter=3, leftIndent=12,
        firstLineIndent=0)

    summary_style = ParagraphStyle('Summary',
        fontName='Helvetica', fontSize=10,
        textColor=TEXT, leading=16,
        spaceAfter=4, alignment=TA_JUSTIFY)

    small_style = ParagraphStyle('Small',
        fontName='Helvetica', fontSize=8,
        textColor=SUBTEXT, leading=11,
        alignment=TA_CENTER)

    def section_heading(text):
        story.append(Paragraph(text.upper(), section_style))
        story.append(HRFlowable(width="100%", thickness=1.5,
                                color=INDIGO, spaceAfter=6))

    def bullet_item(text):
        story.append(Paragraph(f"▪  {enhance_text(text)}", bullet_style))

    # ════════════════════════════════
    # HEADER — Name, Title, Contact
    # ════════════════════════════════
    # Top accent bar
    story.append(Table([['']], colWidths=['100%'],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), INDIGO),
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [INDIGO]),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ])))
    story.append(Spacer(1, 10))

    story.append(Paragraph(name.upper(), name_style))
    story.append(Paragraph(title, title_style))

    # Contact row
    contact_parts = []
    if email: contact_parts.append(f"✉  {email}")
    if phone: contact_parts.append(f"  |  📞  {phone}")
    if contact_parts:
        story.append(Paragraph("".join(contact_parts), contact_style))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor('#E5E7EB'), spaceAfter=6))

    # ════════════════════════════════
    # PROFILE SUMMARY
    # ════════════════════════════════
    if summary:
        section_heading("Profile Summary")
        story.append(Paragraph(summary, summary_style))

    # ════════════════════════════════
    # EDUCATION
    # ════════════════════════════════
    if education and education.lower() != 'none':
        section_heading("Education")
        story.append(Paragraph(enhance_text(education), body_style))

    # ════════════════════════════════
    # SKILLS
    # ════════════════════════════════
    if skills and skills.lower() != 'none':
        section_heading("Skills")
        skill_list = split_items(skills)
        # Show skills in a clean wrapped row
        skill_text = "  •  ".join(skill_list)
        story.append(Paragraph(skill_text, body_style))

    # ════════════════════════════════
    # WORK EXPERIENCE
    # ════════════════════════════════
    if experience and experience.lower() != 'none':
        section_heading("Work Experience")
        jobs = [j.strip() for j in re.split(r'[;\n]', experience) if j.strip()]
        for job in jobs:
            bullet_item(job)

    # ════════════════════════════════
    # ACHIEVEMENTS & CERTIFICATIONS
    # ════════════════════════════════
    if achievements and achievements.lower() != 'none':
        section_heading("Achievements & Certifications")
        ach_list = split_items(achievements)
        for ach in ach_list:
            bullet_item(ach)

    # ════════════════════════════════
    # FOOTER
    # ════════════════════════════════
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor('#E5E7EB'), spaceAfter=6))
    story.append(Paragraph("Resume generated by Tinku AI", small_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


def build_resume_docx(name, title, email, phone, skills, experience,
                      education, achievements, summary=""):
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(1.8)
        section.bottom_margin = Cm(1.8)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    INDIGO = RGBColor(0x4F, 0x46, 0xE5)
    DARK   = RGBColor(0x11, 0x18, 0x27)
    GRAY   = RGBColor(0x6B, 0x72, 0x80)
    TEXT   = RGBColor(0x1F, 0x29, 0x37)

    def add_section_heading(label):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(label.upper())
        run.font.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = INDIGO
        # Bottom border
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single')
        bottom.set(qn('w:sz'), '8')
        bottom.set(qn('w:space'), '1')
        bottom.set(qn('w:color'), '4F46E5')
        pBdr.append(bottom)
        pPr.append(pBdr)

    def add_body(text, italic=False):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(enhance_text(text))
        run.font.size = Pt(10)
        run.font.italic = italic
        run.font.color.rgb = TEXT

    def add_bullet(text):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(enhance_text(text))
        run.font.size = Pt(10)
        run.font.color.rgb = TEXT

    # ── Header ──
    name_p = doc.add_paragraph()
    name_run = name_p.add_run(name.upper())
    name_run.font.size = Pt(24)
    name_run.font.bold = True
    name_run.font.color.rgb = DARK
    name_p.paragraph_format.space_after = Pt(2)

    title_p = doc.add_paragraph()
    title_run = title_p.add_run(title)
    title_run.font.size = Pt(13)
    title_run.font.color.rgb = INDIGO
    title_p.paragraph_format.space_after = Pt(3)

    # Contact
    contact_parts = []
    if email: contact_parts.append(f"✉ {email}")
    if phone: contact_parts.append(f"📞 {phone}")
    if contact_parts:
        cp = doc.add_paragraph("  |  ".join(contact_parts))
        cp.runs[0].font.size = Pt(9)
        cp.runs[0].font.color.rgb = GRAY
        cp.paragraph_format.space_after = Pt(6)

    # Separator
    sep = doc.add_paragraph()
    sep.paragraph_format.space_after = Pt(4)

    # Profile Summary
    if summary:
        add_section_heading("Profile Summary")
        add_body(summary)

    # Education
    if education and education.lower() != 'none':
        add_section_heading("Education")
        add_body(education)

    # Skills
    if skills and skills.lower() != 'none':
        add_section_heading("Skills")
        skill_list = split_items(skills)
        skills_text = "  •  ".join(skill_list)
        add_body(skills_text)

    # Experience
    if experience and experience.lower() != 'none':
        add_section_heading("Work Experience")
        jobs = [j.strip() for j in re.split(r'[;\n]', experience) if j.strip()]
        for job in jobs:
            add_bullet(job)

    # Achievements
    if achievements and achievements.lower() != 'none':
        add_section_heading("Achievements & Certifications")
        ach_list = split_items(achievements)
        for ach in ach_list:
            add_bullet(ach)

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph("Resume generated by Tinku AI")
    footer.runs[0].font.size = Pt(8)
    footer.runs[0].font.color.rgb = GRAY
    footer.runs[0].font.italic = True
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
