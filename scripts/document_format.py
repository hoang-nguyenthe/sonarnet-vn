"""Shared typography for the print-ready SonarNet documents."""
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIRECTORY = Path(os.environ.get(
    'SONARNET_DOCUMENT_FONT_DIR', '/System/Library/Fonts/Supplemental'
))
PAGE_MARGIN = 51.5
PAGE_NUMBER_Y = 37


def register_document_fonts(regular='Document', bold='DocumentBold'):
    fonts = {
        regular: 'Times New Roman.ttf',
        bold: 'Times New Roman Bold.ttf',
        f'{regular}Italic': 'Times New Roman Italic.ttf',
        f'{regular}BoldItalic': 'Times New Roman Bold Italic.ttf',
    }
    for name, filename in fonts.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIRECTORY / filename)))
    pdfmetrics.registerFontFamily(regular, normal=regular, bold=bold,
                                 italic=f'{regular}Italic', boldItalic=f'{regular}BoldItalic')


def page_number(canvas, number, font_name='Document'):
    width, _ = canvas._pagesize
    canvas.saveState()
    canvas.setFillColor(colors.black)
    canvas.setFont(font_name, 10)
    canvas.drawCentredString(width / 2, PAGE_NUMBER_Y, str(number))
    canvas.restoreState()
