import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

# Maps region code → Audible TLD (mirrors ABS's Audible.js regionMap)
_REGION_TLD = {
    'us': '.com',
    'ca': '.ca',
    'uk': '.co.uk',
    'au': '.com.au',
    'fr': '.fr',
    'de': '.de',
    'jp': '.co.jp',
    'it': '.it',
    'in': '.in',
    'es': '.es',
}


class BookSearchService:
    """Fetches audiobook metadata from Audible (primary) and Open Library (fallback).

    Audible search mirrors the approach used by Audiobookshelf:
      1. Query api.audible.<tld> to get a ranked list of ASINs.
      2. Fetch full metadata for each ASIN from api.audnex.us (community API).
    """

    TIMEOUT = 10  # seconds

    def search(self, query: str, page: int = 1) -> list[dict]:
        """Search enabled providers in order: Audible → Open Library."""
        from app.models import AppSettings
        settings = AppSettings.get()

        if settings.audible_enabled:
            results = self._search_audible_regions(query, settings.audible_regions, page=page)
            if results:
                return results

        if settings.open_library_enabled:
            return self._search_open_library(query)

        return []

    def _search_audible_regions(self, query: str, regions: list[str], page: int = 1) -> list[dict]:
        """Search multiple Audible regions in parallel and merge, deduplicating by ASIN."""
        if not regions:
            regions = ['us']

        if len(regions) == 1:
            return self._search_audible(query, region=regions[0], page=page)

        seen_asins: set[str] = set()
        merged: list[dict] = []

        with ThreadPoolExecutor(max_workers=len(regions)) as executor:
            futures = {
                executor.submit(self._search_audible, query, region, page): region
                for region in regions
            }
            for future in as_completed(futures):
                for result in (future.result() or []):
                    asin = result.get('asin')
                    if asin:
                        if asin not in seen_asins:
                            seen_asins.add(asin)
                            merged.append(result)
                    else:
                        merged.append(result)

        return merged

    # ── Audible ────────────────────────────────────────────────────────────────

    def _search_audible(self, query: str, region: str = 'us', page: int = 1) -> list[dict]:
        region = (region or 'us').lower()
        tld = _REGION_TLD.get(region, '.com')

        # Step 1: catalog search → list of ASINs
        # Use `keywords` (general search) rather than `title` so that author
        # names, series names, and mixed queries all return relevant results.
        try:
            resp = requests.get(
                f'https://api.audible{tld}/1.0/catalog/products',
                params={
                    'keywords': query,
                    'num_results': 25,
                    'page': page,
                    'products_sort_by': 'Relevance',
                },
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            products = resp.json().get('products', [])
        except Exception as exc:
            logger.warning('Audible catalog search failed: %s', exc)
            return []

        asins = [p['asin'] for p in products if p.get('asin')]
        if not asins:
            return []

        # Step 2: fetch full metadata from audnex.us for each ASIN in parallel
        asin_order = {asin: i for i, asin in enumerate(asins)}
        raw_results: list[dict] = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self._fetch_audnex, asin, region): asin
                for asin in asins
            }
            for future in as_completed(futures):
                data = future.result()
                if data:
                    raw_results.append(self._parse_audnex(data))

        # Restore original relevance order from the catalog search
        raw_results.sort(key=lambda r: asin_order.get(r.get('asin', ''), 999))
        return raw_results

    def _fetch_audnex(self, asin: str, region: str) -> dict | None:
        """Fetch a single book's metadata from audnex.us."""
        try:
            params = {}
            if region and region != 'us':
                params['region'] = region
            resp = requests.get(
                f'https://api.audnex.us/books/{asin}',
                params=params,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if data.get('asin') else None
        except Exception as exc:
            logger.debug('audnex fetch failed for %s: %s', asin, exc)
            return None

    def _parse_audnex(self, p: dict) -> dict:
        """Map an audnex.us response dict to our internal result format."""
        title = (p.get('title') or '').strip()
        subtitle = (p.get('subtitle') or '').strip()
        if subtitle:
            title = f'{title}: {subtitle}'

        authors = ', '.join(
            a.get('name', '') for a in (p.get('authors') or []) if a.get('name')
        ) or None

        narrators = ', '.join(
            n.get('name', '') for n in (p.get('narrators') or []) if n.get('name')
        ) or None

        duration = None
        mins = p.get('runtimeLengthMin')
        if mins:
            try:
                h, m = divmod(int(mins), 60)
                duration = f'{h}h {m}m' if h else f'{m}m'
            except (TypeError, ValueError):
                pass

        description = p.get('summary') or None
        if description:
            description = re.sub(r'<[^>]+>', '', description).strip() or None

        return {
            'title': title,
            'author': authors,
            'narrator': narrators,
            'cover_url': p.get('image') or None,
            'isbn': p.get('isbn') or None,
            'asin': p.get('asin') or None,
            'google_books_id': None,
            'duration': duration,
            'description': description,
            'source': 'audible',
        }

    # ── Open Library ───────────────────────────────────────────────────────────

    def _search_open_library(self, query: str) -> list[dict]:
        try:
            resp = requests.get(
                'https://openlibrary.org/search.json',
                params={
                    'q': query,
                    'fields': 'key,title,author_name,cover_i,isbn,first_sentence',
                    'limit': 20,
                },
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for doc in data.get('docs', []):
                cover_i = doc.get('cover_i')
                cover_url = (
                    f'https://covers.openlibrary.org/b/id/{cover_i}-M.jpg'
                    if cover_i
                    else None
                )

                isbn: str | None = None
                isbn_list: list[str] = doc.get('isbn', [])
                for candidate in isbn_list:
                    if len(candidate) == 13:
                        isbn = candidate
                        break
                if not isbn and isbn_list:
                    isbn = isbn_list[0]

                description: str | None = None
                first_sentence = doc.get('first_sentence')
                if isinstance(first_sentence, str):
                    description = first_sentence
                elif isinstance(first_sentence, dict):
                    description = first_sentence.get('value')
                elif isinstance(first_sentence, list) and first_sentence:
                    item = first_sentence[0]
                    if isinstance(item, str):
                        description = item
                    elif isinstance(item, dict):
                        description = item.get('value')

                authors = doc.get('author_name', [])
                results.append({
                    'title': doc.get('title', 'Unknown Title'),
                    'author': ', '.join(authors) if authors else None,
                    'narrator': None,
                    'cover_url': cover_url,
                    'description': description,
                    'isbn': isbn,
                    'asin': None,
                    'google_books_id': None,
                    'duration': None,
                    'source': 'open_library',
                })
            return results

        except Exception:
            return []
