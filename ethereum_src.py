import requests
import time
import pandas as pd
API_KEY = "MBK2HMREV9ASCIR97UTJBEDVCFQ8NTVZ9B"  # Replace with your actual API key
base_url = "https://api.etherscan.io/api"

def has_ethereum_src(address, max_retries = 1):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": API_KEY
    }

    retries = 0
    delay = 0.2

    while retries <= max_retries:
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if "Max daily rate limit reached" in data["result"]:
                return ValueError(data["result"])

            # Now check if it's a list and not a string
            if isinstance(data["result"], list) and len(data["result"]) > 0:
                contract_info = data["result"][0]
                if contract_info["SourceCode"] == '':
                    return False
                else:
                    return True
        else:
            print("this is not working")
            retries += 1
            wait_time = delay * (2 ** retries)
            time.sleep(wait_time)

    return None

import requests
import time
import json

def get_solidity_source(file_name, source_code):
    cleaned_input = source_code.replace("'", '"').replace(r'\r\n', '\n')
    #cleaned_input = json.loads(cleaned_input)
    hi = cleaned_input.get("language", "")
    print(hi)
    source_code_str = source_code.strip('{}')
    try:
        source_code = json.loads(source_code_str)  # Now source_code is a dictionary
    except json.JSONDecodeError as e:
        print(f"Error parsing SourceCode: {e}")
        source_code = {}

    source_code = source_code.get("sources", {})
    if file_name in source_code:
        return source_code["content"]
    return None

def get_src(address, max_retries=2):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": API_KEY
    }

    retries = 0
    delay = 0.2

    while retries <= max_retries:
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            data = response.json()
            
            with open("test11111111.txt", "w") as file:
                json.dump(data, file, indent=4)
                

            if "Max daily rate limit reached" in data["result"]:
                raise ValueError(data["result"])

            if isinstance(data["result"], list) and len(data["result"]) > 0:
                contract_info = data["result"][0]
                source_code = contract_info.get("SourceCode", '')
                return source_code
        else:
            print(f"Request failed with status code {response.status_code}, retrying...")
            retries += 1
            wait_time = delay * (2 ** retries)
            time.sleep(wait_time)

    return None

def main():
    address = "0xc7de47b9ca2fc753d6a2f167d8b3e19c6d18b19a"
    file = "FiatTokenV1.sol"

    source_code = get_src(address)    

    if source_code:
        print("Source code found:\n", source_code)
    else:
        print("No matching file found.")

if __name__ == "__main__":
    main()