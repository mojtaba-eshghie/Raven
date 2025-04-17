from concurrent.futures import ThreadPoolExecutor, as_completed
from analyze_transaction import fetch_transaction_info
import logging

import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import time
import os

file_path = r"Failysis\ethereum_failed_transactions\dune_results\all_hashes.parquet"

import numpy as np
def read_parquet(file_name = "transactions.parquet"):
    df = pd.read_parquet(file_name)  # Load all columns
    for idx, row in df.iterrows():
        print(f"Row {idx}: {row.to_dict()}")

def write_to_file(dict_list, file_name="transactions.parquet"):
    EXPECTED_COLUMNS = [
        'hash', 'failure_reason', 'block_number', 'from_address', 'to_address', 
        'tx_input', 'gas', 'gas_price', 'gas_limit', 'value', 'tx_index', 'failure_message', 'failure_invariant'
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

        cleaned_rows.append(normalized)

    if not cleaned_rows:
        return  # nothing to write

    df = pd.DataFrame(cleaned_rows)
    table = pa.Table.from_pandas(df)

    if os.path.exists(file_name):
        existing_table = pq.read_table(file_name)
        combined_table = pa.concat_tables([existing_table, table])
        pq.write_table(combined_table, file_name)
    else:
        pq.write_table(table, file_name)

def get_rand_trans(transaction_nr, input_file, output_file):
    logging.basicConfig(
        filename=output_file, 
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    start_time = time.time()
    
    print("read file")
    df = pd.read_parquet(input_file)
    random_rows = df.sample(n=transaction_nr, random_state=30)  # Set random_state for reproducibility
    # first state was 42
    
    cols = random_rows["hash"]
    
    for row in cols:
        res = fetch_transaction_info(row)
        logging.info(f"hash: {row}, invariant: {res.get('failure_invariant')}")
    
    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"Total execution time: {total_time:.4f} seconds")


def get_rand_trans_multi(transaction_nr, input_file, output_file):
    general_logger = logging.getLogger("main_logger")
    if not general_logger.hasHandlers():
        handler = logging.FileHandler(output_file)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        general_logger.addHandler(handler)
        general_logger.setLevel(logging.INFO)
    start_time = time.time()
    df = pd.read_parquet(input_file)
    random_rows = df.sample(n=transaction_nr, random_state=30)  # Set random_state for reproducibility    
    cols = random_rows["hash"]
    batch = []
    BATCH_SIZE = 1000

    def process_row(row):
        res = fetch_transaction_info(row)
        general_logger.info(f"hash: {row}, invariant: {res.get('failure_invariant')}")
        return res
    
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_row, row) for row in cols]
        for idx, future in enumerate(as_completed(futures), 1):
            result = future.result()
            batch.append(result)
            if idx % BATCH_SIZE == 0:
                write_to_file(batch)
                general_logger.info("Written to file")
                batch.clear()
        if batch:
            write_to_file(batch)

    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"Total execution time: {total_time:.4f} seconds")

def run_all_mutli(input_file, output_file):
    general_logger = logging.getLogger("main_logger")
    if not general_logger.hasHandlers():
        handler = logging.FileHandler(output_file)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        general_logger.addHandler(handler)
        general_logger.setLevel(logging.INFO)
    start_time = time.time()
    df = pd.read_parquet(input_file)
    cols = df["hash"]
    batch = []
    BATCH_SIZE = 1000

    def process_row(row):
        try:
            res = fetch_transaction_info(row)
            general_logger.info(f"hash: {row}, invariant: {res.get('failure_invariant')}")
            return res
        except Exception as e:
            general_logger.error(f"Exception in row {row}: {str(e)}")
            return None
    
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_row, row) for row in cols]
        for idx, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
                if result:
                    batch.append(result)
            except Exception as e:
                general_logger.error(f"Error processing future at index {idx}: {e}")
            if idx % BATCH_SIZE == 0:
                write_to_file(batch, file_name = "transactions_CORRECT.parquet")
                general_logger.info("Written to file")
                batch.clear()
        if batch:
            write_to_file(batch, file_name = "transactions_CORRECT.parquet")
        
    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"Total execution time: {total_time:.4f} seconds")

#get_rand_trans(10000, file_path, "check_correctness_500.log")
#get_rand_trans_multi(1000000, file_path, "main.log")

run_all_mutli(file_path, "error_test.log")