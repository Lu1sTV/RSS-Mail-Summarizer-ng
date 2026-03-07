import os

class Config:
    """RSS Feed Konfiguration"""
    
    RSS_FEEDS = [
        {
            "name": "hackernews",
            "url": "https://news.ycombinator.com/rss",
            "mode": "since_last_crawl",
            "time_window_hours": None,
            "use_etag": True
        },
        {
            "name": "techcrunch",
            "url": "https://techcrunch.com/feed/",
            "mode": "time_window",
            "time_window_hours": 24,
            "use_etag": False
        }
    ]
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
