from src.config.config_main import tfl_config
import requests
from typing import List

class TflClient:
    def __init__(self, config):
        self.app_key = config.primary_key if config.primary_key else config.secondary_key
        self.base_url = config.base_url
        self.use_cache = config.use_cache

        if not self.app_key:
            raise ValueError("At least one TFL API key must be provided in the configuration.")
        
    def get_modes(self):
        response = self._execute_request("Line/Meta/Modes")

        for mode_info in response:
            yield mode_info["modeName"]

    def get_lines_by_mode(self, modes: List[str] = []):
        if modes == []:
            modes = list(self.get_modes())

        endpoint = f"Line/Mode/{','.join(modes)}"
        for line in self._execute_request(endpoint):
            yield {
                "id": line["id"],
                "name": line["name"],
                "mode": line["modeName"],
                "disruptions": line["disruptions"],
                "serviceTypes": [st["name"] for st in line["serviceTypes"]],
            }
        

    def _build_url(self, endpoint: str, params: dict = {}) -> str:
        url = f"{self.base_url}/{endpoint}"
        params["app_key"] = self.app_key

        query_string = "&".join(f"{key}={value}" for key, value in params.items())

        return f"{url}?{query_string}"
    
    def _execute_request(self, endpoint: str, params: dict = {}) -> dict:
        url = self._build_url(endpoint, params)

        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            #TODO: add logging
            raise

tfl_client = TflClient(tfl_config)