from concurrent.futures import ThreadPoolExecutor, as_completed
from analyze_transaction import fetch_transaction_info
import logging
import argparse
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import time
import os
from threading import Lock
import numpy as np
from error_logging import error_logger, listener
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed


write_lock = Lock()
BATCH_SIZE = 1000

file_path = r"Failysis\ethereum_failed_transactions\dune_results\all_hashes.parquet"


def read_parquet(file_name = "transactions.parquet"):
    df = pd.read_parquet(file_name)  # Load all columns
    for idx, row in df.iterrows():
        print(f"Row {idx}: {row.to_dict()}")

def write_to_file(dict_list, file_name="transactions.parquet"):
    EXPECTED_COLUMNS = [
        'hash', 'failure_reason', 'block_number', 'from_address', 'to_address',
        'tx_input', 'gas_used', 'gas_price', 'gas_limit', 'value', 'tx_index', 'failure_message', 'failure_invariant', 
        'tenderly_src', 'etherscan_src', 'failure_file', 'failure_function', 'failure_contract', 'timestamp'
    ]

    cleaned_rows = []
    for row in dict_list:
        if row is None:
            continue

        normalized = {col: row.get(col, None) for col in EXPECTED_COLUMNS}
        if normalized["value"] is not None:
            try:
                normalized["value"] = np.int64(normalized["value"])
            except Exception:
                normalized["value"] = np.int64(0)

        for bool_col in ["tenderly_src", "etherscan_src"]:
            val = row.get(bool_col, None)
            normalized[bool_col] = bool(val) if val is not None else None

        cleaned_rows.append(normalized)

    if not cleaned_rows:
        return  # nothing to write

    df = pd.DataFrame(cleaned_rows)
    table = pa.Table.from_pandas(df)
    # Use lock to prevent race conditions while writing
    if os.path.exists(file_name):
        existing_table = pq.read_table(file_name)
        combined_table = pa.concat_tables([existing_table, table])
        pq.write_table(combined_table, file_name)
    else:
        pq.write_table(table, file_name)

def setup_logger():
    logger = logging.getLogger("main_logger")
    if not logger.hasHandlers():
        handler = logging.FileHandler("main.log")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

def process_transactions(hashes, batch_size, output_file, general_logger):
    batch = []
    processed_hashes = set()
    to_retry = []

    def process_row(tx_hash):
        try:
            res = fetch_transaction_info(tx_hash)
            if res is None:
                error_logger.error(f"Tenderly returned None for hash {tx_hash}")
                return None
            return res
        except Exception as e:
            error_logger.error(f"Exception processing hash {tx_hash}: {e}")
            return None

    total = len(hashes)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_row, h): h for h in hashes}
        # Wrap as_completed with tqdm for progress bar
        for idx, future in enumerate(tqdm(as_completed(futures), total=total, unit="tx"), 1):
            tx_hash = futures[future]
            try:
                result = future.result()
                if result:
                    batch.append(result)
                    processed_hashes.add(tx_hash)
                else:
                    to_retry.append(tx_hash)
            except Exception as e:
                error_logger.error(f"Error processing future for hash {tx_hash}: {e}")
                to_retry.append(tx_hash)

            if idx % batch_size == 0:
                with write_lock:
                    write_to_file(batch, file_name=output_file)
                general_logger.info(f"Written batch of {batch_size} transactions to {output_file}")
                batch.clear()

        # Write any remaining batch
        if batch:
            with write_lock:
                write_to_file(batch, file_name=output_file)
            general_logger.info(f"Written final batch of {len(batch)} transactions to {output_file}")

    return to_retry

def retry_failed(hashes, batch_size, output_file, general_logger, max_retries=3):
    retries = 0
    to_retry = list(hashes)
    while retries < max_retries and to_retry:
        general_logger.info(f"Retry attempt {retries + 1} for {len(to_retry)} failed hashes.")
        to_retry = process_transactions(to_retry, batch_size, output_file, general_logger)
        retries += 1
    if to_retry:
        error_logger.error(f"Following hashes failed after {max_retries} retries: {to_retry}")

def get_rand_trans(transaction_nr, input_file, output_file):
    general_logger = setup_logger()
    start_time = time.time()
    df = pd.read_parquet(input_file)
    random_hashes = df.sample(n=transaction_nr, random_state=30)["hash"]

    to_retry = process_transactions(random_hashes, BATCH_SIZE, output_file, general_logger)
    if to_retry:
        retry_failed(to_retry, BATCH_SIZE, output_file, general_logger)

    general_logger.info(f"Total execution time: {time.time() - start_time:.4f} seconds")

def get_rand_trans_multi(transaction_nr, input_file, output_file):
    # for SmartBERT:
    #rn_state = 36
    #for my actual thesis:
    rn_state = 15
    general_logger = setup_logger()
    general_logger.info(f"Start running for {transaction_nr} transactions with random state: {rn_state}")
    
    start_time = time.time()
    df = pd.read_parquet(input_file)
    random_hashes = df.sample(n=transaction_nr, random_state=rn_state)["hash"]
    remaining_hashes = random_hashes.iloc[94000:]

    to_retry = process_transactions(remaining_hashes, BATCH_SIZE, output_file, general_logger)
    if to_retry:
        retry_failed(to_retry, BATCH_SIZE, output_file, general_logger)

    general_logger.info(f"Total execution time: {time.time() - start_time:.4f} seconds")

def run_all_multi(input_file, output_file):
    general_logger = setup_logger()
    start_time = time.time()
    df = pd.read_parquet(input_file)
    all_hashes = df["hash"]

    to_retry = process_transactions(all_hashes, BATCH_SIZE, output_file, general_logger)
    if to_retry:
        retry_failed(to_retry, BATCH_SIZE, output_file, general_logger)

    general_logger.info(f"Total execution time: {time.time() - start_time:.4f} seconds")

def main():
    parser = argparse.ArgumentParser(description="Ethereum transaction processor")
    
    parser.add_argument("--input", type=str, default=r"Failysis\ethereum_failed_transactions\dune_results\all_hashes.parquet",
                        help="Path to input parquet file")
    parser.add_argument("--output", type=str, default="SmartBERT.parquet",
                        help="Path to output parquet file")
    parser.add_argument("--count", type=int, default=20000,
                        help="Number of transactions to process (ignored in --all mode)")
    parser.add_argument("--all", action="store_true",
                        help="Process all transactions instead of a random sample")

    args = parser.parse_args()

    listener.start()

    if args.all:
        run_all_multi(args.input, args.output)
    else:
        get_rand_trans_multi(args.count, args.input, args.output)

    listener.stop()

if __name__ == "__main__":
    main()