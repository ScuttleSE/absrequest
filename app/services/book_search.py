import os
import re

import requests


# Audible base URLs by marketplace code
_AUDIBLE_MARKETPLACES = {
    'US': 'https://api.audible.com',
    'UK': 'https://api.audible.co.uk',
    'AU': 'https://api.audible.com.au',
    'CA': 'https://api.audible.ca',
    'DE': 'https://api.audible.de',
    'FR': 'https://api.audible.fr',
    'IT': 'https://api.audible.it',
    'ES': 'https://api.audible.es',
    'JP': 'https://api.audible.co.jp',
    'IN': 'https://api.audible.in',
}


class BookSearchService:
    """Fetches audiobook metadata from Audible (primary) and Open Library (fallback)."""

    TIMEOUT = 8  # seconds

    def search(self, query: str) -> list[dict]:
        """Search Audible first; fall back to Open Library if nothing is returned."""
        results = self._search_audible(query)
        if not results:
            results = self._search_open_library(query)
        return results

    # ── Audible ────────────────────────────────────────────────────────────────

    def _search_audible(self, query: str) -> list[dict]:
        """Search the Audible catalog API (no authentication required)."""
        marketplace = os.environ.get('AUDIBLE_MARKETPLACE', 'US').upper()
        base_url = _AUDIBLE_MARKETPLACES.get(marketplace, _AUDIBLE_MARKETPLACES['US'])

        try:
            resp = requests.get(
                f'{base_url}/1.0/catalog/products',
                params={
                    'keywords': query,
                    'num_results': 20,
                    'response_groups': 'contributors,product_desc,product_images,media',
                    'image_sizes': '500,300',
                },
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            products = resp.json().get('products', [])
        except Exception:
            return []

        results = []
        for p in products:
            title = p.get('title', '').strip()
            if not title:
                continue

            subtitle = p.get('subtitle', '').strip()
            if subtitle:
                title = f'{title}: {subtitle}'

            authors = ', '.join(
                a.get('name', '') for a in p.get('authors', []) if a.get('name')
            ) or None

            narrators = ', '.join(
                n.get('name', '') for n in p.get('narrators', []) if n.get('name')
            ) or None

            # Duration from runtime_length_min (minutes)
            duration = None
            mins = p.get('runtime_length_min')
            if mins:
                try:
                    h, m = divmod(int(mins), 60)
                    duration = f'{h}h {m}m' if h else f'{m}m'
                except (TypeError, ValueError):
                    pass

            # Cover — prefer 500px, fall back to 300px
            images = p.get('product_images') or {}
            cover_url = images.get('500') or images.get('300') or None

            # Description — strip any HTML tags Audible may include
            description = (
                p.get('merchandising_summary') or p.get('publisher_summary') or None
            )
            if description:
                description = re.sub(r'<[^>]+>', '', description).strip() or None

            results.append({
                'title': title,
                'author': authors,
                'narrator': narrators,
                'cover_url': cover_url,
                'isbn': None,
                'asin': p.get('asin') or None,
                'google_books_id': None,
                'duration': duration,
                'description': description,
                'source': 'audible',
            })

        return results

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
                # Cover image
                cover_i = doc.get('cover_i')
                cover_url = (
                    f'https://covers.openlibrary.org/b/id/{cover_i}-M.jpg'
                    if cover_i
                    else None
                )

                # Prefer ISBN-13 (13 digits); fall back to first available
                isbn: str | None = None
                isbn_list: list[str] = doc.get('isbn', [])
                for candidate in isbn_list:
                    if len(candidate) == 13:
                        isbn = candidate
                        break
                if not isbn and isbn_list:
                    isbn = isbn_list[0]

                # first_sentence can be a string, a dict, or a list
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
