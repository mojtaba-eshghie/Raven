from concurrent.futures import ThreadPoolExecutor, as_completed
from analyze_transaction import fetch_transaction_info
import logging

import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import time

file_path = r"ethereum_failed_transactions\dune_results\all_hashes.parquet"

def get_invariant(hash):
    result = fetch_transaction_info(hash)
    invariant = result.get("failure_invariant", "")
    message = result.get("failure_message", "")
    reason = result.get("failure_reason", "")
    if "out of gas" in message or "out of gas" in reason:
        return "out of gas"
    if invariant is None or invariant == []:
        return "no reason found"
    return invariant
  

def run_all_invariants(file_name):
    print("read file")
    df = pd.read_parquet(file_name)
    if 'invariant' not in df.columns:
        df['invariant'] = None

    if 'hash' not in df.columns:
        raise ValueError(f"Column '{hash}' does not exist.")

    for index, row in df.iterrows():
        if row['invariant'] != None:
            continue
        invariant = get_invariant(row['hash'])
        print(invariant)
        df.at[index, 'invariant'] = invariant
    
    table = pa.Table.from_pandas(df)
    # Save the result back to the same Parquet file
    pq.write_table(table, file_name)  # This will overwrite the existing file

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
        res = get_invariant(row)
        logging.info(f"hash: {row}, invariant: {res}")
    
    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"Total execution time: {total_time:.4f} seconds")

def get_rand_trans_multi(transaction_nr, input_file, output_file):
    logging.basicConfig(
        filename=output_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    start_time = time.time()
    
    print("read file")
    df = pd.read_parquet(input_file)
    random_rows = df.sample(n=transaction_nr, random_state=30)  # Set random_state for reproducibility
    
    cols = random_rows["hash"]

    def process_row(row):
        res = get_invariant(row)
        logging.info(f"hash: {row}, invariant: {res}")
    
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_row, row) for row in cols]
        for future in as_completed(futures):
            pass
    
    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"Total execution time: {total_time:.4f} seconds")


#get_rand_trans(10000, file_path, "check_correctness_500.log")
#get_rand_trans_multi(100000, file_path, "test_100000.log")
