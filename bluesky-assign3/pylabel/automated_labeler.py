import os
import csv
from typing import List, Optional, Set
from urllib.parse import urlparse
import io

import requests
from PIL import Image
from atproto import Client, models
from perception.hashers import PHash
from .label import did_from_handle
import re
import base64


# Constants from the assignment
T_AND_S_LABEL = "t-and-s"
DOG_LABEL = "dog"
HAMMING_DISTANCE_THRESHOLD = 17 


class AutomatedLabeler:
    """Automated labeler implementation"""

    def __init__(self, client: Client, input_dir: str):
        """
        Initialize the labeler.

        Args:
            client: ATProto client instance.
            input_dir: Directory containing input data files (CSVs, images).
        """
        self.client = client
        self.input_dir = input_dir
        self.phash = PHash() # Initialize PHash hasher

        # --- Milestone 2 Data ---
        self.ts_words = self._load_ts_words()
        self.ts_domains = self._load_ts_domains()

        # --- Milestone 3 Data ---
        self.news_domains = self._load_news_domains()

        # --- Milestone 4 Data ---
        self.dog_hashes = self._load_dog_hashes()

    # --- Data Loading Helpers ---

    def _load_ts_words(self) -> Set[str]:
        """Loads T&S words from the CSV, converting to lowercase."""
        words = set()
        try:
            filepath = os.path.join(self.input_dir, "t-and-s-words.csv")
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row: 
                        words.add(row[0].strip().lower())
        except FileNotFoundError:
            print(f"Warning: {filepath} not found.")
        except Exception as e:
            print(f"Error loading T&S words: {e}")
        return words

    def _load_ts_domains(self) -> Set[str]:
        """Loads T&S domains from the CSV."""
        domains = set()
        try:
            filepath = os.path.join(self.input_dir, "t-and-s-domains.csv")
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                     if row: 
                        domains.add(row[0].strip().lower())
        except FileNotFoundError:
            print(f"Warning: {filepath} not found.")
        except Exception as e:
            print(f"Error loading T&S domains: {e}")
        return domains

    def _load_news_domains(self) -> dict[str, str]:
        """Loads news domains and their corresponding labels from the CSV."""
        domain_to_label = {}
        try:
            filepath = os.path.join(self.input_dir, "news-domains.csv")
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2: 
                        domain = row[0].strip().lower()
                        label = row[1].strip()
                        domain_to_label[domain] = label
        except FileNotFoundError:
            print(f"Warning: {filepath} not found.")
        except Exception as e:
            print(f"Error loading news domains: {e}")
        return domain_to_label

    def _load_dog_hashes(self) -> Set[str]:
        """Loads dog images, computes their PHashes, and stores them."""
        hashes = set()
        dog_image_dir = os.path.join(self.input_dir, "dog-list-images")
        if not os.path.isdir(dog_image_dir):
             print(f"Warning: Dog image directory not found at {dog_image_dir}")
             return hashes

        try:
            for filename in os.listdir(dog_image_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    filepath = os.path.join(dog_image_dir, filename)
                    try:
                        img_hash = self.phash.compute(filepath)
                        if img_hash:
                           hashes.add(img_hash)
                    except Exception as e:
                        print(f"Error processing dog image {filename}: {e}")
        except Exception as e:
            print(f"Error listing dog images directory: {e}")
        return hashes

    # --- Post Fetching Helper ---

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



    # --- Milestone Logic Helpers ---

    def _check_ts_content(self, post_text: str) -> bool:
        """Checks if post text contains T&S words or domains (case-insensitive)."""
        text_lower = post_text.lower()
        # Check for words
        if any(word in text_lower for word in self.ts_words):
            return True
        # Check for domains (simple substring check, might need refinement for accuracy)
        if any(domain in text_lower for domain in self.ts_domains):
             return True
        return False

    def _check_news_links(self, post: models.AppBskyFeedDefs.PostView) -> Set[str]:
        """
        Checks for links to known news domains within the post's facets,
        external link embeds, or raw text content.

        Args:
            post: The PostView object fetched from Bluesky.

        Returns:
            A set of string labels corresponding to the matched news sources.
        """
        found_labels = set()
        processed_urls = set() # Keep track of URLs already processed to avoid double-checking

        # --- Helper function to process a URL ---
        def process_url(url_string: str):
            if not url_string or url_string in processed_urls:
                return # Skip if empty or already processed
            processed_urls.add(url_string)
            try:
                domain = urlparse(url_string).netloc.lower()
                # Remove 'www.' if present for consistent matching
                if domain.startswith('www.'):
                    domain = domain[4:]

                # Check against known news domains
                if domain in self.news_domains:
                    matched_label = self.news_domains[domain]
                    # Add label only once per source per post
                    found_labels.add(matched_label)
            except Exception as e:
                # Log errors parsing specific URLs if they occur
                print(f"Warning: Could not parse URL '{url_string}': {e}")
        # --- End Helper function ---


        # 1. Check Facets (Links within text body)
        post_record = getattr(post, 'record', None)
        if post_record and hasattr(post_record, 'facets') and post_record.facets:
            for facet in post_record.facets:
                if facet.features:
                    for feature in facet.features:
                        if isinstance(feature, models.AppBskyRichtextFacet.Link):
                            process_url(getattr(feature, 'uri', None))


        # 2. Check Embeds (External Link Cards)
        post_embed = getattr(post, 'embed', None)
        if isinstance(post_embed, models.AppBskyEmbedExternal.Main):
            external_data = getattr(post_embed, 'external', None)
            if external_data:
                process_url(getattr(external_data, 'uri', None))# Consider adding checks for other embed types (e.g., Record with External) if needed


        # 3. Check Raw Text for URLs
        if post_record and hasattr(post_record, 'text'):
            post_text = getattr(post_record, 'text', '')
            # Simple regex for http/https URLs
            url_pattern = r'https?://[^\s/$.?#].[^\s]*'
            potential_urls = re.findall(url_pattern, post_text)
            for url_text in potential_urls:
                process_url(url_text)


        return found_labels

    def _check_dog_image(self, post: models.AppBskyFeedDefs.PostView) -> bool:
        """
        Checks if any image embedded in the post has a perceptual hash
        similar (within HAMMING_DISTANCE_THRESHOLD) to a known dog image hash.

        Args:
            post: The PostView object fetched from Bluesky.

        Returns:
            True if a matching dog image is found, False otherwise.
        """
        post_embed = getattr(post, 'embed', None)

        # 1. Check if the embed is the correct Image View type
        if not isinstance(post_embed, models.AppBskyEmbedImages.View):
            return False # Not an image embed view

        # 2. Check if the embed view actually contains images
        if not hasattr(post_embed, 'images') or not post_embed.images:
            return False # Image embed view exists but has no images list

        # 3. Process each image in the embed
        for i, img_data in enumerate(post_embed.images):
            # Attempt to get a usable image URL (fullsize preferred, fallback to thumb)
            img_url = getattr(img_data, 'fullsize', getattr(img_data, 'thumb', None))
            if not img_url:
                continue # Skip to the next image if no URL

            try:
                # 4. Download and hash the image from the post
                response = requests.get(img_url, timeout=20)
                response.raise_for_status() # Check for download errors
                image_bytes = response.content
                pil_image = Image.open(io.BytesIO(image_bytes))
                post_img_hash_str = self.phash.compute(pil_image)

                if not post_img_hash_str:
                    continue # Skip to next image if hashing fails

                # 5. Convert post image hash string (assume Base64) to integer
                try:
                    post_img_hash_bytes = base64.b64decode(post_img_hash_str)
                    post_img_hash_int = int.from_bytes(post_img_hash_bytes, 'big')
                except (base64.binascii.Error, TypeError) as e:
                    print(f"Warning: Error converting computed hash '{post_img_hash_str}' to integer: {e}")
                    continue 

                # 6. Compare with known dog hashes
                for dog_hash_str in self.dog_hashes:
                    # Convert known dog hash string (assume Base64) to integer
                    try:
                        dog_hash_bytes = base64.b64decode(dog_hash_str)
                        dog_hash_int = int.from_bytes(dog_hash_bytes, 'big')
                    except (base64.binascii.Error, TypeError) as e:
                        # This indicates a potential issue during loading of known hashes
                        print(f"Warning: Error converting known dog hash '{dog_hash_str}' to integer: {e}")
                        continue # Skip this known hash comparison

                    # Calculate Hamming Distance
                    xor_result = post_img_hash_int ^ dog_hash_int
                    distance = bin(xor_result).count('1')

                    # 7. Check if distance is within the defined threshold
                    if distance <= HAMMING_DISTANCE_THRESHOLD:
                        # Match found!
                        return True # Return True immediately, no need to check further

            except requests.exceptions.RequestException as e:
                print(f"Warning: Error downloading image {i} from {img_url}: {e}")
            except Image.UnidentifiedImageError:
                print(f"Warning: Could not identify image format for image {i} from {img_url}")
            except Exception as e:
                # Catch any other unexpected errors during image processing
                print(f"Warning: Unexpected error processing image {i} from {img_url}: {e}")

        # If the loop finishes without finding any match
        return False

    # --- Main Moderation Function ---

    def moderate_post(self, url: str) -> List[str]:
        """
        Apply moderation to the post specified by the given url.
        Checks for T&S content, news links, and dog images.

        Args:
            url: The URL of the Bluesky post.

        Returns:
            A list of labels to be applied to the post.
        """
        labels_to_apply = set() # Use a set to automatically handle duplicates

        # 1. Get Post Details
        post_details = self._get_post_details(url)
        if not post_details or not post_details.record or not hasattr(post_details.record, 'text'):

             if post_details and self._check_dog_image(post_details): # Check dog image even if text fails
                 labels_to_apply.add(DOG_LABEL)
             if not post_details:
                 print(f"Failed to fetch post details for {url}. Cannot moderate fully.")
                 return [] # Return empty list if post fetch fails completely
             else:
                 # If we have post_details but no text, proceed with image check only
                  post_text = "" # Assign empty string if text is missing
             # Proceed only with image check if text is unavailable
        else:
            post_text = post_details.record.text

            # 2. Milestone 2: Check T&S Words/Domains
            if self._check_ts_content(post_text):
                labels_to_apply.add(T_AND_S_LABEL)

            # 3. Milestone 3: Check News Links
            news_labels = self._check_news_links(post_details)
            labels_to_apply.update(news_labels) # Add all unique news labels found

            # 4. Milestone 4: Check Dog Images
            if self._check_dog_image(post_details):
                labels_to_apply.add(DOG_LABEL)

        return list(labels_to_apply)