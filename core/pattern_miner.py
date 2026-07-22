"""
Heuristic Shadow Agent - Pattern Mining Engine
Analyzes event streams to discover repetitive workflow patterns
using sequence similarity clustering and PrefixSpan-inspired mining.

Confidence score formula:
    Cs = w_freq * FreqScore + w_struct * StructScore + w_temp * TempScore
    where each sub-score ∈ [0, 1] and weights sum to 1.
"""

import hashlib
import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from config import Config
from db.database import db_manager
from db.models import RawEvent, DetectedPattern

logger = logging.getLogger(__name__)


class PatternMiner:
    """
    Heuristic pattern discovery engine.
    Identifies repeating action sequences from raw events using
    simplified PrefixSpan sequence mining with confidence scoring.
    """

    CONFIDENCE_WEIGHTS = {
        "frequency": 0.45,
        "structure": 0.35,
        "temporal": 0.20,
    }

    def __init__(self):
        self.threshold = Config.PATTERN_CONFIDENCE_THRESHOLD
        self.min_freq = Config.PATTERN_MIN_FREQUENCY
        self.min_len = Config.PATTERN_MIN_SEQUENCE_LENGTH
        self.max_len = Config.PATTERN_MAX_SEQUENCE_LENGTH
        self.window_hours = Config.ROLLING_WINDOW_HOURS

    # ------------------------------------------------------------------
    # Event abstraction
    # ------------------------------------------------------------------

    @staticmethod
    def _abstract_event(event: RawEvent) -> str:
        """
        Convert a raw event into an abstract action token.
        This reduces noise by binning similar events.

        Example tokens:
            CLICK:chrome.exe
            KEY:notepad.exe
            SWITCH:outlook.exe
            COPY:excel.exe
        """
        event_type = event.event_type
        process = (event.process_name or "unknown").replace(".exe", "").lower()

        if event_type == "click":
            return f"CLICK:{process}"
        elif event_type == "keypress":
            # Special tokens for common shortcuts
            key = (event.key_name or "").lower()
            if "ctrl" in key or "cmd" in key:
                return f"HOTKEY:{process}"
            if key in ("key.enter", "enter", "\r", "\n"):
                return f"ENTER:{process}"
            if key in ("key.tab", "tab", "\t"):
                return f"TAB:{process}"
            if "key.ctrl" in key and "c" in key:
                return f"COPY:{process}"
            if "key.ctrl" in key and "v" in key:
                return f"PASTE:{process}"
            return f"KEY:{process}"
        elif event_type == "app_switch":
            return f"SWITCH:{process}"
        elif event_type == "copy":
            return f"COPY:{process}"
        return f"{event_type}:{process}"

    # ------------------------------------------------------------------
    # Sequence extraction
    # ------------------------------------------------------------------

    def _get_recent_events(self) -> list:
        """Fetch recent raw events within the rolling window."""
        cutoff = datetime.utcnow() - timedelta(hours=self.window_hours)
        try:
            with db_manager.get_session() as session:
                events = (
                    session.query(RawEvent)
                    .filter(
                        RawEvent.timestamp >= cutoff,
                        RawEvent.is_sensitive == False,  # noqa: E712
                    )
                    .order_by(RawEvent.timestamp.asc())
                    .limit(20000)
                    .all()
                )
                return events
        except Exception as e:
            logger.error(f"Failed to fetch events: {e}")
            return []

    def _build_event_sequences(self, events: list, gap_threshold: float = 5.0) -> list:
        """
        Group events into sessions/sequences separated by time gaps.
        A gap > threshold splits sequences.
        """
        if not events:
            return []

        sequences = []
        current_seq = []
        last_ts = None

        for event in events:
            if last_ts is not None:
                gap = (event.timestamp - last_ts).total_seconds()
                if gap > gap_threshold and current_seq:
                    sequences.append(current_seq)
                    current_seq = []

            token = self._abstract_event(event)
            current_seq.append(token)
            last_ts = event.timestamp

        if current_seq:
            sequences.append(current_seq)

        return sequences

    # ------------------------------------------------------------------
    # Pattern discovery (simplified PrefixSpan)
    # ------------------------------------------------------------------

    def mine_patterns(self) -> list:
        """
        Main mining method. Returns list of discovered patterns
        with confidence scores.
        """
        logger.info("Starting pattern mining cycle...")
        start = time.time()

        events = self._get_recent_events()
        if len(events) < self.min_freq * 2:
            logger.debug(f"Insufficient events ({len(events)}) for mining.")
            return []

        sequences = self._build_event_sequences(events)

        # Extract frequent subsequences
        patterns = self._extract_frequent_subsequences(sequences)

        # Score each pattern
        scored_patterns = []
        for seq, freq in patterns:
            if len(seq) < self.min_len or len(seq) > self.max_len:
                continue
            if freq < self.min_freq:
                continue

            score = self._calculate_confidence(seq, freq, sequences)
            if score >= self.threshold:
                scored_patterns.append({
                    "sequence": seq,
                    "frequency": freq,
                    "confidence": score,
                    "hash": self._hash_sequence(seq),
                })

        # Sort by confidence descending
        scored_patterns.sort(key=lambda p: p["confidence"], reverse=True)

        elapsed = time.time() - start
        logger.info(
            f"Mining complete in {elapsed:.2f}s. "
            f"Found {len(scored_patterns)} patterns above threshold ({self.threshold})."
        )

        # Persist new patterns
        self._persist_patterns(scored_patterns)

        return scored_patterns

    def _extract_frequent_subsequences(self, sequences: list) -> list:
        """
        Extract frequent sub-sequences using a sliding window approach.
        Returns list of (sequence, frequency) tuples.
        """
        # Count all possible sub-sequences of lengths [min_len, max_len]
        pattern_counter = Counter()

        for seq in sequences:
            seq_len = len(seq)
            for length in range(self.min_len, min(self.max_len + 1, seq_len + 1)):
                for start in range(seq_len - length + 1):
                    subseq = tuple(seq[start : start + length])
                    pattern_counter[subseq] += 1

        # Filter by minimum frequency
        frequent = [
            (list(seq), count)
            for seq, count in pattern_counter.items()
            if count >= self.min_freq and self.min_len <= len(seq) <= self.max_len
        ]

        return frequent

    # ------------------------------------------------------------------
    # Confidence scoring
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self, sequence: list, frequency: int, all_sequences: list
    ) -> float:
        """
        Calculate confidence score for a pattern.

        Components:
        - Frequency: how often does this pattern appear?
        - Structure: how coherent/consistent are the steps?
        - Temporal: are occurrences evenly spaced in time?
        """
        n_sequences = max(len(all_sequences), 1)

        # Frequency score: normalized by total sequences
        freq_score = min(frequency / max(n_sequences * 0.1, 1), 1.0)

        # Structure score: penalty for very short sequences, bonus for diversity
        len_factor = min((len(sequence) - self.min_len) / (self.max_len - self.min_len + 1), 1.0)
        unique_steps = len(set(sequence)) / max(len(sequence), 1)
        struct_score = 0.5 * len_factor + 0.5 * unique_steps

        # Temporal consistency score: how evenly distributed are occurrences?
        temp_score = min(frequency / 5.0, 1.0)

        # Weighted combination
        confidence = (
            self.CONFIDENCE_WEIGHTS["frequency"] * freq_score
            + self.CONFIDENCE_WEIGHTS["structure"] * struct_score
            + self.CONFIDENCE_WEIGHTS["temporal"] * temp_score
        )

        return round(confidence, 4)

    @staticmethod
    def _hash_sequence(sequence: list) -> str:
        """Generate a stable hash for a sequence pattern."""
        content = "|".join(sequence)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_patterns(self, patterns: list) -> None:
        """Save newly discovered patterns to the database."""
        try:
            with db_manager.get_session() as session:
                new_count = 0
                for p in patterns:
                    existing = (
                        session.query(DetectedPattern)
                        .filter_by(pattern_hash=p["hash"])
                        .first()
                    )
                    if existing:
                        # Update frequency and confidence
                        existing.frequency_count = max(
                            existing.frequency_count, p["frequency"]
                        )
                        existing.confidence_score = max(
                            existing.confidence_score, p["confidence"]
                        )
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Generate a human-readable name
                        name_parts = [
                            s.split(":", 1)[1] if ":" in s else s
                            for s in p["sequence"]
                        ]
                        name = " -> ".join(name_parts[:4])
                        if len(p["sequence"]) > 4:
                            name += f" ... (+{len(p['sequence']) - 4} steps)"

                        pattern = DetectedPattern(
                            pattern_hash=p["hash"],
                            pattern_name=name,
                            frequency_count=p["frequency"],
                            confidence_score=p["confidence"],
                            sequence_json=json.dumps(p["sequence"]),
                            status="discovered",
                        )
                        session.add(pattern)
                        new_count += 1

            if new_count > 0:
                logger.info(f"Persisted {new_count} new patterns.")
        except Exception as e:
            logger.error(f"Failed to persist patterns: {e}")

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_ready_patterns(self) -> list:
        """Get all patterns with status 'discovered' or 'validating'."""
        try:
            with db_manager.get_session() as session:
                patterns = (
                    session.query(DetectedPattern)
                    .filter(
                        DetectedPattern.status.in_(["discovered", "validating"])
                    )
                    .order_by(DetectedPattern.confidence_score.desc())
                    .limit(20)
                    .all()
                )
                return [p.to_dict() for p in patterns]
        except Exception as e:
            logger.error(f"Failed to fetch ready patterns: {e}")
            return []

    def get_pattern_by_hash(self, pattern_hash: str) -> Optional[dict]:
        """Retrieve a specific pattern by its hash."""
        try:
            with db_manager.get_session() as session:
                pattern = (
                    session.query(DetectedPattern)
                    .filter_by(pattern_hash=pattern_hash)
                    .first()
                )
                return pattern.to_dict() if pattern else None
        except Exception as e:
            logger.error(f"Failed to fetch pattern {pattern_hash}: {e}")
            return None

    def update_pattern_status(self, pattern_hash: str, status: str) -> bool:
        """Update a pattern's status (discovered/validating/ready/dismissed)."""
        try:
            with db_manager.get_session() as session:
                pattern = (
                    session.query(DetectedPattern)
                    .filter_by(pattern_hash=pattern_hash)
                    .first()
                )
                if pattern:
                    pattern.status = status
                    pattern.updated_at = datetime.utcnow()
                    logger.info(f"Pattern {pattern_hash} status -> {status}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to update pattern status: {e}")
            return False

    def dismiss_pattern(self, pattern_hash: str) -> bool:
        """Dismiss (ignore) a discovered pattern."""
        return self.update_pattern_status(pattern_hash, "dismissed")

    def get_statistics(self) -> dict:
        """Get mining statistics."""
        try:
            with db_manager.get_session() as session:
                from sqlalchemy import func
                total = session.query(func.count(DetectedPattern.id)).scalar() or 0
                discovered = (
                    session.query(func.count(DetectedPattern.id))
                    .filter_by(status="discovered")
                    .scalar()
                    or 0
                )
                ready = (
                    session.query(func.count(DetectedPattern.id))
                    .filter_by(status="ready")
                    .scalar()
                    or 0
                )
                avg_conf = (
                    session.query(func.avg(DetectedPattern.confidence_score))
                    .scalar()
                    or 0
                )
                return {
                    "total_patterns": total,
                    "discovered": discovered,
                    "ready": ready,
                    "avg_confidence": round(float(avg_conf), 4),
                    "threshold": self.threshold,
                }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}
