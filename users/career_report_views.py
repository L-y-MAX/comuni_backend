# -*- coding: utf-8 -*-
"""职业生涯发展报告：保存/读取 + 导出 Word。

导出不依赖 python-docx，直接构造一个最小合法 DOCX（zip + OOXML），
避免比赛前在服务器装新依赖。
"""

import re
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

REPORT_CACHE_TTL = 30 * 24 * 60 * 60


def _report_key(user_id) -> str:
    return f'career_report:{user_id}'


def _clean_line(line: str) -> str:
    line = re.sub(r'^#{1,6}\s*', '', line)
    line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
    line = re.sub(r'`([^`]*)`', r'\1', line)
    return line.strip()


def _run(text: str, bold: bool = False) -> str:
    props = '<w:rPr><w:b/></w:rPr>' if bold else ''
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _paragraph(text: str, bold: bool = False, center: bool = False) -> str:
    ppr = '<w:pPr><w:jc w:val="center"/></w:pPr>' if center else ''
    return f'<w:p>{ppr}{_run(text, bold)}</w:p>'


def build_docx(markdown: str, title: str) -> Path:
    reports_dir = Path(settings.MEDIA_ROOT) / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f'report-{uuid.uuid4().hex}.docx'
    path = reports_dir / filename

    body_parts = [_paragraph(title or '职业生涯发展报告', bold=True, center=True), '<w:p/>']
    for raw_line in markdown.splitlines():
        line = _clean_line(raw_line)
        if line:
            body_parts.append(_paragraph(line))
        else:
            body_parts.append('<w:p/>')

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(body_parts) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        '</w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '</Relationships>'
    )

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('word/document.xml', document_xml)

    return path


class CareerReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'report': cache.get(_report_key(request.user.id))})

    def post(self, request):
        payload = request.data
        if not isinstance(payload, dict):
            return Response(
                {'detail': '报告数据必须是 JSON 对象'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cache.set(_report_key(request.user.id), payload, REPORT_CACHE_TTL)
        return Response({'ok': True})


class CareerReportExportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        markdown = str(request.data.get('markdown') or '')
        title = str(request.data.get('title') or '职业生涯发展报告')
        export_format = str(request.data.get('format') or 'docx').lower()

        if not markdown.strip():
            return Response(
                {'detail': '报告内容为空，无法导出'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if export_format != 'docx':
            return Response(
                {'detail': '当前仅支持导出 Word（docx），请选择 Word 格式'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            path = build_docx(markdown, title)
        except Exception as exc:
            return Response(
                {'detail': f'生成 Word 失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        media_url = settings.MEDIA_URL or '/media/'
        if not media_url.endswith('/'):
            media_url += '/'
        file_url = request.build_absolute_uri(f'{media_url}reports/{path.name}')
        return Response({'file_url': file_url})
