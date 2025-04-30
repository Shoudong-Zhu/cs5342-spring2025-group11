# Assignment 3: Automated Bluesky Labeler

**Course:** CS 5342 Trust and Safety: Platforms, Policies, Products (Spring 2025)
**Team:** Team 11

## Overview

This project involves implementing an automated moderation service, known as a "labeler," for the Bluesky social network as part of Assignment 3. Bluesky labelers allow for customizable, stackable moderation by attaching categorical labels to posts or accounts based on defined criteria. Users can then subscribe to these labelers and configure how labeled content is displayed (e.g., hidden, shown with a warning).

The assignment consists of two main parts:

1.  **Part I:** Implementing labeler functionalities based on predefined requirements:
    * Labeling posts containing specific Trust & Safety (T&S) related keywords or domains.
    * Labeling posts with the source of linked news articles (Source Citation).
    * Labeling posts containing images that perceptually match known images of dogs (Image Hashing).
2.  **Part II:** Designing, implementing, testing, and evaluating a labeler for a custom moderation policy. Our chosen policy targets **Potential Financial Solicitation**.

This README details the project structure, setup instructions, implementation logic for both parts, testing methodology, results, and ethical considerations.

## Project Structure

The project is organized as follows:
```text
bluesky-assign3/
|-- pylabel/            # Core labeler logic Python package
|   |-- __init__.py     # Makes 'pylabel' a package
|   |-- automated_labeler.py  # Logic for Part I milestones
|   |-- policy_proposal_labeler.py # Logic for Part II (Financial Solicitation)
|   \-- label.py          # Helper functions (DID lookup, emitting labels via API)
|-- labeler-inputs/     # Input data files used by labelers
|   |-- dog-list-images/  # Images used for Part I dog hashing
|   |-- placeholder-ncii-images/ # Placeholder images (NOT USED IN FINAL PART II)
|   |-- news-domains.csv
|   |-- t-and-s-domains.csv
|   |-- t-and-s-words.csv
|   |-- payment-app-keywords.csv # Part II data
|   |-- crypto-keywords.csv      # Part II data
|   \-- call-to-action-keywords.csv # Part II data
|-- test-data/          # Test case files (URLs & expected labels)
|   |-- input-posts-cite.csv
|   |-- input-posts-dogs.csv
|   |-- input-posts-t-and-s.csv
|   \-- input-posts-financial-policy.csv # Part II test data
|-- .env                # Stores Bluesky API credentials (USERNAME, PW) - Not committed
|-- .env-TEMPLATE       # Template for .env file
|-- .gitignore          # Specifies files to ignore for Git (e.g., .env, __pycache__)
|-- test_labeler.py     # Main script for testing labeler logic against test data
|-- README.md           # This file
\-- requirements.txt    # List of Python dependencies
```

## Setup Instructions

1.  **Prerequisites:**
    * Python 3.x installed.
    * `pip` (Python package installer).

2.  **Clone Repository:** (If applicable)
    ```bash
    git clone git@github.com:Shoudong-Zhu/cs5342-spring2025-group11.git
    cd bluesky-assign3
    ```

3.  **Install Dependencies:** It's recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

4.  **Environment Variables:**
    * Copy the `.env-TEMPLATE` file to a new file named `.env`.
    * Edit the `.env` file and add your Bluesky handle (username) and an app password:
        ```dotenv
        USERNAME=your-bluesky-handle.bsky.social
        PW=xxxx-xxxx-xxxx-xxxx
        ```
    * **Important:** Ensure the `.env` file is listed in your `.gitignore` file to avoid committing credentials.

## Part I Implementation (`pylabel/automated_labeler.py`)

The `AutomatedLabeler` class implements the logic for the three predefined milestones.

* **Core Architecture:** Uses helper methods (`_load_*`, `_check_*`, `_get_post_details`) called by the main `moderate_post` function. Loads necessary data (keywords, domains, image hashes) during initialization.
* **Post Fetching (`_get_post_details`):** After initial debugging showed issues with `client.get_post`, this function was updated to use `client.get_post_thread(uri=at_uri, depth=0)` which reliably returned the necessary `PostView` object containing record and embed details. It handles URL parsing and handle-to-DID resolution.

### Milestone 2: T&S Keywords/Domains
* **Logic (`_check_ts_content`):** Performs case-insensitive substring checks of the post text against pre-loaded sets of T&S keywords and domains. Returns `True` if any match is found.
* **Label:** `"t-and-s"`

### Milestone 3: News Source Citation
* **Logic (`_check_news_links`):** Identifies news domains from URLs found in the post.
    * *Challenge:* Initial implementation checking only facets/embeds failed as test posts lacked these.
    * *Solution:* Expanded logic to also use `re.findall` to extract plain URLs from the post text.
    * Parses domains from URLs found in facets, external embeds, OR raw text. Normalizes domains (lowercase, remove `www.`) and compares against a loaded dictionary (`news-domains.csv`) to determine the appropriate label (e.g., 'cnn', 'bbc'). Returns a set of unique labels found.
* **Labels:** Dynamically determined based on `news-domains.csv` (e.g., `"cnn"`, `"bbc"`, `"nyt"`, `"wapo"`, `"fox"`, `"reuters"`, `"ap"`)

### Milestone 4: Dog Image Labeler
* **Logic (`_load_dog_hashes`, `_check_dog_image`):** Identifies posts containing images perceptually similar to known dog images.
    * Uses `perception.hashers.PHash` to generate perceptual hashes.
    * `_load_dog_hashes`: Generates and stores Base64-encoded PHash strings for reference dog images.
    * `_check_dog_image`:
        * *Challenge 1:* Embed type check initially failed (`Main` vs `View`). *Fix:* Changed check to `isinstance(post_embed, models.AppBskyEmbedImages.View)`.
        * *Challenge 2:* `PHash` object lacked a built-in distance method. *Fix:* Implemented manual Hamming distance calculation: Decode Base64 hashes to bytes, convert bytes to integers, compute XOR (`^`), count set bits (`bin(...).count('1')`).
        * Compares the hash of each image in the post embed against known dog hashes.
        * Returns `True` if Hamming distance <= `HAMMING_DISTANCE_THRESHOLD` (set to 17).
* **Label:** `"dog"`

## Part II Implementation: Potential Financial Solicitation Labeler (`pylabel/policy_proposal_labeler.py`)

### Policy Goal & Motivation
* **Initial Idea (Assignment 2):** Implement NCII detection policy.
* **Challenge:** Difficulty creating safe/ethical test data and evaluating NCII detection accurately within assignment constraints.
* **Pivot:** Adopted the "Potential Financial Solicitation" policy suggested in the assignment description, focusing on text analysis.
* **Goal:** Detect posts that *might* be soliciting financial information (scams, requests, fundraising) without making definitive judgments. Apply the label `"potential-financial-solicitation"`.

### Implementation (`FinancialSolicitationLabeler`)
* **Data:** Loads keywords from `payment-app-keywords.csv`, `crypto-keywords.csv`, and `call-to-action-keywords.csv`.
* **Core Logic (`_check_financial_solicitation`):** Analyzes post text using multiple signals:
    1.  **Crypto Addresses:** Uses `re.search` with compiled regex patterns for common BTC and ETH address formats. Returns `True` if found (strong signal).
    2.  **Payment Platform Patterns:** Uses `re.search` with compiled regex patterns for common identifiers like `$CashTag`, `paypal.me/...`, `ko-fi.com/...`, `venmo.com/u/...`, `venmo: ...`. Returns `True` if found (considered a strong signal).
    3.  **Keyword Combination:** If no patterns match, checks for the co-occurrence of:
        * At least one keyword from the combined payment app/crypto lists.
        * AND at least one keyword from the call-to-action list.
        * Returns `True` if this combination is found.
* **`moderate_post`:** Fetches the post, extracts the text record, calls `_check_financial_solicitation`, and applies the label if the check returns `True`.

### Challenges & Iteration
* Simple keyword logic initially missed many real-world solicitation examples.
* Required significant expansion of keyword lists (payment variations, nuanced CTAs).
* Introduced regex for platform-specific patterns (e.g., `$CashTag`) for better signal strength.
* Iteratively refined the combination logic based on testing.
* Balancing detection of scams/requests vs. legitimate fundraising/mutual aid remains a challenge; the current labeler flags both as "potential" solicitation.

### Ethical Considerations
* The label `"potential-financial-solicitation"` is intentionally non-definitive, acknowledging the difficulty in distinguishing intent (scam vs. aid vs. joke).
* Keyword selection was done carefully, but bias is possible. Overly broad keywords could lead to false positives.
* The labeler might incorrectly flag legitimate mutual aid or fundraising requests. Transparency about this limitation is important. Users subscribing to the labeler should understand it flags *potential* signals, not confirmed scams.
* No sensitive or harmful data was used in development or testing.

## Testing and Evaluation

* **Framework:** Used the provided `test_labeler.py` script, adapted for each labeler class and test data file. The script compares the labeler's output list against an expected list from a CSV and reports accuracy.
* **Part I Evaluation:**
    * Tested against provided CSVs (`input-posts-t-and-s.csv`, `input-posts-cite.csv`, `input-posts-dogs.csv`).
    * Accuracy Achieved:
        * T&S Keywords/Domains: 100%
        * News Source Citation: 100%
        * Dog Image Labeler: 100% with Hamming Distance Threshold = 10.
* **Part II Evaluation:**
    * **Data Collection:** Manually collected/created Bluesky post URLs representing various scenarios (clear solicitation, crypto addresses, legitimate aid, non-solicitation discussion) and stored them in `test-data/input-posts-financial-policy.csv` with manually assigned expected labels (`["potential-financial-solicitation"]` or `[]`).
    * **Metrics:** Calculated Accuracy. Precision and Recall were also considered during development to tune keywords/logic (Precision: % of flagged posts that were actual solicitation; Recall: % of actual solicitation posts that were flagged).
    * **Results:** 86% accuracy.
* **Performance:** API calls (`get_post_thread`) were the primary performance factor. Local processing (text checks, hashing, comparisons) was generally fast.

## How to Run Tests

1.  Ensure all setup steps (dependencies, `.env` file) are complete.
2.  Navigate to the `bluesky-assign3` root directory in your terminal.
3.  Activate your virtual environment (`source venv/bin/activate` or `venv\Scripts\activate`).
4.  Run the tests using `test_labeler.py`, providing the path to the input data directory and the specific test CSV file.

    ```bash
    # Example: Test Part I - T&S Keywords
    python test_labeler.py labeler-inputs test-data/input-posts-t-and-s.csv

    # Example: Test Part I - Citations
    python test_labeler.py labeler-inputs test-data/input-posts-cite.csv

    # Example: Test Part I - Dogs
    python test_labeler.py labeler-inputs test-data/input-posts-dogs.csv

    # Example: Test Part II - Financial Solicitation
    python test_labeler.py labeler-inputs test-data/input-posts-financial-policy.csv
    ```


## Future Work

* **Part II Refinements:**
    * Expand keyword lists and regex patterns for financial solicitation detection.
    * Explore more advanced NLP techniques (e.g., sentiment analysis, entity recognition) to better understand context and potentially differentiate scams from aid requests.
    * Incorporate account-level signals (account age, follower/following count, profile description) as additional features.
    * Implement rate limiting or caching for external API calls if used (e.g., fact-checking APIs).
* **General:**
    * Add more comprehensive unit tests for helper functions.
    * Explore deploying the labeler as a live service (following Bluesky guidelines).

