"""
Unit Tests fuer MastodonService

Testet die Business Logic mit Mock-Objekten (keine echten API-Aufrufe).
"""

import sys
import types
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

# Stub database module to avoid Firebase init during test import
database_stub = types.ModuleType("database")
database_stub.add_url_to_website_collection = lambda *args, **kwargs: None
database_stub.get_last_toot_id = lambda *args, **kwargs: None
database_stub.save_last_toot_id = lambda *args, **kwargs: None
sys.modules["database"] = database_stub

from mastodon_service import MastodonService
from conftest import has_firebase_env


class TestMastodonService:
    """Test Suite für MastodonService"""
    
    @pytest.fixture
    def mock_logger(self):
        """Mock Logger für Tests"""
        with patch("mastodon_service.logger") as mock:
            yield mock
    
    @pytest.fixture
    def mock_database_functions(self):
        """Mock Database-Funktionen"""
        with patch("mastodon_service.get_last_toot_id") as mock_get, \
             patch("mastodon_service.save_last_toot_id") as mock_save, \
             patch("mastodon_service.add_url_to_website_collection") as mock_add:
            yield {
                "get_last_toot_id": mock_get,
                "save_last_toot_id": mock_save,
                "add_url_to_website_collection": mock_add,
            }
    
    @pytest.fixture
    def mock_mastodon_api(self):
        """Mock Mastodon API"""
        with patch("mastodon_service.Mastodon") as mock:
            yield mock
    
    @pytest.fixture
    def service(self, mock_mastodon_api, mock_database_functions, mock_logger):
        """Erstellt einen MastodonService mit Mocks"""
        return MastodonService()
    
    # =====================================================
    # Tests für fetch_and_store_links
    # =====================================================
    
    def test_fetch_and_store_links_success_with_new_toots(
        self, service, mock_database_functions, mock_mastodon_api, mock_logger
    ):
        """Test: Erfolgreiches Abrufen und Speichern von neuen Toots"""
        # Setup
        mock_db_functions = mock_database_functions
        mock_db_functions["get_last_toot_id"].return_value = None  # Erster Lauf
        
        mock_account = {"id": 12345}
        service.mastodon.account_lookup.return_value = mock_account
        
        mock_toots = [
            {
                "id": "100",
                "content": '<a href="https://example.com">Link 1</a>'
            },
            {
                "id": "101",
                "content": '<a href="https://test.com">Link 2</a>'
            }
        ]
        service.mastodon.account_statuses.return_value = mock_toots
        service.mastodon.fetch_next.return_value = None
        
        # Execute
        service.fetch_and_store_links()
        
        # Assert
        # Account lookup wurde aufgerufen
        service.mastodon.account_lookup.assert_called_once_with("pinboard_pop@mstdn.social")
        
        # Toots wurden abgerufen
        service.mastodon.account_statuses.assert_called_once_with(
            12345, limit=20, since_id=None
        )
        
        # Neue Toot-ID wurde gespeichert
        mock_db_functions["save_last_toot_id"].assert_called_once_with(101)
        
        # Links wurden gespeichert
        assert mock_db_functions["add_url_to_website_collection"].call_count == 2
        mock_db_functions["add_url_to_website_collection"].assert_any_call("https://example.com")
        mock_db_functions["add_url_to_website_collection"].assert_any_call("https://test.com")
        
        # Logging
        mock_logger.info.assert_any_call("Starte Mastodon-Connector...")
        mock_logger.info.assert_any_call("Erster Lauf: 20 neueste Toots werden geladen.")
    
    def test_fetch_and_store_links_with_since_id(
        self, service, mock_database_functions, mock_mastodon_api, mock_logger
    ):
        """Test: Abrufen mit already known since_id"""
        mock_db_functions = mock_database_functions
        mock_db_functions["get_last_toot_id"].return_value = 99  # Bekannte ID
        
        mock_account = {"id": 12345}
        service.mastodon.account_lookup.return_value = mock_account
        
        mock_toots = [{"id": "100", "content": '<a href="https://new.com">New</a>'}]
        service.mastodon.account_statuses.return_value = mock_toots
        service.mastodon.fetch_next.return_value = None
        
        # Execute
        service.fetch_and_store_links()
        
        # Assert
        service.mastodon.account_statuses.assert_called_once_with(
            12345, limit=20, since_id=99
        )
        mock_logger.info.assert_any_call("Lade neue Toots seit ID 99 ...")
    
    def test_fetch_and_store_links_no_new_toots(
        self, service, mock_database_functions, mock_mastodon_api, mock_logger
    ):
        """Test: Keine neuen Toots vorhanden"""
        mock_db_functions = mock_database_functions
        mock_db_functions["get_last_toot_id"].return_value = 99
        
        mock_account = {"id": 12345}
        service.mastodon.account_lookup.return_value = mock_account
        
        service.mastodon.account_statuses.return_value = []  # Keine Toots
        
        # Execute
        service.fetch_and_store_links()
        
        # Assert
        mock_logger.info.assert_any_call("Keine neuen Toots gefunden.")
        mock_db_functions["save_last_toot_id"].assert_not_called()
    
    def test_fetch_and_store_links_account_not_found(
        self, service, mock_database_functions, mock_mastodon_api, mock_logger
    ):
        """Test: Benutzer nicht gefunden"""
        mock_db_functions = mock_database_functions
        service.mastodon.account_lookup.return_value = None
        
        # Execute
        service.fetch_and_store_links()
        
        # Assert
        mock_logger.error.assert_called_once_with("Benutzer pinboard_pop nicht gefunden.")
        mock_db_functions["save_last_toot_id"].assert_not_called()
    
    def test_fetch_and_store_links_exception_handling(
        self, service, mock_database_functions, mock_mastodon_api, mock_logger
    ):
        """Test: Exception Handling"""
        service.mastodon.account_lookup.side_effect = Exception("API Error")
        
        # Execute - sollte nicht crashen
        service.fetch_and_store_links()
        
        # Assert
        mock_logger.exception.assert_called()
        assert "Fehler bei Mastodon-Abruf" in str(mock_logger.exception.call_args)
    
    # =====================================================
    # Tests für _extract_and_store_links
    # =====================================================
    
    def test_extract_and_store_links_various_link_types(
        self, service, mock_database_functions
    ):
        """Test: Verschiedene Link-Typen werden korrekt filtert"""
        mock_db_functions = mock_database_functions
        
        toots = [
            {
                "id": "100",
                "content": """
                    <a href="https://example.com">External Link</a>
                    <a href="https://mstdn.social/tags/test" rel="tag">Hashtag (should skip)</a>
                    <a href="https://mstdn.social/@user" class="mention">Mention (should skip)</a>
                    <a href="https://test.org">Another Link</a>
                """
            }
        ]
        
        # Execute
        result = service._extract_and_store_links(toots)
        
        # Assert
        # Nur externe Links sollten gespeichert sein, keine Hashtags/Mentions
        assert len(result) == 2
        mock_db_functions["add_url_to_website_collection"].assert_any_call("https://example.com")
        mock_db_functions["add_url_to_website_collection"].assert_any_call("https://test.org")
    
    def test_extract_and_store_links_empty_toots(
        self, service, mock_database_functions
    ):
        """Test: Leere Toot-Liste"""
        mock_db_functions = mock_database_functions
        
        # Execute
        result = service._extract_and_store_links([])
        
        # Assert
        assert result == []
        mock_db_functions["add_url_to_website_collection"].assert_not_called()
    
    def test_extract_and_store_links_no_links(
        self, service, mock_database_functions
    ):
        """Test: Toots ohne Links"""
        mock_db_functions = mock_database_functions
        
        toots = [
            {"id": "100", "content": "Just text, no links here"},
            {"id": "101", "content": "More text"}
        ]
        
        # Execute
        result = service._extract_and_store_links(toots)
        
        # Assert
        assert result == []
        mock_db_functions["add_url_to_website_collection"].assert_not_called()
    
    # =====================================================
    # Integration Tests
    # =====================================================
    
    def test_full_flow_pagination(
        self, service, mock_database_functions, mock_mastodon_api, mock_logger
    ):
        """Test: Kompletter Flow mit Pagination"""
        mock_db_functions = mock_database_functions
        mock_db_functions["get_last_toot_id"].return_value = 98
        
        mock_account = {"id": 12345}
        service.mastodon.account_lookup.return_value = mock_account
        
        # Erste Seite
        first_page = [
            {"id": "100", "content": '<a href="https://page1.com">Link</a>'},
            {"id": "101", "content": '<a href="https://page1-2.com">Link</a>'}
        ]
        
        # Zweite Seite
        second_page = [
            {"id": "102", "content": '<a href="https://page2.com">Link</a>'}
        ]
        
        service.mastodon.account_statuses.return_value = first_page
        service.mastodon.fetch_next.side_effect = [second_page, None]
        
        # Execute
        service.fetch_and_store_links()
        
        # Assert
        assert mock_db_functions["add_url_to_website_collection"].call_count == 3
        mock_db_functions["save_last_toot_id"].assert_called_once_with(102)

    # =====================================================
    # Integration Tests (optional)
    # =====================================================

    @pytest.mark.integration
    def test_integration_fetch_and_store_links(self):
        """Integration test: real Mastodon + Firebase (requires env)."""
        if not has_firebase_env():
            pytest.skip("RSS_FIREBASE_KEY not set")

        service = MastodonService()
        service.fetch_and_store_links()


if __name__ == "__main__":
    # Tests ausführen: pytest test_mastodon_service.py -v
    pytest.main([__file__, "-v"])
