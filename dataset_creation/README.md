# Dataset Curation – Failysis

This folder contains the scripts used to generate the dataset for **Failysis**. The dataset is constructed by analyzing Ethereum blocks and transactions, simulating their execution, and extracting structured failure information.

---

## File Overview

| File Name                | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| `analyze_block.py`       | Analyzes a range of Ethereum blocks to extract transactions for the dataset. |
| `analyze_transaction.py` | Simulates a single transaction using Tenderly and extracts failure details.  |
| `error_logging.py`       | Handles structured error detection, categorization, and logging.            |
| `ethereum_src.py`        | Retrieves and parses smart contract source code and metadata from Etherscan. |

---

## Tenderly API Setup

This project uses [Tenderly](https://tenderly.co/) to simulate Ethereum transactions and extract execution traces.

To use it, you must:

- Provide your **Tenderly API key**
- Set your **Tenderly account and project name** correctly in the simulation URL

In `analyze_transaction.py`, make sure the following lines are filled in correctly:

```python
TENDERLY_API_KEY = "your_api_key_here"

TENDERLY_SIMULATION_URL = "https://api.tenderly.co/api/v1/account/{ACCOUNT_NAME}/project/{PROJECT_NAME}/simulate"
```

Replace {ACCOUNT_NAME} and {PROJECT_NAME} with your actual Tenderly account and project name.
---


## Usage

### Run full dataset curation (all blocks)

```bash
python analyze_block.py --input "ethereum_failed_transactions\dune_results\all_hashes.parquet" --output "datasets/test.parquet" --count 20000 
```

This processes 20,000 transactions for thesis replication.


### Run single transaction

```bash
python analyze_transaction.py --tx_hash <TX_HASH>
```

Put in the actual transaction hash. 

---

## Output
The output is a Parquet file containing detailed information about each failed transaction.
Error logs are written to error.log in the working directory.


### Dataset Schema

| Attribute         | Description                                  |
|-------------------|----------------------------------------------|
| `hash`            | Transaction hash                             |
| `failure_reason`  | Short description of why the transaction failed |
| `block_number`    | Block number of the transaction              |
| `from_address`    | Sender’s Ethereum address                     |
| `to_address`      | Receiver’s Ethereum address                   |
| `tx_input`        | Input data sent with the transaction         |
| `gas`             | Gas used by the transaction                   |
| `gas_price`       | Gas price specified for the transaction      |
| `gas_limit`       | Maximum gas allowed                           |
| `value`           | Ether value transferred                       |
| `tx_index`        | Transaction’s position within its block      |
| `failure_message` | Error message from simulation                 |
| `failure_invariant` | Extracted condition that caused the failure |
| `tenderly_src`    | Whether Tenderly had source code access       |
| `etherscan_src`   | Whether Etherscan had source code access      |
| `failure_file`     | File path or source location of the failure   |
| `failure_function`| Name of function where failure occurred       |
| `failure_contract`| Contract address involved in failure          |
| `timestamp`       | Timestamp of the transaction                   |

---

## Troubleshooting
Error log: All errors encountered during processing are recorded in error.log.

API issues: Ensure your Tenderly API key and project/account names are correct.

