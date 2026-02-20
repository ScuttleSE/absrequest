import os

import requests


class BookSearchService:
    """Fetches audiobook metadata from Google Books (primary) and Open Library (fallback)."""

    TIMEOUT = 8  # seconds

    def search(self, query: str) -> list[dict]:
        """Search both APIs; fall back to Open Library if Google returns nothing."""
        results = self._search_google_books(query)
        if not results:
            results = self._search_open_library(query)
        return results

    # ── Google Books ───────────────────────────────────────────────────────────

    def _search_google_books(self, query: str) -> list[dict]:
        try:
            params: dict = {
                'q': query,
                'maxResults': 20,
                'printType': 'books',
            }
            api_key = os.environ.get('GOOGLE_BOOKS_API_KEY', '')
            if api_key:
                params['key'] = api_key

            resp = requests.get(
                'https://www.googleapis.com/books/v1/volumes',
                params=params,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get('items', []):
                info = item.get('volumeInfo', {})

                # Prefer ISBN-13; fall back to ISBN-10
                isbn: str | None = None
                for identifier in info.get('industryIdentifiers', []):
                    if identifier.get('type') == 'ISBN_13':
                        isbn = identifier.get('identifier')
                        break
                if not isbn:
                    for identifier in info.get('industryIdentifiers', []):
                        if identifier.get('type') == 'ISBN_10':
                            isbn = identifier.get('identifier')
                            break

                # Cover URL — upgrade to HTTPS and request a larger image
                cover_url: str | None = None
                thumbnail = info.get('imageLinks', {}).get('thumbnail', '')
                if thumbnail:
                    cover_url = thumbnail.replace('http://', 'https://')
                    if '&fife=' not in cover_url:
                        cover_url += '&fife=w400'

                authors = info.get('authors', [])
                results.append({
                    'title': info.get('title', 'Unknown Title'),
                    'author': ', '.join(authors) if authors else None,
                    'narrator': None,  # Google Books API does not expose narrator info
                    'cover_url': cover_url,
                    'description': info.get('description'),
                    'isbn': isbn,
                    'asin': None,
                    'google_books_id': item.get('id'),
                    'duration': None,
                    'source': 'google_books',
                })
            return results

        except Exception:
            return []

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
