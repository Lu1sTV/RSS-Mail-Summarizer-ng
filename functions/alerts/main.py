import os
import sys
import json
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple

import functions_framework
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup
from urllib.parse import unquote

from config import AlertConfig
from database import FirestoreDatabase

# Logger Setup
logger = logging.getLogger("alerts_processor")
logger.setLevel(getattr(logging, os.environ.get("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG))

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class GmailService:
    """Gmail API client for reading and moving alert mails."""

    def __init__(self) -> None:
        try:
            token_env: Optional[str] = os.environ.get("GMAIL_TOKEN_JSON")
            if token_env:
                logger.debug("Gmail: using env token.")
                token_data: Dict[str, Any] = json.loads(token_env)
                creds: Credentials = Credentials.from_authorized_user_info(token_data, AlertConfig.SCOPES)
            else:
                logger.error("Gmail token is missing.")
                raise RuntimeError("GMAIL_TOKEN_JSON environment variable is missing but required.")

            self.service: Resource = build('gmail', 'v1', credentials=creds)

            profile = self.service.users().getProfile(userId='me').execute()
            logger.info(f"Gmail connected: {profile.get('emailAddress')}")
        except HttpError as e:
            logger.error(f"Gmail HTTP error: {e}")
            raise RuntimeError(f"Gmail Connection failed (HTTP Error): {e}")
        except Exception as e:
            logger.error(f"Gmail connection failed: {e}")
            raise RuntimeError(f"Gmail Connection failed: {str(e)}")

    def get_label_id(self, label_name: str) -> Optional[str]:
        """Resolve a Gmail label name to its ID."""
        try:
            response: Dict[str, Any] = self.service.users().labels().list(userId='me').execute()
            for label in response.get('labels', []):
                if label['name'].lower() == label_name.lower():
                    return label['id']
            return None
        except Exception as e:
            logger.error(f"Failed to resolve label '{label_name}': {e}")
            raise

    def get_messages(self, label_id: str) -> List[Dict[str, str]]:
        """Fetch messages by label, respecting MAX_RESULTS, MAX_AGE_DAYS and pagination via MAX_PAGES."""
        try:
            kwargs: Dict[str, Any] = {"userId": "me", "labelIds": [label_id]}
            if AlertConfig.MAX_RESULTS:
                kwargs["maxResults"] = AlertConfig.MAX_RESULTS
            if AlertConfig.MAX_AGE_DAYS:
                kwargs["q"] = f"newer_than:{AlertConfig.MAX_AGE_DAYS}d"

            all_messages: List[Dict[str, str]] = []
            pages_fetched: int = 0

            while True:
                response: Dict[str, Any] = self.service.users().messages().list(**kwargs).execute()
                all_messages.extend(response.get('messages', []))
                pages_fetched += 1

                next_page_token: Optional[str] = response.get('nextPageToken')
                if not next_page_token:
                    break
                if AlertConfig.MAX_PAGES and pages_fetched >= AlertConfig.MAX_PAGES:
                    logger.info(f"Reached MAX_PAGES limit ({AlertConfig.MAX_PAGES}), stopping pagination.")
                    break
                kwargs["pageToken"] = next_page_token

            logger.debug(f"Fetched {len(all_messages)} messages in {pages_fetched} page(s) for label {label_id}.")
            return all_messages
        except Exception as e:
            logger.error(f"Failed to fetch messages for label {label_id}: {e}")
            raise

    def get_message_body(self, msg_id: str) -> str:
        """Extract the HTML body from a message."""
        try:
            msg: Dict[str, Any] = self.service.users().messages().get(userId='me', id=msg_id).execute()
            payload: Dict[str, Any] = msg.get('payload', {})
            parts: List[Dict[str, Any]] = payload.get('parts', [payload])
            for part in parts:
                if part.get('mimeType') == 'text/html':
                    return part.get('body', {}).get('data', '')
            return ""
        except Exception as e:
            logger.error(f"Failed to get body for message {msg_id}: {e}")
            return ""

    def move_message(self, msg_id: str, id_in: str, id_out: str) -> None:
        """Move a message from one label to another."""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'addLabelIds': [id_out], 'removeLabelIds': [id_in]}
            ).execute()
            logger.debug(f"Moved message {msg_id}.")
        except Exception as e:
            logger.error(f"Failed to move message {msg_id}: {e}")
            raise

class AlertProcessor:
    """Parses alert mails, extracts links, saves to Firestore."""

    def __init__(self, gmail: GmailService, db: FirestoreDatabase) -> None:
        self.gmail: GmailService = gmail
        self.db: FirestoreDatabase = db

    def _clean_url(self, url: str) -> str:
        """Extract real URL from Google redirect wrappers."""
        if "google." in url and "/url" in url and ("q=" in url or "url=" in url):
            param: str = "q=" if "q=" in url else "url="
            try:
                return unquote(url.split(param)[1].split("&")[0])
            except IndexError:
                pass
        return url

    def _is_blacklisted(self, url: str) -> bool:
        """Check URL against blacklist."""
        return any(b.lower() in url.lower() for b in AlertConfig.LINK_BLACKLIST)

    def process_config(self, config: Dict[str, str]) -> Dict[str, Any]:
        """Process one alert config: fetch mails, extract links, save & move."""
        result: Dict[str, Any] = {"name": config["name"], "messages_processed": 0, "status": "ok", "error": None}
        logger.info(f"Processing alert: {config['name']}")

        try:
            id_in: Optional[str] = self.gmail.get_label_id(config["label"])
            id_out: Optional[str] = self.gmail.get_label_id(config["processed_label"])

            if not id_in:
                logger.warning(f"Input label '{config['label']}' not found.")
                result["status"] = "warning"
                result["error"] = f"Input label '{config['label']}' not found in Gmail."
                return result

            if not id_out:
                logger.warning(f"Output label '{config['processed_label']}' not found.")
                result["status"] = "warning"
                result["error"] = f"Output label '{config['processed_label']}' not found in Gmail."
                return result

            messages: List[Dict[str, str]] = self.gmail.get_messages(id_in)
            logger.info(f"{len(messages)} messages in '{config['label']}'.")

            for msg_summary in messages:
                msg_id: str = msg_summary['id']
                body_data: str = self.gmail.get_message_body(msg_id)

                if not body_data:
                    logger.warning(f"No HTML body for {msg_id}, skipping.")
                    continue

                try:
                    html_content: str = base64.urlsafe_b64decode(body_data).decode()
                except Exception as decode_err:
                    logger.error(f"Failed to decode body for message {msg_id}: {decode_err}")
                    continue

                soup: BeautifulSoup = BeautifulSoup(html_content, 'html.parser')

                links_found: int = 0
                for a in soup.find_all('a', href=True):
                    url: str = self._clean_url(a['href'])
                    if not self._is_blacklisted(url):
                        self.db.save_url(url, config["name"])
                        links_found += 1

                logger.debug(f"{links_found} links in message {msg_id}.")
                self.gmail.move_message(msg_id, id_in, id_out)
                result["messages_processed"] += 1

            logger.info(f"Done '{config['name']}': {result['messages_processed']} mails processed.")
            return result

        except Exception as e:
            logger.error(f"Error processing '{config['name']}': {e}", exc_info=True)
            result["status"] = "error"
            result["error"] = str(e)
            return result

@functions_framework.http
def alerts_mvp_endpoint(request: Any) -> Tuple[str, int]:
    """HTTP entry point – runs the full alerts pipeline."""
    logger.info("Starting alerts_mvp_endpoint.")
    try:
        gmail = GmailService()
        db = FirestoreDatabase()
        processor = AlertProcessor(gmail, db)

        results: List[Dict[str, Any]] = []
        total_processed: int = 0
        has_errors: bool = False

        for c in AlertConfig.ALERT_CONFIG:
            res: Dict[str, Any] = processor.process_config(c)
            results.append(res)
            total_processed += res["messages_processed"]
            if res["status"] == "error":
                has_errors = True

        configs_with_errors: int = sum(1 for r in results if r["status"] == "error")

        response_data: Dict[str, Any] = {
            "status": "error" if has_errors else "success",
            "resource": "firestore/website",
            "details": {
                "entries_processed": total_processed,
                "configs_run": len(results),
                "configs_with_errors": configs_with_errors,
                "per_config": results,
            },
        }

        if has_errors:
            logger.error("Execution finished with errors.")
            return json.dumps(response_data, indent=2), 500

        logger.info(f"Execution completed. {total_processed} mails processed.")
        return json.dumps(response_data, indent=2), 200

    except RuntimeError as re:
        logger.critical(f"Init error: {re}")
        return json.dumps({"status": "error", "resource": "firestore/website", "details": {"error": "Initialization failed"}}, indent=2), 500
    except Exception as e:
        logger.critical(f"Server error: {e}", exc_info=True)
        return json.dumps({"status": "error", "resource": "firestore/website", "details": {"error": "Internal server error"}}, indent=2), 500