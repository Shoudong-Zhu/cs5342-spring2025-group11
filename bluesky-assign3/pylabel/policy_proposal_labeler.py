import os
import csv
import re 
from typing import List, Optional, Set

from atproto import Client, models 

# Import the DID resolver (using relative import from within pylabel)
from .label import did_from_handle

class FinancialSolicitationLabeler:
    """
    Labeler implementing the 'Potential Financial Solicitation' policy.
    Flags posts containing potential signals of financial requests, such as
    crypto addresses or combinations of payment keywords and calls to action.

    Label Name: potential-financial-solicitation
    """

    # Define the label
    POTENTIAL_FINANCIAL_SOLICITATION = "potential-financial-solicitation"

    def __init__(self, client: Client, input_dir: str):
        """
        Initialize the labeler.

        Args:
            client: Authenticated ATProto client instance.
            input_dir: Path to the directory containing input data ('labeler-inputs').
                       Expects:
                       - payment-app-keywords.csv
                       - crypto-keywords.csv
                       - call-to-action-keywords.csv
        """
        self.client = client
        self.input_dir = input_dir

        # Load keywords from CSV files
        print("INFO: Initializing FinancialSolicitationLabeler...")
        self.payment_app_keywords = self._load_keywords("payment-app-keywords.csv")
        self.crypto_keywords = self._load_keywords("crypto-keywords.csv")
        self.call_to_action_keywords = self._load_keywords("call-to-action-keywords.csv")

        # Define Regex patterns for common crypto addresses (can be expanded)
        # Simple Bitcoin P2PKH/P2SH pattern
        self.btc_pattern = re.compile(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b')
        # Simple Ethereum pattern
        self.eth_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')

        print(f"INFO: Loaded {len(self.payment_app_keywords)} payment app keywords.")
        print(f"INFO: Loaded {len(self.crypto_keywords)} crypto keywords.")
        print(f"INFO: Loaded {len(self.call_to_action_keywords)} call-to-action keywords.")


    def _load_keywords(self, filename: str) -> Set[str]:
        """
        Loads keywords from a given CSV filename in the input directory.
        Expects one keyword/phrase per row, first column. Converts to lowercase.
        """
        keywords = set()
        filepath = os.path.join(self.input_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip(): # Check for non-empty
                        keywords.add(row[0].strip().lower())
            print(f"INFO: Successfully loaded {len(keywords)} keywords from {filepath}")
        except FileNotFoundError:
            print(f"WARNING: Keyword file not found at {filepath}. No keywords loaded for this category.")
        except Exception as e:
            print(f"ERROR: Failed to load keywords from {filepath}: {e}")
        return keywords


    def _get_post_details(self, url: str) -> Optional[models.AppBskyFeedDefs.PostView]:
        """
        Fetches the full PostView object for a given Bluesky post URL.

        Uses get_post_thread for robustness in retrieving the PostView structure.

        Args:
            url: The URL of the Bluesky post

        Returns:
            A PostView object if successful, otherwise None.
        """
        try:
            # 1. Parse Handle and Record Key (rkey) from URL
            parts = url.split('/')
            # Basic validation of URL structure
            if len(parts) < 5 or parts[-2] != 'post':
                print(f"Error: Invalid post URL format: {url}")
                return None
            handle = parts[-3]
            rkey = parts[-1]

            # 2. Resolve Handle to DID
            try:
                did = did_from_handle(handle)
                if not did:
                    # Log if DID resolution fails for the handle
                    print(f"Error: Could not resolve DID for handle '{handle}'")
                    return None
            except Exception as resolve_e:
                # Log any exception during DID resolution
                print(f"Error resolving DID for handle '{handle}': {resolve_e}")
                return None

            # 3. Fetch Post Thread to get the PostView object
            # Construct the AT URI required by get_post_thread
            at_uri = f"at://{did}/app.bsky.feed.post/{rkey}"
            try:
                # Fetch thread with depth 0 to just get the main post view
                post_thread = self.client.get_post_thread(uri=at_uri, depth=0)

                # Check if the response structure contains the expected post view
                if (post_thread and
                        post_thread.thread and
                        isinstance(post_thread.thread, models.AppBskyFeedDefs.ThreadViewPost) and
                        post_thread.thread.post):
                    # Successfully found the PostView object
                    return post_thread.thread.post
                else:
                    # Log if the expected structure wasn't found in the response
                    print(f"Warning: Could not retrieve valid post view from thread for URI: {at_uri}")
                    return None
            except Exception as thread_e:
                # Log any exception during thread fetching
                print(f"Error fetching post thread for URI {at_uri}: {thread_e}")
                return None

        except Exception as e:
            # Catch-all for any unexpected errors during the process
            print(f"Error processing URL {url}: {e}")
            return None

    
    def _check_financial_solicitation(self, post_record: models.AppBskyFeedPost.Record) -> bool:
        """
        Checks post text for crypto addresses or keyword combinations
        indicative of potential financial solicitation.
        """
        post_text = getattr(post_record, 'text', None)
        if not post_text:
            return False # No text to analyze

        post_text_lower = post_text.lower() # Work with lowercase for keywords

        # --- Check 1: Crypto Address Pattern Match
        if self.btc_pattern.search(post_text) or self.eth_pattern.search(post_text):
            print("INFO: Crypto address pattern found.")
            return True # Finding an address is a strong signal

        # --- Check 2: Keyword Combination Match ---

        # Keywords indicating payment methods/platforms
        payment_keywords_found = any(k in post_text_lower for k in self.payment_app_keywords)
        crypto_keywords_found = any(k in post_text_lower for k in self.crypto_keywords)
        mentions_payment_method = payment_keywords_found or crypto_keywords_found

        # Keywords indicating Call to Action or Fundraising Context

        cta_keywords_found = any(k in post_text_lower for k in self.call_to_action_keywords)

        # For simplicity now, we just use CTA keywords from the list
        needs_help_signal = cta_keywords_found


        # Apply refined combination logic:
        # If a payment method/crypto term is mentioned AND there's a help signal
        if mentions_payment_method and needs_help_signal:
            print("INFO: Keyword combination (Payment/Crypto + CTA/Hashtag) found.")
            return True

        
        # --- Check 3: Payment Platform Patterns (Regex) ---
        cashapp_pattern = cashapp_pattern = re.compile(r'(?:cash[\s]?app)[:@ ]+[$]?[a-zA-Z0-9_-]+', re.IGNORECASE)
        paypalme_pattern = re.compile(r'paypal\.me/[a-zA-Z0-9_.-]+', re.IGNORECASE)
        kofi_pattern = re.compile(r'ko-fi\.com/[a-zA-Z0-9_.-]+', re.IGNORECASE)
        btc_address_pattern = re.compile(r'\bbc1[ac-hj-np-z02-9]{25,87}\b', re.IGNORECASE)
        venmo_pattern = re.compile(r'venmo[:@ ]+\$?[a-zA-Z0-9_-]+', re.IGNORECASE)
        venmo_link_pattern = re.compile(r'venmo\.com/u/[a-zA-Z0-9_-]+', re.IGNORECASE)

        if (cashapp_pattern.search(post_text) or
            paypalme_pattern.search(post_text) or
            kofi_pattern.search(post_text) or
            venmo_pattern.search(post_text) or
            venmo_link_pattern.search(post_text) or
            btc_address_pattern.search(post_text)):
            print("INFO: Payment platform pattern (CashTag/PayPal.Me/Ko-fi/Venmo) found.")
            return True

        return False # No suspicious patterns/combinations found
    
    def moderate_post(self, url: str) -> List[str]:
        """
        Applies the financial solicitation policy to the post.

        Args:
            url: The URL of the Bluesky post.

        Returns:
            A list containing the label if criteria met, else empty list.
        """
        labels_to_apply = set()

        # 1. Get Post Details
        post_details = self._get_post_details(url)
        if not post_details:
            return []

        # 2. Get the post record content
        post_record = getattr(post_details, 'record', None)
        if not post_record:
            # Log if needed, but proceed without text check if record missing
            return []

        # 3. Check for solicitation signals in the text
        if self._check_financial_solicitation(post_record):
            print(f"INFO: Applying label '{self.POTENTIAL_FINANCIAL_SOLICITATION}' to post {url}")
            labels_to_apply.add(self.POTENTIAL_FINANCIAL_SOLICITATION)

        return list(labels_to_apply)