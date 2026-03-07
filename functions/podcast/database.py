import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

import firebase_admin
from firebase_admin import credentials, firestore

from config import PodcastConfig

# Logger Setup
logger = logging.getLogger("podcast_generator")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class FirestoreDatabase:
    """Firestore access layer for the podcast pipeline."""

    def __init__(self) -> None:
        try:
            key_json: Optional[str] = os.environ.get("RSS_FIREBASE_KEY")
            if key_json:
                logger.debug("Firebase: using env secret.")
                cred = credentials.Certificate(json.loads(key_json))
            else:
                logger.debug("Firebase: using local key file.")
                key_path: str = os.path.join(os.path.dirname(__file__), "keys", "serviceAccountKey.json")
                cred = credentials.Certificate(key_path)

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()

            # Quick connectivity check
            self.db.collection("website").limit(1).get()
            logger.info("Firestore connected.")
        except Exception as e:
            logger.error(f"Firestore connection failed: {e}")
            raise RuntimeError(f"Firestore Connection failed: {str(e)}")

    @staticmethod
    def _parse_timestamp(ts: Any) -> Optional[datetime]:
        """Parse various timestamp formats to UTC datetime."""
        if ts is None:
            return None
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts
        if isinstance(ts, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt: datetime = datetime.strptime(ts, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            logger.warning(f"Unknown timestamp format: {ts}")
        return None

    def fetch_entries(self) -> List[Tuple[Any, Dict[str, Any]]]:
        """Fetch unprocessed entries per config. Returns (ref, data) tuples."""
        candidates: List[Tuple[Any, Dict[str, Any]]] = []

        # Mastodon
        if PodcastConfig.SOURCES.get("mastodon"):
            logger.info("Querying source=mastodon...")
            query = self.db.collection("website").where("source", "==", "mastodon").stream()
            for doc in query:
                data: Dict[str, Any] = doc.to_dict()
                if data.get("podcast_generated", False):
                    continue
                if PodcastConfig.SOURCES["mastodon"] != ["*"]:
                    pass  # Future: filter by specific accounts
                candidates.append((doc.reference, data))
            logger.info(f"Mastodon: {len(candidates)} candidates.")

        # Alerts
        if PodcastConfig.SOURCES.get("alerts"):
            count_before: int = len(candidates)
            logger.info("Querying alert=true...")
            query = self.db.collection("website").where("alert", "==", True).stream()
            for doc in query:
                data: Dict[str, Any] = doc.to_dict()
                if data.get("podcast_generated", False):
                    continue
                if PodcastConfig.SOURCES["alerts"] != ["*"]:
                    if data.get("category") not in PodcastConfig.SOURCES["alerts"]:
                        continue
                candidates.append((doc.reference, data))
            logger.info(f"Alerts: {len(candidates) - count_before} candidates.")

        # RSS (placeholder)
        if PodcastConfig.SOURCES.get("rss"):
            count_before: int = len(candidates)
            logger.info("Querying source=rss...")
            query = self.db.collection("website").where("source", "==", "rss").stream()
            for doc in query:
                data: Dict[str, Any] = doc.to_dict()
                if data.get("podcast_generated", False):
                    continue
                candidates.append((doc.reference, data))
            logger.info(f"RSS: {len(candidates) - count_before} candidates.")

        # Deduplicate
        seen_ids: set = set()
        unique: List[Tuple[Any, Dict[str, Any]]] = []
        for ref, data in candidates:
            if ref.id not in seen_ids:
                seen_ids.add(ref.id)
                unique.append((ref, data))
        candidates = unique

        # Time window
        if PodcastConfig.TIME_WINDOW_HOURS is not None:
            cutoff: datetime = datetime.now(timezone.utc) - timedelta(hours=PodcastConfig.TIME_WINDOW_HOURS)
            filtered: List[Tuple[Any, Dict[str, Any]]] = []
            for ref, data in candidates:
                ts: Optional[datetime] = self._parse_timestamp(data.get("timestamp"))
                if ts is None or ts >= cutoff:
                    filtered.append((ref, data))
            logger.info(f"Time filter ({PodcastConfig.TIME_WINDOW_HOURS}h): {len(candidates)} -> {len(filtered)}.")
            candidates = filtered

        # Sort newest first
        candidates.sort(
            key=lambda x: self._parse_timestamp(x[1].get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        # Limit
        if len(candidates) > PodcastConfig.LIMIT:
            logger.info(f"Limit applied: {len(candidates)} -> {PodcastConfig.LIMIT}.")
            candidates = candidates[:PodcastConfig.LIMIT]

        logger.info(f"Selected {len(candidates)} entries.")
        return candidates

    def mark_as_podcast_generated(self, doc_refs: List[Any]) -> None:
        """Batch-set podcast_generated=True on processed docs."""
        if not doc_refs:
            return

        try:
            batch = self.db.batch()
            for i, ref in enumerate(doc_refs):
                batch.update(ref, {"podcast_generated": True})
                if (i + 1) % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
                    logger.debug(f"Batch committed: {i + 1} docs.")
            batch.commit()
            logger.info(f"Marked {len(doc_refs)} docs as generated.")
        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            raise
