"""
RSS Connector - Cloud Function Entry Point
"""

import functions_framework
from flask import Request
from rss_service import RSSService
from database import logger


@functions_framework.http
def rss_connector(request: Request):
    """
    HTTP Cloud Function entry point for RSS Connector
    
    Args:
        request: Flask Request object
        
    Returns:
        Response tuple (message, status_code)
    """
    try:
        logger.info("RSS Connector triggered via HTTP")
        
        service = RSSService()
        service.fetch_and_store_links()
        
        return "RSS Connector executed successfully", 200
        
    except Exception as e:
        logger.error(f"RSS Connector failed: {e}", exc_info=True)
        return f"Error: {str(e)}", 500
