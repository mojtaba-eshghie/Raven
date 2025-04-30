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
            if data["result"] is "Max daily rate limit reached":
                return data["result"]

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
