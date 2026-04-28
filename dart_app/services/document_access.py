from __future__ import annotations

import time
from collections.abc import Callable

from dart_app.utils.pdf import pdf_front_text


class DartDocumentAccess:
    """Cached document accessors used by matching workflows."""

    def __init__(self, client, force_refresh=False, delay_seconds=0.0):
        self.client = client
        self.force_refresh = bool(force_refresh)
        self.delay_seconds = float(delay_seconds or 0)
        self._index_cache: dict[str, str] = {}
        self._doc_cache: dict[str, tuple[str | None, list[str]]] = {}
        self._pdf_cache: dict[tuple[str, str], bytes | None] = {}
        self._text_cache: dict[tuple[str, str], str] = {}
        self._document_text_cache: dict[str, str] = {}

    def _delay(self):
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

    def index_html(self, rcp_no):
        rcp_no = str(rcp_no or "")
        if rcp_no not in self._index_cache:
            self._index_cache[rcp_no] = self.client.get_index_html(rcp_no)
            self._delay()
        return self._index_cache[rcp_no]

    def doc_info(self, rcp_no):
        rcp_no = str(rcp_no or "")
        if rcp_no not in self._doc_cache:
            self._doc_cache[rcp_no] = self.client.parse_doc_info(self.index_html(rcp_no))
        return self._doc_cache[rcp_no]

    def pdf_for(self, rcp_no, dcm_no):
        key = (str(rcp_no or ""), str(dcm_no or ""))
        if key not in self._pdf_cache:
            self._pdf_cache[key] = self.client.download_pdf(*key)
            self._delay()
        return self._pdf_cache[key]

    def front_text(self, rcp_no, dcm_no):
        key = (str(rcp_no or ""), str(dcm_no or ""))
        if key not in self._text_cache:
            viewer_text = ""
            try:
                viewer_text = self.client.get_viewer_text_from_index(
                    self.index_html(key[0]), key[0], key[1]
                )
            except Exception:
                viewer_text = ""
            if viewer_text:
                self._delay()
                self._text_cache[key] = viewer_text
            else:
                pdf = self.pdf_for(*key)
                self._text_cache[key] = pdf_front_text(pdf, max_pages=5) if pdf else ""
        return self._text_cache[key]

    def opendart_enabled(self):
        opendart = getattr(self.client, "opendart", None)
        return bool(opendart and opendart.enabled())

    def document_text(self, rcp_no):
        rcp_no = str(rcp_no or "")
        if not self.opendart_enabled():
            return ""
        if rcp_no not in self._document_text_cache:
            self._document_text_cache[rcp_no] = self.client.opendart.get_document_text(
                rcp_no,
                force_refresh=self.force_refresh,
            )
            self._delay()
        return self._document_text_cache[rcp_no]

    def document_text_callback(self) -> Callable[[str], str] | None:
        return self.document_text if self.opendart_enabled() else None
