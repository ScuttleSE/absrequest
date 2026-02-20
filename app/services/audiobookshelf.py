import requests
from flask import current_app


class AudiobookshelfClient:
    """HTTP client for the Audiobookshelf REST API.

    All public methods return empty/falsy values gracefully when ABS is not
    configured or when network / API errors occur.
    """

    TIMEOUT = 10  # seconds

    def __init__(self) -> None:
        self._base_url: str = current_app.config.get('AUDIOBOOKSHELF_URL', '').rstrip('/')
        self._token: str = current_app.config.get('AUDIOBOOKSHELF_API_TOKEN', '')

    # ── Internal helpers ──────────────────────────────────────────────────────

    @property
    def _configured(self) -> bool:
        return bool(self._base_url and self._token)

    @property
    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._token}',
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params: dict | None = None):
        """Make a GET request; returns the Response or None on error."""
        try:
            resp = requests.get(
                f'{self._base_url}{path}',
                headers=self._headers,
                params=params,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            return resp
        except Exception:
            return None

    @staticmethod
    def _fmt_duration(seconds) -> str | None:
        """Format a duration in seconds as 'Xh Ym'."""
        try:
            total = int(float(seconds))
            h, m = divmod(total, 3600)
            m = m // 60
            return f'{h}h {m}m' if h else f'{m}m'
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_item(raw: dict, base_url: str, token: str) -> dict:
        """Flatten an ABS item dict into the fields we care about."""
        media = raw.get('media', {})
        meta = media.get('metadata', {})
        item_id = raw.get('id', '')

        # ABS exposes authorName (pre-formatted string) and/or authors list
        author = meta.get('authorName') or ', '.join(
            a.get('name', '') for a in meta.get('authors', []) if a.get('name')
        ) or None

        narrator = meta.get('narratorName') or ', '.join(
            n.get('name', '') for n in meta.get('narrators', []) if n.get('name')
        ) or None

        # Cover: pass token as query param so <img> tags can load it
        cover_url = (
            f'{base_url}/api/items/{item_id}/cover?token={token}' if item_id else None
        )

        return {
            'id': item_id,
            'title': meta.get('title', ''),
            'author': author,
            'narrator': narrator,
            'cover_url': cover_url,
            'duration': AudiobookshelfClient._fmt_duration(media.get('duration')),
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Return True if ABS is reachable and the token is valid."""
        if not self._configured:
            return False
        return self._get('/api/libraries') is not None

    def get_libraries(self) -> list[dict]:
        """Return book libraries from ABS (mediaType == 'book')."""
        if not self._configured:
            return []
        resp = self._get('/api/libraries')
        if resp is None:
            return []
        try:
            data = resp.json()
            return [
                lib for lib in data.get('libraries', [])
                if lib.get('mediaType') == 'book'
            ]
        except Exception:
            return []

    def get_library_items(
        self,
        library_id: str,
        page: int = 0,
        limit: int = 50,
    ) -> dict:
        """Return one page of items from a library."""
        if not self._configured:
            return {'results': [], 'total': 0}
        resp = self._get(
            f'/api/libraries/{library_id}/items',
            params={'limit': limit, 'page': page},
        )
        if resp is None:
            return {'results': [], 'total': 0}
        try:
            return resp.json()
        except Exception:
            return {'results': [], 'total': 0}

    def get_all_library_items(self, library_id: str) -> list[dict]:
        """Paginate through every item in a single library."""
        items: list[dict] = []
        page = 0
        limit = 50
        max_pages = 200  # safety cap

        for _ in range(max_pages):
            data = self.get_library_items(library_id, page=page, limit=limit)
            results = data.get('results', [])
            if not results:
                break

            for raw in results:
                items.append(
                    self._extract_item(raw, self._base_url, self._token)
                )

            total = data.get('total', 0)
            if len(items) >= total:
                break
            page += 1

        return items

    def get_all_items_all_libraries(self) -> list[dict]:
        """Return all items from all book libraries, each tagged with library info."""
        libraries = self.get_libraries()
        all_items: list[dict] = []
        for lib in libraries:
            lib_id = lib.get('id', '')
            lib_name = lib.get('name', '')
            items = self.get_all_library_items(lib_id)
            for item in items:
                item['library_id'] = lib_id
                item['library_name'] = lib_name
            all_items.extend(items)
        return all_items

    def search(self, query: str) -> list[dict]:
        """Use the ABS /api/search endpoint."""
        if not self._configured:
            return []
        resp = self._get('/api/search', params={'q': query})
        if resp is None:
            return []
        try:
            data = resp.json()
            return data.get('book', [])
        except Exception:
            return []

    def get_status(self) -> dict:
        """Return a summary dict used by the navbar status pill."""
        configured = self._configured
        reachable = False
        libraries: list[dict] = []
        if configured:
            reachable = self.ping()
            if reachable:
                libraries = self.get_libraries()
        return {
            'configured': configured,
            'reachable': reachable,
            'libraries': libraries,
        }
