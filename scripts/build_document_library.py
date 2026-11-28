"""Build printable supporting documents and a same-site PDF preview catalog."""
from __future__ import annotations

import argparse
from hashlib import file_digest
from html import escape
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urljoin

from markdown_it import MarkdownIt
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from document_format import PAGE_MARGIN, page_number, register_document_fonts

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://hoang-nguyenthe.github.io/sonarnet-vn/'
SOURCE = 'https://github.com/hoang-nguyenthe/sonarnet-vn/blob/chang-2/'
MD = MarkdownIt('commonmark').enable('table')


def inline(token, source_url):
    out = []
    for item in token.children or ():
        match item.type:
            case 'text' | 'code_inline':
                out.append(escape(item.content, quote=False))
            case 'softbreak':
                out.append(' ')
            case 'hardbreak':
                out.append('<br/>')
            case 'strong_open':
                out.append('<b>')
            case 'strong_close':
                out.append('</b>')
            case 'em_open':
                out.append('<i>')
            case 'em_close':
                out.append('</i>')
            case 'link_open':
                link = urljoin(source_url, item.attrGet('href') or '')
                out.append(f'<link href="{escape(link, quote=True)}" color="#000000">')
            case 'link_close':
                out.append('</link>')
            case _:
                out.append(escape(item.content, quote=False))
    return ''.join(out)


def markdown_pdf(text, output, title, source_url, *, compact=False):
    register_document_fonts()
    body = ParagraphStyle('body',fontName='Document',fontSize=11,leading=12.8 if compact else 14,
                          firstLineIndent=18,alignment=TA_JUSTIFY,spaceAfter=4 if compact else 6)
    heading = ParagraphStyle('heading',parent=body,fontName='DocumentBold',fontSize=12,
                             leading=15,firstLineIndent=0,alignment=TA_LEFT,
                             spaceBefore=9,spaceAfter=5,keepWithNext=True)
    cover = ParagraphStyle('title',parent=heading,fontSize=16,leading=19,alignment=TA_CENTER,
                           spaceBefore=0,spaceAfter=12,keepWithNext=True)
    cell = ParagraphStyle('cell',parent=body,fontSize=10,leading=12,firstLineIndent=0,
                          alignment=TA_LEFT,spaceAfter=0)
    head_cell = ParagraphStyle('head-cell',parent=cell,fontName='DocumentBold',alignment=TA_CENTER)
    listed = ParagraphStyle('list',parent=body,leftIndent=18,firstLineIndent=0,
                           bulletIndent=4,spaceAfter=2.5 if compact else 4)
    code = ParagraphStyle('code',parent=body,fontName='Courier',fontSize=8,leading=10,
                         firstLineIndent=0,leftIndent=5,alignment=TA_LEFT,spaceBefore=4,spaceAfter=6)
    tokens = MD.parse(text)
    story = [Paragraph(escape(title.upper()),cover)]
    width = A4[0]-2*PAGE_MARGIN-12
    pending = None
    lists = []
    inside_table = False
    rows = []
    heading_n = 0
    for token in tokens:
        match token.type:
            case 'heading_open':
                pending = 'skip' if token.tag=='h1' else 'heading'
            case 'bullet_list_open':
                lists.append(None)
            case 'ordered_list_open':
                lists.append(int(token.attrGet('start') or 1))
            case 'bullet_list_close' | 'ordered_list_close':
                lists.pop()
            case 'list_item_open':
                pending = 'list'
            case 'paragraph_open':
                if pending!='list':
                    pending='body'
            case 'table_open':
                inside_table=True
                rows=[]
            case 'tr_open':
                rows.append([])
            case 'table_close':
                columns=len(rows[0])
                proportions=[.31,.69] if columns==2 else [1/columns]*columns
                cells=[[Paragraph(value,head_cell if j==0 else cell) for value in row]
                       for j,row in enumerate(rows)]
                table=Table(cells,colWidths=[width*w for w in proportions],repeatRows=1,hAlign='LEFT',
                    style=[('GRID',(0,0),(-1,-1),.45,colors.black),
                           ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                           ('TOPPADDING',(0,0),(-1,-1),3 if compact else 4),
                           ('BOTTOMPADDING',(0,0),(-1,-1),3 if compact else 4)])
                story.extend([table,Spacer(1,8)])
                inside_table=False
            case 'inline':
                value=inline(token,source_url)
                if inside_table:
                    rows[-1].append(value)
                elif pending=='heading':
                    heading_n+=1
                    story.append(Paragraph(f'{heading_n}. {value}',heading))
                elif pending=='list':
                    number=lists[-1]
                    marker='-' if number is None else f'{number}.'
                    if number is not None:
                        lists[-1]+=1
                    story.append(Paragraph(value,listed,bulletText=marker))
                elif pending!='skip':
                    story.append(Paragraph(value,body))
                pending=None
            case 'fence' | 'code_block':
                story.append(Preformatted(token.content.rstrip(),code,maxLineLength=95,
                                          splitChars=' /_-=.',newLineChars='  '))
    SimpleDocTemplate(str(output),pagesize=A4,leftMargin=PAGE_MARGIN,rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,bottomMargin=48,title=title,author='SonarNet Việt Nam').build(
        story,onFirstPage=lambda c,d:page_number(c,d.page),onLaterPages=lambda c,d:page_number(c,d.page))


def file_sha(path):
    with path.open('rb') as source:
        return file_digest(source,'sha256').hexdigest()


def previews(pdf, output):
    output.mkdir(exist_ok=True,parents=True)
    with TemporaryDirectory(prefix='sonarnet-pdf-preview-') as directory:
        prefix=Path(directory)/'p'
        subprocess.run(['pdftoppm','-scale-to','1500','-png',str(pdf),str(prefix)],check=True)
        pages=sorted(Path(directory).glob('p-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
        for number,page in enumerate(pages,1):
            with Image.open(page) as img:
                img.save(output/f'{number}.webp',quality=90,method=4)
    for unused in output.glob('*.webp'):
        if unused.stem.isdigit() and int(unused.stem)>len(pages):
            unused.unlink()
    return len(pages)


def library_html(documents):
    cards=[]
    for ident,doc in documents.items():
        pdf=escape(doc['pdf'],quote=True)
        title=escape(doc['title'])
        cards.append(f'''<article class="document-card">
  <h2>{title}</h2><p class="document-meta">PDF · {doc['pages']} trang</p>
  <div class="document-actions">
    <a class="document-button" href="{pdf}" data-document="{ident}" aria-label="Xem {title}">Xem</a>
    <a class="document-button secondary" href="{pdf}" download aria-label="Tải về {title}">Tải về</a>
  </div>
</article>''')
    return '''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thư viện tài liệu · SonarNet Việt Nam</title>
<link rel="stylesheet" href="viewer.css">
<script src="documents.js" defer></script><script src="viewer.js" defer></script></head>
<body class="document-library"><header class="library-header"><a href="../index.html">SonarNet Việt Nam</a>
<nav aria-label="Điều hướng"><a href="../index.html">Minh chứng Chặng 1</a><a href="../chang2/index.html">Minh chứng Chặng 2</a></nav></header>
<main class="library-shell"><h1>Tài liệu SonarNet</h1>
<p>Báo cáo và văn bản được dàn trang PDF A4. Bấm <strong>Xem</strong> để đọc ngay trên trang.</p>
<div class="document-grid">'''+'\n'.join(cards)+'''</div></main></body></html>
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chang1',type=Path,required=True)
    parser.add_argument('--filing',type=Path,default=ROOT/'reports/final/chang2/DIEN_CONG.md')
    options=parser.parse_args()
    folder=ROOT/'web/tai-lieu'
    files=folder/'tai-ve'
    files.mkdir(exist_ok=True,parents=True)

    filing=options.filing.read_text()
    specs=(
        ('tai-lap-chang-2','Hướng dẫn tái lập Chặng 2',
         (ROOT/'reports/final/chang2/PROTOCOL.md').read_text(),SOURCE+'reports/final/chang2/PROTOCOL.md'),
        ('dien-cong-chang-2','Hướng dẫn điền cổng Chặng 2',filing,SITE+'chang2/'),
        ('ke-khai-ai-chang-1','Kê khai hỗ trợ AI Chặng 1',
         (ROOT/'docs/AI_DECLARATION_CHANG1.md').read_text(),SOURCE+'docs/AI_DECLARATION_CHANG1.md'),
    )
    public={
        'bao-cao-chang-1':('Báo cáo cải tiến Chặng 1','../data/bao-cao-chang-1.pdf',options.chang1),
        'bao-cao-chang-2':('Báo cáo cải tiến Chặng 2','../chang2/SonarNet_Bao_cao_cai_tien_Chang2.pdf',
                          ROOT/'web/chang2/SonarNet_Bao_cao_cai_tien_Chang2.pdf'),
    }
    for ident,title,text,url in specs:
        path=files/(ident+'.pdf')
        markdown_pdf(text,path,title,url,compact=ident=='ke-khai-ai-chang-1')
        public[ident]=(title,'tai-ve/'+path.name,path)
    documents={}
    for ident,(title,url,pdf) in public.items():
        preview='xem/'+ident
        count=previews(pdf,folder/preview)
        documents[ident]=dict(title=title,pdf=url,preview=preview,pages=count,sha256=file_sha(pdf))
        print(ident,count,'pages',flush=True)
    (folder/'documents.js').write_text('window.SonarNetDocuments = '+json.dumps(documents,ensure_ascii=False,indent=2)+'\n')
    (folder/'index.html').write_text(library_html(documents))


if __name__=='__main__':
    main()
