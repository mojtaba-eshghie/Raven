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
INITIAL_RETRY_DELAY = 1  # Start at 1 second
BACKOFF_MULTIPLIER = 2  # Exponential growth factor



def safe_request(url, method="GET", headers=None, payload=None):
    """Helper function to handle API requests with exponential backoff."""
    retry_delay = INITIAL_RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        try:
            if method == "POST":
                response = requests.post(url, json=payload, headers=headers)
            else:
                response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()  # Successfully got a response
            elif response.status_code == 429:  # Rate limit error
                print(f"Rate limit exceeded. Retrying in {retry_delay} seconds...")
            else:
                # Handle other HTTP errors (non-200, non-429)
                print(f"Received status code {response.status_code}. Retrying in {retry_delay} seconds...")

        except requests.exceptions.Timeout:
            print(f"Request timed out. Retrying in {retry_delay} seconds...")
        except requests.exceptions.ConnectionError:
            print(f"Network error. Retrying in {retry_delay} seconds...")
        except requests.exceptions.RequestException as e:
            print(f"An unexpected error occurred: {e}")
            break  # Stop retries for unexpected errors

        time.sleep(retry_delay)  # Wait before retrying
        retry_delay *= BACKOFF_MULTIPLIER  # Apply exponential backoff

    print("Max retries reached. Request failed.")
    return None

def get_errorlines(contract, line_number):
    """Analyze contract source code around the error line."""
    source_code = contract["source"].splitlines()
    error_lines = ""
    if len(source_code) >= line_number and line_number > 0:
        error_lines = [source_code[line_number - 1].strip()]
        if ");" not in source_code[line_number -1] and "}" not in source_code[line_number -1]:
            for i in range(line_number, len(source_code), 1):
                error_lines.append(source_code[i].strip())
                if ");" in source_code[i] or "}" in source_code[i]:
                    break
    error_lines = "\n".join(error_lines)
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
        return "No stack trace found"
    if stack_trace.get("line") == "null" and stack_trace.get("line") == "null":
        return {"error_message": "OpCode: REVERT", "failure_invariant": ""}
    
    if stack_trace.get("error") != "null":
        file_index = stack_trace.get("file_index")
        contract = stack_trace.get("contract")
        name = stack_trace.get("name")
        error_line = stack_trace.get("line")
        error_message = stack_trace.get("error")
        error_details = {"failure_message": error_message, "failure_invariant": []}
        # Analyze the contract where the failure occurred
        contracts = response_data["contracts"]
        for contract in contracts:
            if contract["contract_name"] == name:
                contract_data = contract["data"]["contract_info"]
                for data in contract_data:
                    if data["id"] == file_index:
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
    if response == None:
        return ""
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

    if data == 429:
        return data

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
