import requests
import time
import pandas as pd
from error_logging import error_logger, listener

API_KEY = "MBK2HMREV9ASCIR97UTJBEDVCFQ8NTVZ9B"  # Replace with your actual API key
base_url = "https://api.etherscan.io/api"

def has_ethereum_src(address, max_retries=1):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": API_KEY
    }

    retries = 0
    delay = 0.2

    while retries <= max_retries:
        try:
            response = requests.get(base_url, params=params)
            if response.status_code == 200:
                data = response.json()

                # Check for rate limit message
                if isinstance(data.get("result"), str) and "Max daily rate limit reached" in data["result"]:
                    #error_logger.error(f"Rate limit reached when querying address {address}: {data['result']}")
                    return None

                # Ensure result is a list and has elements
                if isinstance(data.get("result"), list) and len(data["result"]) > 0:
                    contract_info = data["result"][0]
                    if contract_info.get("SourceCode") == '':
                        return False
                    else:
                        return True
                else:
                    #error_logger.error(f"Unexpected result format for address {address}: {data.get('result')}")
                    return None

            else:
                #error_logger.error(f"Request failed with status {response.status_code} for address {address}")
                retries += 1
                wait_time = delay * (2 ** retries)
                time.sleep(wait_time)

        except requests.exceptions.Timeout:
            #error_logger.error(f"Timeout occurred for address {address} on attempt {retries+1}")
            retries += 1
            wait_time = delay * (2 ** retries)
            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            #error_logger.error(f"RequestException for address {address} on attempt {retries+1}: {e}")
            retries += 1
            wait_time = delay * (2 ** retries)
            time.sleep(wait_time)

        except Exception as e:
            #error_logger.error(f"Unexpected error for address {address}: {e}")
            return None

    # If retries exceeded
    #error_logger.error(f"Max retries exceeded for address {address}")
    return None