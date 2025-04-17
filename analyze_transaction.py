import requests
import sys
import json
import argparse
import time

# API Endpoints and Keys (Consider storing sensitive keys securely using environment variables)
#TENDERLY_SIMULATION_URL = "https://api.tenderly.co/api/v1/account/Melissa194/project/project/simulate"
TENDERLY_PUBLIC_TX_URL = "https://api.tenderly.co/api/v1/public-contract/1/tx/"
TENDERLY_SIMULATION_URL = "https://api.tenderly.co/api/v1/account/Melissa200/project/project/simulate"
#TENDERLY_API_KEY = "QBaUP1mgKshN32lxAUgaGxkksjBXVoo8"
TENDERLY_API_KEY = "YjWv8sRGMjsn7nWjM36rMIF9gBJRNoqK"
MAX_RETRIES = 20
INITIAL_RETRY_DELAY = 2
BACKOFF_MULTIPLIER = 2

import logging

# Set up a dedicated error logger
error_logger = logging.getLogger("error_logger")
if not error_logger.hasHandlers():
    handler = logging.FileHandler("errors.log")
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    error_logger.addHandler(handler)
    error_logger.setLevel(logging.ERROR)

def safe_request(url, method="GET", headers=None, payload=None, hash = None):
    """Helper function to handle API requests with exponential backoff."""
    retry_delay = INITIAL_RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers)
        else:
            response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        time.sleep(retry_delay)
        retry_delay *= BACKOFF_MULTIPLIER
    error_logger.error(f"hash: {hash} Failed request to {url} after {MAX_RETRIES} attempts. Last status: {response.status_code if 'response' in locals() else 'No response'}")
    return None

def strip_comments(line):
    parts = line.split("//", 1)
    return parts[0].strip() if parts else ""

def extract_function(source_code, fn_line_start):
    function_lines = []
    brace_count = 0
    found_open_brace = False

    for i, line in enumerate(source_code[fn_line_start:], start=fn_line_start):
        function_lines.append(line.strip())

        # Count opening braces
        brace_count += line.count('{')

        # Start tracking only after the first {
        if brace_count > 0:
            found_open_brace = True

        # Count closing braces
        brace_count -= line.count('}')

        if found_open_brace and brace_count == 0:
            break

    return function_lines

def further_analysis(contract, function_name, error_msg):
    source_code = contract["source"].splitlines()

    if not function_name:
        return ""
    fn_line_start = next((i for i, line in enumerate(source_code, 1) if function_name in line), None)
    if fn_line_start is None:
        return ""
    function_lines = extract_function(source_code, fn_line_start)
    current_statement = ""
    capturing = False
    for line in function_lines:
        stripped = line.strip()
        if any(keyword in stripped for keyword in ("require", "revert", "assert", "if")) or capturing:
            capturing = True
            current_statement += " " + stripped
            if ";" in stripped:
                capturing = False
                if error_msg and error_msg in current_statement:
                    return current_statement.strip()
                current_statement = ""
    return ""

def get_errorlines(contract, line_number):
    """Analyze contract source code around the error line."""
    source_code = contract["source"].splitlines()
    error_lines = []
    if len(source_code) >= line_number and line_number > 0:
        if "revert" in source_code[line_number - 1].strip() and not "if" in source_code[line_number - 1].strip():
            for j in range(line_number - 2, -1, -1):
                if not source_code[j].strip().startswith("//"):
                    error_lines.insert(0, strip_comments(source_code[j]))
                    if "if" in source_code[j].strip() or "function" in source_code[j].strip():
                        break
        error_lines.append(strip_comments(source_code[line_number - 1]))
        if ";" not in source_code[line_number -1] and "}" not in source_code[line_number -1]:
            for i in range(line_number, len(source_code), 1):
                if not source_code[i].strip().startswith("//"):
                    error_lines.append(strip_comments(source_code[i]))
                    if ";" in source_code[i] or "}" in source_code[i]:
                        break
    error_lines = " ".join(error_lines)
    return error_lines

def get_error_from_stack(response_data, hash):
    stack_trace = (
    response_data.get("transaction", {})
    .get("transaction_info", {})
    .get("stack_trace", [])
)
    if isinstance(stack_trace, list) and stack_trace:
        stack_trace = stack_trace[0]
    else:
        error_logger.error(f"hash: {hash} No stack trace found in response")
        return {"failure_message": "", "failure_invariant": "no stack trace found"}
    if "out of gas" in stack_trace.get("error", ""):
        return {"failure_message": "out of gas", "failure_invariant": "out of gas"}
    if stack_trace.get("line") == None and stack_trace.get("file_index") == None:
        for id in response_data.get("contracts"):
            if stack_trace.get("contract") == id.get("id"):
                error_logger.error(f"hash: {hash} No reason found in stack trace")
                return {"failure_message": "", "failure_invariant": "no reason found"}
        return {"failure_message": f"OpCode: {stack_trace.get('op')}", "failure_invariant": "no source code found"}
    
    if stack_trace.get("error") != "null":
        file_index = stack_trace.get("file_index", "")
        contract_id = stack_trace.get("contract", "")
        error_line = stack_trace.get("line", "")
        error_message = stack_trace.get("error_reason", "")
        function_name = stack_trace.get("code", "")
        error_details = {"failure_message": error_message, "failure_invariant": []}

        contracts = response_data["contracts"]
        for contract in contracts:
            if contract_id in contract.get("id"):
                contract_data = contract["data"]["contract_info"]
                for data in contract_data:
                    if data.get("id") == file_index:
                        error_lines = get_errorlines(data, error_line)
                        if "require" not in error_lines and "revert" not in error_lines and "assert" not in error_lines and "contract" in error_lines:
                            err_lns = further_analysis(data, function_name, error_message)
                            if err_lns != "":
                                error_lines = err_lns
                        error_details["failure_invariant"] = error_lines
                        return error_details
    error_logger.error(f"hash: {hash} Invariant is empty")
    return error_details

def analyze_failed_transaction(from_address, to_address, block_number, tx_input, gas, gas_price, value, tx_index, tx_hash,
                          simulation_mode="full", network_id="1", save=False):
    """Simulate a transaction using Tenderly API."""
    payload = {
        "network_id": network_id,
        "from": from_address,
        "to": to_address,
        "block_number": block_number,
        "input": tx_input,
        "gas": gas,
        "gas_price": gas_price,
        "value": value,
        "transaction_index": tx_index,
        "simulation_type": simulation_mode,
        "estimate_gas": True,
        "save": False,
    }
    headers = {'X-Access-Key': TENDERLY_API_KEY}
    response = safe_request(TENDERLY_SIMULATION_URL, method= "POST", headers = headers, payload= payload, hash=tx_hash)
    
    with open("test.txt", "w") as file:
        json.dump(response, file, indent=4)
    
    if response == None:
        return {"failure_message": "", "failure_invariant": ""}
    if "arithmetic underflow or overflow" in response.get("transaction", "").get("error_message", "") or "division or modulo by zero" in response.get("transaction", "").get("error_message", ""):
        err = response.get("transaction").get('error_message')
        return {"failure_message": err, "failure_invariant": err}   
    
    return get_error_from_stack(response, tx_hash)


def fetch_transaction_info(tx_hash):
    """Fetch transaction details from Tenderly's public API."""
    headers = {
        'authority': 'api.tenderly.co',
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://dashboard.tenderly.co/',
    }

    data = safe_request(f"{TENDERLY_PUBLIC_TX_URL}{tx_hash}", headers=headers, hash = tx_hash)


    result = {}
    block_number = int(data.get("block_number", 0))
    from_address = data.get("from")
    to_address = data.get("to")
    tx_input = data.get("input")
    gas = int(data.get("gas", 0))
    gas_price = int(data.get("gas_price", 0))
    value = data.get("value", "0x0")
    if value == "0x":
        value = "0x0"
    value = int(value, 16)
    tx_index = int(data.get("index", 0))    

    tx_data = {
            "hash": tx_hash,
            "block_number": int(data.get("block_number", 0)),
            "from_address": data.get("from"),
            "to_address": data.get("to"),
            "tx_input": data.get("input"),
            "gas": int(data.get("gas", 0)),
            "gas_price": int(data.get("gas_price", 0)),
            "value": value,
            "tx_index": int(data.get("index", 0)),
            "gas_limit": int(data.get("gas_limit", 0))
        }
    result.update(tx_data)


    if not data.get("status"):
        result["status"] = False
        error_message = data.get("error_message")
        result["failure_reason"] = error_message

        if "out of gas" in error_message:
            result["failure_invariant"] = "out of gas"
            return result
        
        if "arithmetic overflow or underflow" in error_message:
            result["failure_invariant"] = "arithmetic overflow or underflow"
            return result
        
        if "division or modulo by zero" in error_message:
            result["failure_invariant"] = "division or modulo by zero"
            return result
        
        # Extract transaction details
        if "out of gas" in error_message:
            result["failure_message"] = "out of gas"
            result["failure_invariant"] = "out of gas"
            return result
        
        # Simulate the failed transaction
        error_analysis = analyze_failed_transaction(from_address, to_address, block_number, tx_input, gas, gas_price, value, tx_index, tx_hash)
        result.update(error_analysis)
    else:
        result["status"] = True
    return result
    
def main():
    """Process a transaction hash passed as a command-line argument."""
    parser = argparse.ArgumentParser(description="Analyze an Ethereum transaction.")
    parser.add_argument("tx_hash", help="Ethereum transaction hash (66 characters, starting with '0x')")
    args = parser.parse_args()

    tx_hash = args.tx_hash.strip()

    if not (tx_hash.startswith("0x") and len(tx_hash) == 66):
        print("Invalid transaction hash. It should start with '0x' and be 66 characters long.")
        sys.exit(1)

    result = fetch_transaction_info(tx_hash)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()