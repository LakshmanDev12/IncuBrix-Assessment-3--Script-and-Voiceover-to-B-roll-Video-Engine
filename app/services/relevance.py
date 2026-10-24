from abc import ABC, abstractmethod
import collections
import importlib.util
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas import (
    CandidateMediaItem,
    RankedCandidateItem,
    RankedScoreBreakdown,
)

# Standard English stopwords for lexical filtering
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't",
    "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
    "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once",
    "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll",
    "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's",
    "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't",
    "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"
}


def tokenize(text: str) -> List[str]:
    """Extracts lowercase alphanumeric tokens, stripping punctuation."""
    return re.findall(r'\b[a-zA-Z0-9_-]+\b', text.lower())


def extract_content_tokens(text: str) -> List[str]:
    """Extracts non-stopword tokens."""
    return [t for t in tokenize(text) if t not in STOP_WORDS and len(t) > 1]


def extract_ngrams(tokens: List[str], n: int) -> Set[Tuple[str, ...]]:
    """Extracts n-grams as tuples of tokens."""
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


class BaseRelevanceRanker(ABC):
    """Abstract interface for matching visual descriptions to candidate visual media."""

    @abstractmethod
    def rank(
        self,
        query_description: str,
        candidates: List[CandidateMediaItem],
        target_duration: Optional[float] = None,
        target_aspect_ratio: Optional[str] = "16:9"
    ) -> List[RankedCandidateItem]:
        pass

    @property
    @abstractmethod
    def ranker_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_info(self) -> str:
        pass


class DeterministicRelevanceRanker(BaseRelevanceRanker):
    """
    Deterministic multi-feature relevance ranking engine.
    
    Avoids keyword-only matching by combining:
    1. TF-IDF weighted sublinear lexical cosine similarity.
    2. Contiguous phrase match via bigram and trigram Dice similarity.
    3. Thematic tag overlap.
    4. Temporal / duration fit penalty.
    5. Aspect ratio compatibility factor.
    6. Antonym / negative concept penalty.
    
    Produces full auditable reason chains and score breakdowns.
    """

    @property
    def ranker_name(self) -> str:
        return "deterministic_baseline"

    @property
    def model_info(self) -> str:
        return "Deterministic Multi-Feature Ranker (TF-IDF + Phrase N-grams + Tag Overlap + Temporal Fit). No neural model loaded."

    def rank(
        self,
        query_description: str,
        candidates: List[CandidateMediaItem],
        target_duration: Optional[float] = None,
        target_aspect_ratio: Optional[str] = "16:9"
    ) -> List[RankedCandidateItem]:
        if not candidates:
            return []

        q_tokens = extract_content_tokens(query_description)
        q_raw_tokens = tokenize(query_description)
        q_bigrams = extract_ngrams(q_raw_tokens, 2).union(extract_ngrams(q_tokens, 2))
        q_trigrams = extract_ngrams(q_raw_tokens, 3).union(extract_ngrams(q_tokens, 3))

        # Build corpus vocabulary & document frequencies for TF-IDF
        corpus: List[List[str]] = [q_tokens]
        for c in candidates:
            c_text = f"{c.title} {c.description} {' '.join(c.tags)}"
            corpus.append(extract_content_tokens(c_text))

        doc_count = len(corpus)
        df: Dict[str, int] = collections.defaultdict(int)
        for doc in corpus:
            unique_terms = set(doc)
            for t in unique_terms:
                df[t] += 1

        # Precompute IDF
        idf: Dict[str, float] = {
            t: math.log(1.0 + (doc_count / (count + 1))) + 1.0
            for t, count in df.items()
        }

        # Query TF-IDF vector
        q_vec = self._compute_tfidf_vector(q_tokens, idf)

        results: List[RankedCandidateItem] = []

        for candidate in candidates:
            c_raw_tokens = tokenize(f"{candidate.title} {candidate.description}")
            c_content_tokens = extract_content_tokens(f"{candidate.title} {candidate.description}")
            c_tags = [t.lower() for t in candidate.tags]

            reasons: List[str] = []

            # 1. Lexical / TF-IDF Cosine Similarity
            c_vec = self._compute_tfidf_vector(c_content_tokens, idf)
            text_sim = self._cosine_similarity(q_vec, c_vec)

            # 2. Phrase N-gram Overlap (Bigrams & Trigrams across raw & content tokens)
            c_bigrams = extract_ngrams(c_raw_tokens, 2).union(extract_ngrams(c_content_tokens, 2))
            c_trigrams = extract_ngrams(c_raw_tokens, 3).union(extract_ngrams(c_content_tokens, 3))
            phrase_sim, matched_phrases = self._compute_phrase_similarity(
                q_bigrams, q_trigrams, c_bigrams, c_trigrams
            )

            # 3. Tag Overlap
            tag_sim, matched_tags = self._compute_tag_similarity(q_tokens, c_tags)

            # 4. Temporal / Duration Fit
            duration_fit, duration_reason = self._compute_duration_fit(
                candidate.duration_seconds, target_duration
            )

            # 5. Aspect Ratio Fit
            aspect_fit, aspect_reason = self._compute_aspect_ratio_fit(
                candidate.aspect_ratio, target_aspect_ratio
            )

            # 6. Negative Conflict Penalty
            penalty, penalty_reasons = self._compute_negative_penalties(
                query_description, candidate
            )

            # Content score combination
            # 30% phrase match, 40% TF-IDF token similarity, 30% tag overlap
            content_score = (0.30 * phrase_sim) + (0.40 * text_sim) + (0.30 * tag_sim)

            if content_score <= 0.001:
                # Disjoint content: no semantic relevance
                final_score = 0.0
                reasons.append("No semantic, phrase, or tag overlap found with query description.")
            else:
                # Apply structural modifiers (duration fit & aspect ratio compatibility)
                final_score = content_score * duration_fit * aspect_fit
                final_score = max(0.0, min(1.0, final_score - penalty))

                # Document auditable reasons
                if matched_phrases:
                    reasons.append(f"Phrase overlap: {phrase_sim:.2f} (matched phrases: {', '.join(matched_phrases[:3])})")
                if text_sim > 0:
                    reasons.append(f"Lexical similarity: {text_sim:.2f}")
                if matched_tags:
                    reasons.append(f"Tag alignment: {tag_sim:.2f} (matched: {', '.join(matched_tags)})")
                reasons.append(duration_reason)
                reasons.append(aspect_reason)
                if penalty > 0:
                    reasons.extend(penalty_reasons)
                reasons.append(f"Final composite score: {final_score:.3f}")

            breakdown = RankedScoreBreakdown(
                text_similarity=round(text_sim, 4),
                phrase_match=round(phrase_sim, 4),
                tag_overlap=round(tag_sim, 4),
                duration_fit=round(duration_fit, 4),
                aspect_ratio_fit=round(aspect_fit, 4),
                penalties=round(penalty, 4)
            )

            results.append(RankedCandidateItem(
                candidate=candidate,
                score=round(final_score, 4),
                reasons=reasons,
                breakdown=breakdown
            ))

        # Sort descending by score; tie-break deterministically on duration_fit, then title
        results.sort(
            key=lambda r: (r.score, r.breakdown.duration_fit, r.candidate.id),
            reverse=True
        )

        return results

    def _compute_tfidf_vector(self, tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
        tf = collections.Counter(tokens)
        vec: Dict[str, float] = {}
        for term, count in tf.items():
            if term in idf:
                # Sublinear term frequency scaling: 1 + log(count)
                vec[term] = (1.0 + math.log(count)) * idf[term]
        return vec

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        dot = sum(vec1[k] * vec2[k] for k in vec1 if k in vec2)
        norm1 = math.sqrt(sum(v * v for v in vec1.values()))
        norm2 = math.sqrt(sum(v * v for v in vec2.values()))
        if norm1 <= 0.0 or norm2 <= 0.0:
            return 0.0
        return min(1.0, max(0.0, dot / (norm1 * norm2)))

    def _compute_phrase_similarity(
        self,
        q_bigrams: Set[Tuple[str, ...]],
        q_trigrams: Set[Tuple[str, ...]],
        c_bigrams: Set[Tuple[str, ...]],
        c_trigrams: Set[Tuple[str, ...]]
    ) -> Tuple[float, List[str]]:
        matched: List[str] = []
        bi_matches = q_bigrams.intersection(c_bigrams)
        tri_matches = q_trigrams.intersection(c_trigrams)

        for b in bi_matches:
            matched.append(" ".join(b))
        for t in tri_matches:
            matched.append(" ".join(t))

        total_q_phrases = len(q_bigrams) + (len(q_trigrams) * 1.5)
        if total_q_phrases == 0:
            return 0.0, []

        match_weight = len(bi_matches) + (len(tri_matches) * 1.5)
        score = min(1.0, match_weight / total_q_phrases)
        return score, matched

    def _compute_tag_similarity(self, q_tokens: List[str], c_tags: List[str]) -> Tuple[float, List[str]]:
        if not q_tokens or not c_tags:
            return 0.0, []

        q_set = set(q_tokens)
        matched_tags: List[str] = []

        for tag in c_tags:
            tag_tokens = set(tokenize(tag))
            if tag_tokens and tag_tokens.issubset(q_set):
                matched_tags.append(tag)
            elif tag in q_set:
                matched_tags.append(tag)

        if not matched_tags:
            return 0.0, []

        # Coverage score
        score = min(1.0, len(matched_tags) / max(len(c_tags), 1))
        return score, matched_tags

    def _compute_duration_fit(
        self,
        candidate_duration: float,
        target_duration: Optional[float]
    ) -> Tuple[float, str]:
        if target_duration is None or target_duration <= 0.0:
            return 1.0, "Duration fit: 1.00 (no target duration specified)"

        if candidate_duration >= target_duration:
            return 1.0, f"Duration fit: 1.00 (candidate {candidate_duration:.1f}s >= target {target_duration:.1f}s)"

        # Candidate is shorter than scene duration
        ratio = max(0.1, candidate_duration / target_duration)
        return ratio, f"Duration fit: {ratio:.2f} (candidate {candidate_duration:.1f}s < target {target_duration:.1f}s; needs loop/hold)"

    def _compute_aspect_ratio_fit(
        self,
        candidate_ratio: str,
        target_ratio: Optional[str]
    ) -> Tuple[float, str]:
        if not target_ratio or candidate_ratio == target_ratio:
            return 1.0, f"Aspect ratio fit: 1.00 (matching {candidate_ratio})"
        
        # Mismatched aspect ratio: can be cropped or letterboxed with slight penalty
        return 0.85, f"Aspect ratio fit: 0.85 (candidate {candidate_ratio} requires reframing to {target_ratio})"

    def _compute_negative_penalties(
        self,
        query: str,
        candidate: CandidateMediaItem
    ) -> Tuple[float, List[str]]:
        """Identifies conflicting visual contexts (e.g. night vs day, indoor vs outdoor)."""
        penalty = 0.0
        reasons = []

        q_lower = query.lower()
        c_text = f"{candidate.title} {candidate.description} {' '.join(candidate.tags)}".lower()

        conflict_pairs = [
            ({"night", "dark", "evening", "sunset", "midnight"}, {"day", "daytime", "sunny", "morning", "sunrise"}),
            ({"indoor", "inside", "office", "room"}, {"outdoor", "outside", "nature", "forest", "mountain"}),
            ({"winter", "snow", "ice", "freezing"}, {"summer", "beach", "tropical", "hot"}),
        ]

        for set_a, set_b in conflict_pairs:
            q_has_a = any(w in q_lower for w in set_a)
            q_has_b = any(w in q_lower for w in set_b)
            c_has_a = any(w in c_text for w in set_a)
            c_has_b = any(w in c_text for w in set_b)

            if q_has_a and c_has_b and not q_has_b:
                penalty += 0.20
                reasons.append("Contextual mismatch penalty: query specifies conflicting environmental condition.")
            elif q_has_b and c_has_a and not q_has_a:
                penalty += 0.20
                reasons.append("Contextual mismatch penalty: candidate environment conflicts with query condition.")

        return min(0.5, penalty), reasons


class EmbeddingRelevanceRanker(BaseRelevanceRanker):
    """
    Pluggable neural embedding adapter.
    
    If embedding model libraries (such as sentence-transformers) or remote credentials
    are not detected, this adapter explicitly falls back to DeterministicRelevanceRanker
    and transparently reports its fallback status.
    """

    def __init__(self, fallback_ranker: Optional[BaseRelevanceRanker] = None):
        self._fallback = fallback_ranker or DeterministicRelevanceRanker()
        self._is_neural_available = self._check_neural_availability()

    def _check_neural_availability(self) -> bool:
        # Check if sentence_transformers is installed
        spec = importlib.util.find_spec("sentence_transformers")
        return spec is not None

    @property
    def ranker_name(self) -> str:
        if self._is_neural_available:
            return "embedding_neural_adapter"
        return "embedding_adapter_fallback_deterministic"

    @property
    def model_info(self) -> str:
        if self._is_neural_available:
            return "Neural Vector Embedding Model (sentence-transformers: all-MiniLM-L6-v2)"
        return "Deterministic Fallback Active: sentence-transformers is not installed in the environment."

    def rank(
        self,
        query_description: str,
        candidates: List[CandidateMediaItem],
        target_duration: Optional[float] = None,
        target_aspect_ratio: Optional[str] = "16:9"
    ) -> List[RankedCandidateItem]:
        if not self._is_neural_available:
            # Explicit, transparent fallback to deterministic ranker
            return self._fallback.rank(
                query_description=query_description,
                candidates=candidates,
                target_duration=target_duration,
                target_aspect_ratio=target_aspect_ratio
            )

        # If neural model is available in the environment:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            model = SentenceTransformer("all-MiniLM-L6-v2")
            q_emb = model.encode(query_description)
            results = []

            for candidate in candidates:
                c_text = f"{candidate.title}. {candidate.description}. {' '.join(candidate.tags)}"
                c_emb = model.encode(c_text)

                # Cosine similarity
                dot = float(q_emb @ c_emb)
                norm_q = float(math.sqrt(q_emb @ q_emb))
                norm_c = float(math.sqrt(c_emb @ c_emb))
                sim = max(0.0, min(1.0, dot / (norm_q * norm_c)))

                # Incorporate duration and aspect fit
                dur_fit, dur_reason = self._fallback._compute_duration_fit(candidate.duration_seconds, target_duration)  # type: ignore
                asp_fit, asp_reason = self._fallback._compute_aspect_ratio_fit(candidate.aspect_ratio, target_aspect_ratio)  # type: ignore

                final_score = round(sim * dur_fit * asp_fit, 4)
                breakdown = RankedScoreBreakdown(
                    text_similarity=round(sim, 4),
                    phrase_match=round(sim, 4),
                    tag_overlap=1.0 if any(t.lower() in query_description.lower() for t in candidate.tags) else 0.0,
                    duration_fit=round(dur_fit, 4),
                    aspect_ratio_fit=round(asp_fit, 4),
                    penalties=0.0
                )
                reasons = [
                    f"Dense neural embedding similarity: {sim:.3f}",
                    dur_reason,
                    asp_reason,
                    f"Final composite score: {final_score:.3f}"
                ]
                results.append(RankedCandidateItem(
                    candidate=candidate,
                    score=final_score,
                    reasons=reasons,
                    breakdown=breakdown
                ))

            results.sort(key=lambda r: r.score, reverse=True)
            return results

        except Exception:
            # Fallback on any runtime error
            return self._fallback.rank(
                query_description=query_description,
                candidates=candidates,
                target_duration=target_duration,
                target_aspect_ratio=target_aspect_ratio
            )


def get_relevance_ranker(ranker_type: str = "deterministic") -> BaseRelevanceRanker:
    """Factory method for pluggable relevance rankers."""
    if ranker_type == "embedding":
        return EmbeddingRelevanceRanker()
    return DeterministicRelevanceRanker()


deterministic_ranker = DeterministicRelevanceRanker()
