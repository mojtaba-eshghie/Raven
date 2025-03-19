import requests
import sys
import json
import argparse
import os

# API Endpoints and Keys (Consider storing sensitive keys securely using environment variables)
TENDERLY_SIMULATION_URL = "https://api.tenderly.co/api/v1/account/Melissa194/project/project/simulate"
TENDERLY_PUBLIC_TX_URL = "https://api.tenderly.co/api/v1/public-contract/1/tx/"
DUNE_TRANSACTIONS_URL = "https://api.dune.com/api/echo/v1/transactions/evm/"

TENDERLY_API_KEY = os.getenv("TENDERLY_API_KEY")
DUNE_API_KEY = os.getenv("DUNE_API_KEY")
DUNE_HEADERS = {"X-Dune-Api-Key": DUNE_API_KEY}

if not TENDERLY_API_KEY or not DUNE_API_KEY:
    raise ValueError("API keys are missing. Set TENDERLY_API_KEY and DUNE_API_KEY as environment variables.")

def get_last_call(call_data):
    """Traverse call trace to get the last executed call."""
    if not call_data or "calls" not in call_data:
        return {}  # Return empty dict instead of crashing

    while "calls" in call_data and isinstance(call_data["calls"], list) and call_data["calls"]:
        call_data = call_data["calls"][-1]  # Move to the last call
    return call_data

def safe_request(url, method="GET", headers=None, payload=None):
    """Helper function to handle API requests with error handling."""
    try:
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            print("Rate limit exceeded. Please try again later.")
        else:
            print(f"API request failed: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        print("Request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        print("Network error. Check your internet connection.")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    return None


def analyze_contract_execution(contract, line_number, last_function):
    """Analyze contract source code around the error line."""
    source_code = contract["source"].splitlines()
    if len(source_code) >= line_number:
        for i in range(line_number, 0, -1):
            if last_function in source_code[i]:   
                error_lines = [source_code[line_number - 1]]
                if ");" not in source_code[line_number -1]:
                    for i in range(line_number + 1, len(source_code), 1):
                        error_lines.append(source_code[i - 1])
                        if ");" in source_code[i -1]:
                            break
                return error_lines
            if "function" in source_code[i]:
                return []
    return []


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

    #response = requests.post(TENDERLY_SIMULATION_URL, json=payload, headers=headers)
    #response_data = response.json()
    response_data = safe_request(TENDERLY_SIMULATION_URL, method="POST", headers=payload, payload=headers)

    # Extract last executed call details
    last_call = get_last_call(response_data["transaction"]["transaction_info"]["call_trace"])
    last_function = last_call.get("function_name")
    line_number = last_call.get("error_line_number")
    
    error_details = {"failure_message": response_data["transaction"]["error_message"], "failure_invariant": []}
    # Analyze the contract where the failure occurred
    contracts = response_data["contracts"]
    for contract in contracts:
        contract_data = contract["data"]["contract_info"]
        for data in contract_data:
            error_lines = analyze_contract_execution(data, line_number, last_function)
            if error_lines:
                error_details["failure_invariant"] = error_lines
                break
    return error_details

def fetch_transaction_info(tx_hash):
    """Fetch transaction details from Tenderly's public API."""
    headers = {
        'authority': 'api.tenderly.co',
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://dashboard.tenderly.co/',
    }

    data = safe_request(f"{TENDERLY_PUBLIC_TX_URL}{tx_hash}", headers=headers)
    if not data:
        return {"error": "Failed to fetch transaction details."}
    
    try:
        with open("output.txt", "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"File writing error: {e}")

    print(f"\nSimulate transaction for: {tx_hash}")
    result = {}

    if not data.get("status"):
        result["status"] = False
        result["failure_reason"] = data.get("error_message")
        
        
        error_message = data.get("error_message")

        if error_message == "out of gas":
            return result
        
        # Extract transaction details
        block_number = int(data.get("block_number", 0))
        from_address = data.get("from")
        to_address = data.get("to")
        tx_input = data.get("input")
        gas = int(data.get("gas_used", 0))
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
        result["Status"] = True
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
