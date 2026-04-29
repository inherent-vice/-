from __future__ import annotations

import time
import threading
from collections.abc import Callable

from dart_app.utils.pdf import pdf_front_text


class RunDocumentCache:
    """Execution-scoped document de-duplication for DART workers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._locks: dict[tuple, threading.Lock] = {}
        self._values: dict[tuple, object] = {}

    def get_or_load(self, namespace, key, loader):
        cache_key = (str(namespace), *self._normalize_key(key))
        with self._lock:
            if cache_key in self._values:
                return self._values[cache_key]
            key_lock = self._locks.setdefault(cache_key, threading.Lock())
        with key_lock:
            with self._lock:
                if cache_key in self._values:
                    return self._values[cache_key]
            try:
                value = loader()
            except Exception:
                with self._lock:
                    if self._locks.get(cache_key) is key_lock:
                        self._locks.pop(cache_key, None)
                raise
            with self._lock:
                self._values[cache_key] = value
                self._locks.pop(cache_key, None)
            return value

    @staticmethod
    def _normalize_key(key):
        if isinstance(key, tuple):
            return tuple(str(item or "") for item in key)
        return (str(key or ""),)


class DartDocumentAccess:
    """Cached document accessors used by matching workflows."""

    def __init__(
        self,
        client,
        force_refresh=False,
        delay_seconds=0.0,
        shared_cache: RunDocumentCache | None = None,
    ):
        self.client = client
        self.force_refresh = bool(force_refresh)
        self.delay_seconds = float(delay_seconds or 0)
        self.shared_cache = shared_cache
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
            def load():
                value = self.client.get_index_html(rcp_no)
                self._delay()
                return value

            self._index_cache[rcp_no] = self._shared_or_load("index", rcp_no, load)
        return self._index_cache[rcp_no]

    def doc_info(self, rcp_no):
        rcp_no = str(rcp_no or "")
        if rcp_no not in self._doc_cache:
            self._doc_cache[rcp_no] = self._shared_or_load(
                "doc_info",
                rcp_no,
                lambda: self.client.parse_doc_info(self.index_html(rcp_no)),
            )
        return self._doc_cache[rcp_no]

    def pdf_for(self, rcp_no, dcm_no):
        key = (str(rcp_no or ""), str(dcm_no or ""))
        if key not in self._pdf_cache:
            def load():
                value = self.client.download_pdf(*key)
                self._delay()
                return value

            self._pdf_cache[key] = self._shared_or_load("pdf", key, load)
        return self._pdf_cache[key]

    def front_text(self, rcp_no, dcm_no):
        key = (str(rcp_no or ""), str(dcm_no or ""))
        if key not in self._text_cache:
            self._text_cache[key] = self._shared_or_load("front_text", key, lambda: self._load_front_text(*key))
        return self._text_cache[key]

    def _load_front_text(self, rcp_no, dcm_no):
        viewer_text = ""
        try:
            viewer_text = self.client.get_viewer_text_from_index(
                self.index_html(rcp_no), rcp_no, dcm_no
            )
        except Exception:
            viewer_text = ""
        if viewer_text:
            self._delay()
            return viewer_text
        pdf = self.pdf_for(rcp_no, dcm_no)
        return pdf_front_text(pdf, max_pages=5) if pdf else ""

    def opendart_enabled(self):
        opendart = getattr(self.client, "opendart", None)
        return bool(opendart and opendart.enabled())

    def document_text(self, rcp_no):
        rcp_no = str(rcp_no or "")
        if not self.opendart_enabled():
            return ""
        if rcp_no not in self._document_text_cache:
            self._document_text_cache[rcp_no] = self._shared_or_load(
                "document_text",
                (rcp_no, self.force_refresh),
                lambda: self._load_document_text(rcp_no),
            )
        return self._document_text_cache[rcp_no]

    def document_text_callback(self) -> Callable[[str], str] | None:
        return self.document_text if self.opendart_enabled() else None

    def _load_document_text(self, rcp_no):
        value = self.client.opendart.get_document_text(
            rcp_no,
            force_refresh=self.force_refresh,
        )
        self._delay()
        return value

    def _shared_or_load(self, namespace, key, loader):
        if self.shared_cache is None:
            return loader()
        return self.shared_cache.get_or_load(namespace, key, loader)
