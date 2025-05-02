"""Script for testing the automated labeler"""

import argparse
import json
import os
import time
import pandas as pd
from atproto import Client
from dotenv import load_dotenv
from statistics import median

from pylabel import AutomatedLabeler, label_post, did_from_handle
from pylabel.policy_proposal_labeler import FinancialSolicitationLabeler

load_dotenv(override=True)
USERNAME = os.getenv("USERNAME")
PW = os.getenv("PW")

def main():
    """
    Main function for the test script
    """
    client = Client()
    labeler_client = None
    client.login(USERNAME, PW)
    did = did_from_handle(USERNAME)

    parser = argparse.ArgumentParser()
    parser.add_argument("labeler_inputs_dir", type=str)
    parser.add_argument("input_urls", type=str)
    parser.add_argument("--emit_labels", action="store_true")
    args = parser.parse_args()

    if args.emit_labels:
        labeler_client = client.with_proxy("atproto_labeler", did)

    # labeler = AutomatedLabeler(client, args.labeler_inputs_dir)
    labeler = FinancialSolicitationLabeler(client, args.labeler_inputs_dir)
    urls = pd.read_csv(args.input_urls)
    num_correct, total = 0, urls.shape[0]

    processing_times = [] # Initialize list to store durations
    print(f"\nStarting moderation test for {args.input_urls}...")

    for _index, row in urls.iterrows():
        url, expected_labels = row["URL"], json.loads(row["Labels"])

        # --- Time Measurement Start ---
        start_time = time.perf_counter() # Use perf_counter for high resolution
        labels = labeler.moderate_post(url)
        end_time = time.perf_counter()
        processing_time = end_time - start_time
        processing_times.append(processing_time)
        print(f"Processing time for {url}: {processing_time:.4f} seconds")
        # --- Time Measurement End ---

        if sorted(labels) == sorted(expected_labels):
            num_correct += 1
        else:
            print(f"For {url}, labeler produced {labels}, expected {expected_labels}")
        if args.emit_labels and (len(labels) > 0):
            label_post(client, labeler_client, url, labels)
    print(f"The labeler produced {num_correct} correct labels assignments out of {total}")
    print(f"Overall ratio of correct label assignments {num_correct/total}")
    # --- Analysis After Loop ---
    print(f"\n--- Performance Summary ---")
    if processing_times: # Avoid errors if all posts failed
        avg_time = sum(processing_times) / len(processing_times)
        print(f"Average processing time: {avg_time:.4f} seconds")
        print(f"Median processing time: {median(processing_times):.4f} seconds")
        print(f"Min processing time: {min(processing_times):.4f} seconds")
        print(f"Max processing time: {max(processing_times):.4f} seconds")


if __name__ == "__main__":
    main()
