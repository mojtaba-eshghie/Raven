import requests
import sys
import json
import argparse
import time

# API Endpoints and Keys (Consider storing sensitive keys securely using environment variables)
TENDERLY_SIMULATION_URL = "https://api.tenderly.co/api/v1/account/Melissa194/project/project/simulate"
TENDERLY_PUBLIC_TX_URL = "https://api.tenderly.co/api/v1/public-contract/1/tx/"

TENDERLY_API_KEY = "QBaUP1mgKshN32lxAUgaGxkksjBXVoo8"

MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 0  # Start at 1 second
BACKOFF_MULTIPLIER = 2  # Exponential growth factor

def safe_request(url, method="GET", headers=None, payload=None):
    """Helper function to handle API requests with exponential backoff."""
    retry_delay = INITIAL_RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers)
        else:
            response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:    
            print(f"Received status code {response.status_code}. Retrying in {retry_delay} seconds...")
        time.sleep(retry_delay)
        retry_delay *= BACKOFF_MULTIPLIER

    return None

def strip_comments(line):
    parts = line.split("//", 1)
    return parts[0].strip() if parts else ""

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
        if ");" not in source_code[line_number -1] and "}" not in source_code[line_number -1]:
            for i in range(line_number, len(source_code), 1):
                if not source_code[i].strip().startswith("//"):
                    error_lines.append(strip_comments(source_code[i]))
                    if ");" in source_code[i] or "}" in source_code[i]:
                        break
    error_lines = " ".join(error_lines)
    return error_lines

def is_out_of_gas(tx_hash):
    """Fetch transaction details from Tenderly's public API."""
    headers = {
        'authority': 'api.tenderly.co',
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://dashboard.tenderly.co/',
    }

    data = safe_request(f"{TENDERLY_PUBLIC_TX_URL}{tx_hash}", headers=headers)
        
    error_message = data.get("error_message")

    if "out of gas" in error_message:
        return True
    return False


def get_error_from_stack(response_data):
    stack_trace = (
    response_data.get("transaction", {})
    .get("transaction_info", {})
    .get("stack_trace", [])
)
    if isinstance(stack_trace, list) and stack_trace:
        stack_trace = stack_trace[0]
    else:
        return {"failure_message": "", "failure_invariant": "no stack trace found"}

    if stack_trace.get("line") == None and stack_trace.get("file_index") == None:
        for id in response_data.get("contracts"):
            if stack_trace.get("contract") == id.get("id"):
                return {"failure_message": "", "failure_invariant": "no reason found"}
        return {"failure_message": f"OpCode: {stack_trace.get('op')}", "failure_invariant": "no source code found"}
    
    if stack_trace.get("error") != "null":
        file_index = stack_trace.get("file_index")
        contract_id = stack_trace.get("contract")
        name = stack_trace.get("name")
        error_line = stack_trace.get("line")
        error_message = stack_trace.get("error")
        error_details = {"failure_message": error_message, "failure_invariant": []}
        # Analyze the contract where the failure occurred
        contracts = response_data["contracts"]
        for contract in contracts:
            if contract_id in contract.get("id"):
                contract_data = contract["data"]["contract_info"]
                for data in contract_data:
                    if data.get("id") == file_index:
                        error_lines = get_errorlines(data, error_line)
                        error_details["failure_invariant"] = error_lines
                        return error_details
    return error_details

def analyze_failed_transaction(from_address, to_address, block_number, tx_input, gas, gas_price, value, tx_index,
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
    response = safe_request(TENDERLY_SIMULATION_URL, method= "POST", headers = headers, payload= payload)
    
    with open("test.txt", "w") as file:
        json.dump(response, file, indent=4)
    
    if response == None:
        return {"failure_message": "", "failure_invariant": ""}
    #response = requests.post(TENDERLY_SIMULATION_URL, json=payload, headers=headers)

    #response_data = response.json()
    # Extract last executed call details
    
    return get_error_from_stack(response)


def fetch_transaction_info(tx_hash):
    """Fetch transaction details from Tenderly's public API."""
    headers = {
        'authority': 'api.tenderly.co',
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://dashboard.tenderly.co/',
    }

    data = safe_request(f"{TENDERLY_PUBLIC_TX_URL}{tx_hash}", headers=headers)

    result = {}

    if not data.get("status"):
        result["status"] = False
        result["failure_reason"] = data.get("error_message")
        
        
        error_message = data.get("error_message")

        if "out of gas" in error_message:
            return result
        
        # Extract transaction details
        block_number = int(data.get("block_number", 0))
        from_address = data.get("from")
        to_address = data.get("to")
        tx_input = data.get("input")
        gas = int(data.get("gas_limit", 0))
        gas_price = int(data.get("gas_price", 0))
        value = data.get("value", "0x0")
        if value == "0x":
            value = "0x0"
        value = int(value, 16)
        tx_index = int(data.get("index", 0))
        
        # Simulate the failed transaction
        error_analysis = analyze_failed_transaction(from_address, to_address, block_number, tx_input, gas, gas_price, value, tx_index)
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

# out of gas
#0x5f7eac6d1a746cabbc76b5a1f29c4449b3342b39aef646952f5d591aecdf7d6f

# multi line require
#0xc0edf110029f19d26a90be43a4c2212a75e6a89f429219f6b1cf7a3d02a26d53

# require
#0x3fa6ac025485bf482a632e1d14e09902b5a176cb455ed081c3f9b8da2036a4fc

# working transaction
#0xc390f5f74130c0821dced50501fea66dd2d684a29887cfb205e2f12edaa2c523

# Problem: doesnt have the error in the trace, and gives out of gas even though not true
#0x030672dcf80cc566c44902f526dd65c78e9e331d0e8ba7257c392a6a2d6b7146
