"""
RSS Service - Handles RSS feed fetching and processing
"""

import time
import logging
from datetime import datetime, timedelta, timezone
import feedparser
from config import Config
from database import FirestoreRepository, logger


class RSSService:
    """Service for managing RSS feeds"""
    
    def __init__(self, repo=None):
        self.feeds = Config.RSS_FEEDS
        self.repo = repo if repo is not None else FirestoreRepository()

    
    def fetch_and_store_links(self):
        """
        Main entry point - processes all configured RSS feeds
        """
        start_time = time.time()
        logger.info(f"Starting RSS Connector - processing {len(self.feeds)} feeds")
        
        total_new_links = 0
        
        for feed_config in self.feeds:
            try:
                new_links = self._process_feed(feed_config)
                total_new_links += new_links
            except Exception as e:
                logger.error(f"Error processing feed {feed_config['name']}: {e}", exc_info=True)
                # Continue with next feed
        
        duration = time.time() - start_time
        logger.info(f"RSS Connector completed in {duration:.2f}s - {total_new_links} new links saved")
    
    def _process_feed(self, feed_config: dict) -> int:
        """
        Process single RSS feed
        
        Args:
            feed_config: Feed configuration dict
            
        Returns:
            Number of new links stored
        """
        feed_name = feed_config["name"]
        feed_url = feed_config["url"]
        mode = feed_config["mode"]
        use_etag = feed_config.get("use_etag", False)
        
        logger.info(f"Processing feed: {feed_name} (mode: {mode}, etag: {use_etag})")
        
        # Load previous state
        state = self.repo.get_feed_state(feed_name)
        
        # Prepare request headers for conditional GET
        request_headers = {}
        if use_etag and state.get("last_etag"):
            request_headers["If-None-Match"] = state["last_etag"]
        if state.get("last_modified"):
            request_headers["If-Modified-Since"] = state["last_modified"]
        
        # Fetch feed
        logger.debug(f"Fetching feed: {feed_url}")
        if request_headers:
            feed = feedparser.parse(feed_url, request_headers=request_headers)
        else:
            feed = feedparser.parse(feed_url)
        
        # Check if feed was modified (304 Not Modified)
        status = getattr(feed, 'status', None)
        if status == 304:
            logger.info(f"Feed {feed_name} not modified (304)")
            return 0
        
        if status and status >= 400:
            logger.error(f"Feed {feed_name} returned HTTP {status}")
            return 0
        
        if feed.bozo:
            logger.warning(f"Feed {feed_name} has parsing issues: {feed.bozo_exception}")
        
        if not feed.entries:
            logger.info(f"Feed {feed_name} has no entries")
            return 0
        
        # Filter entries based on mode
        filtered_entries = self._filter_entries(feed.entries, feed_config, state)
        
        if not filtered_entries:
            logger.info(f"Feed {feed_name}: No new entries after filtering")
            return 0
        
        logger.info(f"Feed {feed_name}: {len(filtered_entries)} new entries to process")
        
        # Extract and store links
        new_links_count = self._extract_and_store_links(filtered_entries, feed_name)
        
        # Update feed state
        headers = getattr(feed, 'headers', {})
        new_etag = headers.get("etag") if isinstance(headers, dict) else None
        new_last_modified = headers.get("last-modified") if isinstance(headers, dict) else None
        
        # Get most recent entry date (don't assume feed is sorted)
        latest_entry_date = None
        if filtered_entries:
            parsed_dates = [self._parse_entry_date(e) for e in filtered_entries]
            valid_dates = [d for d in parsed_dates if d is not None]
            latest_entry_date = max(valid_dates) if valid_dates else None
        
        self.repo.update_feed_state(
            feed_name=feed_name,
            etag=new_etag,
            last_modified=new_last_modified,
            last_entry_date=latest_entry_date
        )
        
        return new_links_count
    
    def _filter_entries(self, entries: list, feed_config: dict, state: dict) -> list:
        """
        Filter feed entries based on mode
        
        Args:
            entries: List of feedparser entries
            feed_config: Feed configuration
            state: Previous feed state
            
        Returns:
            Filtered list of entries
        """
        mode = feed_config["mode"]
        
        if mode == "since_last_crawl":
            return self._filter_since_last_crawl(entries, state)
        elif mode == "time_window":
            time_window_hours = feed_config.get("time_window_hours", 24)
            return self._filter_time_window(entries, time_window_hours)
        else:
            logger.warning(f"Unknown mode: {mode}, returning all entries")
            return entries
    
    def _filter_since_last_crawl(self, entries: list, state: dict) -> list:
        """
        Filter entries published after last crawl
        """
        if not state.get("last_entry_date"):
            # First run - return all entries
            logger.debug("First run for feed - returning all entries")
            return entries
        
        try:
            last_entry_date_str = state["last_entry_date"]
            last_entry_date = datetime.strptime(last_entry_date_str, "%Y-%m-%d %H:%M:%S.%f")
            last_entry_date = last_entry_date.replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.warning(f"Could not parse last_entry_date: {e}, returning all entries")
            return entries
        
        filtered = []
        for entry in entries:
            entry_date = self._parse_entry_date(entry)
            if entry_date and entry_date > last_entry_date:
                filtered.append(entry)
        
        return filtered
    
    def _filter_time_window(self, entries: list, hours: int) -> list:
        """
        Filter entries published within last N hours
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        filtered = []
        for entry in entries:
            entry_date = self._parse_entry_date(entry)
            if entry_date and entry_date > cutoff_date:
                filtered.append(entry)
        
        return filtered
    
    def _parse_entry_date(self, entry) -> datetime:
        """
        Parse entry publication date
        Handles multiple RSS date fields
        """
        # Try different date fields
        date_fields = ['published_parsed', 'updated_parsed']
        
        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                time_tuple = getattr(entry, field)
                try:
                    return datetime(*time_tuple[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
        
        # Fallback: try parsing string dates
        for field in ['published', 'updated']:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    # feedparser usually provides parsed dates, but just in case
                    return datetime.fromisoformat(getattr(entry, field))
                except Exception:
                    pass
        
        return None
    
    def _extract_and_store_links(self, entries: list, feed_name: str) -> int:
        """
        Extract URLs from entries and store in Firestore
        
        Args:
            entries: List of filtered entries
            feed_name: Feed identifier
            
        Returns:
            Number of new links stored
        """
        new_links = 0
        
        for entry in entries:
            # Main link from RSS item
            url = entry.get("link")
            
            if not url:
                logger.warning(f"Entry has no link field: {entry.get('title', 'Unknown')}")
                continue
            
            # Store in Firestore
            was_new = self.repo.add_url_to_website_collection(
                url=url,
                feed_name=feed_name,
            )
            
            if was_new:
                new_links += 1
        
        return new_links
