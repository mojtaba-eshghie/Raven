from analyze_transaction import fetch_transaction_info

import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa

file_path = r"Failysis\ethereum_failed_transactions\dune_results\all_hashes.parquet"

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

run_all_invariants(file_path)