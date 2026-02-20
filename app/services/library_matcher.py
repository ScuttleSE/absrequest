import re

from rapidfuzz import fuzz


class LibraryMatcher:
    """Fuzzy matcher between audiobook request metadata and ABS library items."""

    def __init__(self, threshold: float = 0.85) -> None:
        # threshold is in 0.0–1.0 range (e.g. 0.85 = 85 % similarity required)
        self.threshold = threshold

    # ── Text normalisation ────────────────────────────────────────────────────

    def normalize(self, text: str) -> str:
        """Lowercase, strip punctuation, collapse whitespace."""
        if not text:
            return ''
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    # ── Scoring ───────────────────────────────────────────────────────────────

    def score(
        self,
        request_title: str,
        request_author: str,
        abs_title: str,
        abs_author: str,
    ) -> dict:
        """
        Compare a request against a single ABS item.

        Returns:
            title_score  – 0.0–1.0 (rapidfuzz ratio on normalised strings)
            author_score – 0.0–1.0 (0.0 if one side is unknown)
            is_match     – title AND author both meet the threshold
            is_possible  – title meets threshold, author does not
        """
        t_req = self.normalize(request_title)
        t_abs = self.normalize(abs_title)
        a_req = self.normalize(request_author)
        a_abs = self.normalize(abs_author)

        # token_set_ratio handles subtitle / series suffixes gracefully:
        # "The Hard Line: A Gray Man Novel" vs "The Hard Line" → 100 %
        # whereas plain ratio would give ~55 % for that pair.
        title_score: float = fuzz.token_set_ratio(t_req, t_abs) / 100.0

        # If one side has no author info, treat it as a non-match on author
        # (avoids false positives from empty-vs-empty = 100 %)
        if a_req and a_abs:
            author_score: float = fuzz.ratio(a_req, a_abs) / 100.0
        else:
            author_score = 0.0

        is_match = (
            title_score >= self.threshold and author_score >= self.threshold
        )
        is_possible = title_score >= self.threshold and not is_match

        return {
            'title_score': title_score,
            'author_score': author_score,
            'is_match': is_match,
            'is_possible': is_possible,
        }

    # ── Batch operations ──────────────────────────────────────────────────────

    def find_matches(
        self,
        title: str,
        author: str,
        library_items: list[dict],
    ) -> list[dict]:
        """
        Return all library items that are a match or possible match,
        sorted by title_score descending.
        """
        matches: list[dict] = []
        for item in library_items:
            s = self.score(
                title,
                author,
                item.get('title', ''),
                item.get('author', ''),
            )
            if s['is_match'] or s['is_possible']:
                merged = dict(item)
                merged.update(s)
                matches.append(merged)

        return sorted(matches, key=lambda x: x['title_score'], reverse=True)

    def check_single(
        self,
        title: str,
        author: str,
        library_items: list[dict],
    ) -> dict:
        """
        Return the best match (if any) for a single request.

        Returns:
            found      – bool
            is_certain – True if the best match is a full match (not just possible)
            match      – the matched item dict, or None
        """
        matches = self.find_matches(title, author, library_items)
        if not matches:
            return {'found': False, 'is_certain': False, 'match': None}

        best = matches[0]
        return {
            'found': True,
            'is_certain': bool(best.get('is_match')),
            'match': best,
        }
