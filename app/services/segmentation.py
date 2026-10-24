from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import settings
from app.schemas import Scene


class SegmentationError(ValueError):
    """Raised when scene segmentation or duration allocation fails."""
    def __init__(self, message: str, code: str = "SEGMENTATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class SegmentationConfig:
    min_duration_seconds: float = 0.5
    max_duration_seconds: float = 60.0
    words_per_minute: int = 150
    min_words_per_scene: int = 2
    target_words_per_scene: int = 18
    max_words_per_scene: int = 45


# Common abbreviations and titles to avoid incorrect sentence splitting
COMMON_ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "vs.", "etc.",
    "e.g.", "i.e.", "u.s.", "u.k.", "approx.", "dept.", "est."
}


class SceneSegmenter:
    """
    Splits continuous script narration into coherent, semantically bounded scenes,
    preserves original text verbatim, and calculates frame-accurate, strictly positive
    durations according to audio constraints or speech cadence.
    """

    def __init__(self, config: Optional[SegmentationConfig] = None):
        self.config = config or SegmentationConfig()

    def segment_input(
        self,
        script: Optional[str] = None,
        scenes: Optional[List[Any]] = None,
        aligned_segments: Optional[List[Any]] = None,
        total_duration: Optional[float] = None,
        config: Optional[SegmentationConfig] = None
    ) -> List[Scene]:
        """
        Unified segmentation entry point. Dispatches to script splitting, scene list validation,
        or aligned segment aggregation based on provided inputs.
        """
        cfg = config or self.config
        if aligned_segments and len(aligned_segments) > 0:
            return self.segment_aligned_segments(aligned_segments, total_duration, cfg)
        elif scenes and len(scenes) > 0:
            return self.segment_scene_list(scenes, total_duration, cfg)
        elif script and script.strip():
            return self.segment_script(script, total_duration, cfg)
        else:
            raise SegmentationError(
                "No valid script, scene list, or aligned segments provided.",
                code="NO_INPUT"
            )

    def segment_scene_list(
        self,
        scenes: List[Any],
        total_duration: Optional[float] = None,
        config: Optional[SegmentationConfig] = None
    ) -> List[Scene]:
        """
        Validates, normalizes, and sanitizes an existing scene list.
        Strictly prevents negative or zero-length scenes, guarantees duration bounds,
        and ensures non-empty visual descriptions.
        """
        cfg = config or self.config
        if not scenes:
            raise SegmentationError("Scene list cannot be empty.", code="EMPTY_SCENE_LIST")

        normalized: List[Scene] = []
        for i, s in enumerate(scenes):
            if isinstance(s, dict):
                narration = str(s.get("narration", "")).strip()
                duration = s.get("duration_seconds")
                v_desc = str(s.get("visual_description", "")).strip()
                s_url = s.get("source_url")
                lic = s.get("license_name", "UNVERIFIED — replace with verified licence")
                attr = s.get("attribution", "UNVERIFIED — attribution required")
            elif hasattr(s, "narration"):
                narration = s.narration.strip()
                duration = s.duration_seconds
                v_desc = s.visual_description.strip() if s.visual_description else ""
                s_url = getattr(s, "source_url", None)
                lic = getattr(s, "license_name", "UNVERIFIED — replace with verified licence")
                attr = getattr(s, "attribution", "UNVERIFIED — attribution required")
            else:
                raise SegmentationError(f"Invalid scene item at index {i}: {type(s)}", code="INVALID_SCENE_TYPE")

            if not narration:
                raise SegmentationError(f"Scene at index {i} has empty narration text.", code="EMPTY_NARRATION")

            if duration is None or duration <= 0.0:
                raise SegmentationError(
                    f"Scene at index {i} has invalid duration ({duration}s). Scene durations must be strictly positive (> 0.0s).",
                    code="INVALID_SCENE_DURATION"
                )

            # Enforce configuration bounds
            duration = max(cfg.min_duration_seconds, min(cfg.max_duration_seconds, float(duration)))

            if not v_desc or len(v_desc) < settings.MIN_VISUAL_DESCRIPTION_LENGTH:
                v_desc = self._generate_visual_description(narration, scene_index=i + 1)

            normalized.append(Scene(
                narration=narration,
                duration_seconds=round(duration, 3),
                visual_description=v_desc,
                source_url=s_url,
                license_name=lic,
                attribution=attr
            ))

        # Rebalance if total_duration provided
        if total_duration is not None:
            total_current = sum(sc.duration_seconds for sc in normalized)
            scale = total_duration / total_current
            running = 0.0
            rebalanced = []
            for j, sc in enumerate(normalized):
                if j == len(normalized) - 1:
                    new_dur = round(total_duration - running, 3)
                else:
                    new_dur = round(sc.duration_seconds * scale, 3)
                    running += new_dur
                new_dur = max(cfg.min_duration_seconds, min(cfg.max_duration_seconds, new_dur))
                rebalanced.append(Scene(
                    narration=sc.narration,
                    duration_seconds=new_dur,
                    visual_description=sc.visual_description,
                    source_url=sc.source_url,
                    license_name=sc.license_name,
                    attribution=sc.attribution
                ))
            return rebalanced

        return normalized

    def segment_aligned_segments(
        self,
        aligned_segments: List[Any],
        total_duration: Optional[float] = None,
        config: Optional[SegmentationConfig] = None
    ) -> List[Scene]:
        """
        Coalesces word/phrase-level aligned narration segments into coherent scenes
        using punctuation boundaries, length constraints, and speech pauses.
        Strictly prevents negative or zero-length scenes.
        """
        cfg = config or self.config
        if not aligned_segments:
            raise SegmentationError("Aligned segments list cannot be empty.", code="EMPTY_ALIGNED_SEGMENTS")

        parsed_segs = []
        for i, seg in enumerate(aligned_segments):
            if isinstance(seg, dict):
                text = str(seg.get("text", "")).strip()
                start = float(seg.get("start_seconds", 0.0))
                end = float(seg.get("end_seconds", 0.0))
            else:
                text = seg.text.strip()
                start = float(seg.start_seconds)
                end = float(seg.end_seconds)

            if not text:
                continue

            if end <= start:
                raise SegmentationError(
                    f"Aligned segment at index {i} has invalid timing: end ({end}s) <= start ({start}s).",
                    code="INVALID_SEGMENT_TIMING"
                )

            parsed_segs.append({"text": text, "start": start, "end": end})

        if not parsed_segs:
            raise SegmentationError("No valid text found in aligned segments.", code="EMPTY_ALIGNED_SEGMENTS")

        # Group segments into scenes
        scenes: List[Scene] = []
        cur_texts: List[str] = []
        scene_start = parsed_segs[0]["start"]

        for i, s in enumerate(parsed_segs):
            cur_texts.append(s["text"])
            cur_duration = s["end"] - scene_start
            word_count = sum(len(t.split()) for t in cur_texts)
            ends_with_sentence_punct = bool(re.search(r'[.!?]$', s["text"]))

            pause_to_next = 0.0
            if i + 1 < len(parsed_segs):
                pause_to_next = parsed_segs[i + 1]["start"] - s["end"]

            should_cut = False
            if ends_with_sentence_punct and cur_duration >= cfg.min_duration_seconds:
                should_cut = True
            elif pause_to_next >= 0.8 and cur_duration >= cfg.min_duration_seconds:
                should_cut = True
            elif word_count >= cfg.target_words_per_scene and cur_duration >= cfg.min_duration_seconds:
                should_cut = True
            elif cur_duration >= cfg.max_duration_seconds:
                should_cut = True

            if should_cut or i == len(parsed_segs) - 1:
                scene_narration = " ".join(cur_texts)
                scene_dur = round(max(cfg.min_duration_seconds, s["end"] - scene_start), 3)
                visual_desc = self._generate_visual_description(scene_narration, scene_index=len(scenes) + 1)
                scenes.append(Scene(
                    narration=scene_narration,
                    duration_seconds=scene_dur,
                    visual_description=visual_desc
                ))
                cur_texts = []
                if i + 1 < len(parsed_segs):
                    scene_start = parsed_segs[i + 1]["start"]

        return scenes

    def segment_script(
        self,
        script: str,
        total_duration: Optional[float] = None,
        config: Optional[SegmentationConfig] = None
    ) -> List[Scene]:
        """
        Segments raw script text into Scene objects with allocated durations
        and visual descriptions.
        """
        cfg = config or self.config
        cleaned_text = script.strip() if script else ""
        if not cleaned_text:
            raise SegmentationError("Script text cannot be empty or solely whitespace.", code="EMPTY_SCRIPT")

        # Step 1: Split into candidate sentence/clause chunks
        chunks = self._split_into_sentence_chunks(cleaned_text, cfg)
        if not chunks:
            raise SegmentationError("Unable to segment script into valid scenes.", code="SEGMENTATION_FAILED")

        # Step 2: Merge very small fragments to avoid undersized scenes
        merged_chunks = self._merge_short_chunks(chunks, cfg)

        # Step 3: Compute durations for each chunk
        durations = self._allocate_durations(merged_chunks, total_duration, cfg)

        # Step 4: Construct Scene objects with visual descriptions
        scenes: List[Scene] = []
        for i, (chunk, duration) in enumerate(zip(merged_chunks, durations)):
            visual_desc = self._generate_visual_description(chunk, scene_index=i + 1)
            scenes.append(Scene(
                narration=chunk,
                duration_seconds=duration,
                visual_description=visual_desc
            ))

        return scenes

    def _split_into_sentence_chunks(self, text: str, cfg: SegmentationConfig) -> List[str]:
        """
        Splits text on sentence boundaries and punctuation while protecting abbreviations.
        Long sentences exceeding max_words_per_scene are further divided at clause boundaries.
        """
        # Protect common abbreviations by temporarily replacing period with placeholder while preserving case
        protected_text = text
        for abbr in COMMON_ABBREVIATIONS:
            pattern = re.compile(r'\b' + re.escape(abbr), re.IGNORECASE)
            protected_text = pattern.sub(lambda m: m.group(0).replace(".", "§DOT§"), protected_text)

        # Protect decimal numbers (e.g. 3.14 -> 3§DOT§14)
        protected_text = re.sub(r'(\d)\.(\d)', r'\1§DOT§\2', protected_text)

        # Split on sentence ending punctuation [.!?] followed by whitespace or line breaks
        raw_sentences = re.split(r'(?<=[.!?])\s+', protected_text)

        chunks: List[str] = []
        for s in raw_sentences:
            s_clean = s.strip()
            if not s_clean:
                continue

            # Restore periods in protected text
            restored = s_clean.replace("§DOT§", ".")
            words = restored.split()

            # If a single sentence is excessively long, split on secondary punctuation (semicolon, comma, dash)
            if len(words) > cfg.max_words_per_scene:
                sub_chunks = self._split_long_sentence(restored, cfg)
                chunks.extend(sub_chunks)
            else:
                chunks.append(restored)

        return chunks

    def _split_long_sentence(self, sentence: str, cfg: SegmentationConfig) -> List[str]:
        """
        Subdivides an overly long sentence at semicolons, dashes, or commas to keep
        scenes within acceptable pacing boundaries, without dropping words.
        """
        # First try splitting by semicolons or colons
        if re.search(r'[;:—–]\s+', sentence):
            parts = re.split(r'(?<=[;:—–])\s+', sentence)
            refined = []
            for p in parts:
                p_clean = p.strip()
                if p_clean:
                    if len(p_clean.split()) > cfg.max_words_per_scene:
                        refined.extend(self._split_by_commas(p_clean, cfg))
                    else:
                        refined.append(p_clean)
            return refined

        return self._split_by_commas(sentence, cfg)

    def _split_by_commas(self, text: str, cfg: SegmentationConfig) -> List[str]:
        """Splits long text by commas while preserving the comma and all words."""
        parts = re.split(r'(?<=,)\s+', text)
        if len(parts) <= 1:
            # No commas to split on; split directly by word window to enforce boundaries
            return self._split_by_word_window(text, cfg.max_words_per_scene)

        chunks: List[str] = []
        current_acc: List[str] = []
        current_word_count = 0

        for part in parts:
            part_words = len(part.split())
            if current_word_count + part_words > cfg.max_words_per_scene and current_acc:
                chunks.append(" ".join(current_acc))
                current_acc = [part]
                current_word_count = part_words
            else:
                current_acc.append(part)
                current_word_count += part_words

        if current_acc:
            chunks.append(" ".join(current_acc))

        return chunks

    def _split_by_word_window(self, text: str, max_words: int) -> List[str]:
        """Splits unpunctuated text into slices of max_words."""
        words = text.split()
        chunks: List[str] = []
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i:i + max_words]))
        return chunks

    def _merge_short_chunks(self, chunks: List[str], cfg: SegmentationConfig) -> List[str]:
        """
        Merges short fragments (< min_words_per_scene) into neighboring chunks
        to prevent micro-scenes shorter than min_duration_seconds.
        """
        if len(chunks) <= 1:
            return chunks

        merged: List[str] = []
        accumulator = ""

        for chunk in chunks:
            words = chunk.split()
            if not accumulator:
                accumulator = chunk
            elif len(accumulator.split()) < cfg.min_words_per_scene:
                accumulator = f"{accumulator} {chunk}"
            elif len(words) < cfg.min_words_per_scene and len(accumulator.split()) + len(words) <= cfg.max_words_per_scene:
                accumulator = f"{accumulator} {chunk}"
            else:
                merged.append(accumulator)
                accumulator = chunk

        if accumulator:
            # If final piece is too short and there's a previous scene, merge with it if possible
            if merged and len(accumulator.split()) < cfg.min_words_per_scene:
                merged[-1] = f"{merged[-1]} {accumulator}"
            else:
                merged.append(accumulator)

        return merged

    def _allocate_durations(
        self,
        chunks: List[str],
        total_duration: Optional[float],
        cfg: SegmentationConfig
    ) -> List[float]:
        """
        Calculates durations for each scene. Guarantees:
        - No zero or negative durations (strictly >= min_duration_seconds).
        - No scene exceeds max_duration_seconds.
        - If total_duration is given, sum matches total_duration.
        """
        n_chunks = len(chunks)
        word_counts = [max(1, len(chunk.split())) for chunk in chunks]
        total_words = sum(word_counts)

        if total_duration is not None:
            if total_duration < n_chunks * cfg.min_duration_seconds:
                raise SegmentationError(
                    f"Requested total duration ({total_duration:.2f}s) is insufficient to allocate "
                    f"{n_chunks} scenes with minimum length of {cfg.min_duration_seconds}s each.",
                    code="DURATION_TOO_SHORT_FOR_SCENES"
                )
            if total_duration > n_chunks * cfg.max_duration_seconds:
                raise SegmentationError(
                    f"Requested total duration ({total_duration:.2f}s) exceeds maximum allowed for {n_chunks} scenes.",
                    code="DURATION_TOO_LONG_FOR_SCENES"
                )

            # Proportional allocation by word count
            raw_durations = [
                (wc / total_words) * total_duration for wc in word_counts
            ]

            # Enforce minimums and distribute remaining time
            durations = [max(cfg.min_duration_seconds, min(cfg.max_duration_seconds, d)) for d in raw_durations]
            current_sum = sum(durations)
            diff = total_duration - current_sum

            # Adjust last scene or distribute remainder proportionally
            durations[-1] = round(durations[-1] + diff, 3)

            # If last scene fell below minimum due to rounding, re-level
            if durations[-1] < cfg.min_duration_seconds:
                durations[-1] = cfg.min_duration_seconds
                excess = sum(durations) - total_duration
                # Subtract excess from largest scenes
                for i in range(len(durations) - 2, -1, -1):
                    can_take = durations[i] - cfg.min_duration_seconds
                    deduct = min(excess, can_take)
                    durations[i] = round(durations[i] - deduct, 3)
                    excess -= deduct
                    if excess <= 0.001:
                        break

            return [round(d, 3) for d in durations]

        else:
            # Script-only mode: estimate duration based on speech cadence (WPM)
            sec_per_word = 60.0 / cfg.words_per_minute
            durations = []
            for wc in word_counts:
                # Add 0.3s pause buffer per scene for natural cadence
                est = (wc * sec_per_word) + 0.3
                clamped = max(cfg.min_duration_seconds, min(cfg.max_duration_seconds, est))
                durations.append(round(clamped, 2))

            return durations

    def _generate_visual_description(self, text: str, scene_index: int) -> str:
        """
        Extracts key visual subjects and context to generate an actionable B-roll description.
        """
        cleaned = re.sub(r'[^\w\s]', '', text).strip()
        words = cleaned.split()

        # Filter out common stop words to identify key conceptual terms
        stop_words = {
            "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to",
            "for", "with", "by", "from", "of", "is", "are", "was", "were", "be",
            "been", "being", "have", "has", "had", "do", "does", "did", "this",
            "that", "these", "those", "it", "its", "you", "we", "they", "i", "my"
        }
        content_words = [w for w in words if w.lower() not in stop_words]

        if content_words:
            key_subject = " ".join(content_words[:6])
            desc = f"Visual showing {key_subject.lower()} representing: {text[:80]}"
        else:
            desc = f"Visual representation of scene {scene_index}: {text[:80]}"

        # Bound to length limits
        if len(desc) > settings.MAX_VISUAL_DESCRIPTION_LENGTH:
            desc = desc[:settings.MAX_VISUAL_DESCRIPTION_LENGTH - 3] + "..."
        if len(desc) < settings.MIN_VISUAL_DESCRIPTION_LENGTH:
            desc = f"B-roll visual for scene {scene_index}"

        return desc

    @staticmethod
    def verify_text_preservation(original_text: str, scenes: List[Scene]) -> bool:
        """
        Validates that all words from the original script are preserved verbatim in the scenes
        in exact sequential order without omissions or hallucinations.
        """
        def normalize_words(t: str) -> List[str]:
            return [re.sub(r'[^\w]', '', w).lower() for w in t.split() if re.sub(r'[^\w]', '', w)]

        orig_words = normalize_words(original_text)
        scene_words: List[str] = []
        for s in scenes:
            scene_words.extend(normalize_words(s.narration))

        return orig_words == scene_words


scene_segmenter = SceneSegmenter()
