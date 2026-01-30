from src.config.config_main import tfl_config
import requests
from typing import List
import time

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

    def get_line_details(self, line_id: str):
        endpoint = f"Line/{line_id}"
        return self._execute_request(endpoint)

    def get_stops_by_mode(self, modes: List[str], page: int = None):
        """
        Get stop points filtered by transport modes.
        
        Args:
            modes: List of mode names (e.g., ['tube', 'dlr'])
            page: Page number for pagination (required for bus mode)
        
        Returns:
            StopPointsResponse dictionary containing stopPoints array
        """
        endpoint = f"StopPoint/Mode/{','.join(modes)}"
        params = {}
        if page is not None:
            params['page'] = page
        
        response = self._execute_request(endpoint, params)
        return response

    def get_route_sequence(self, line_id: str, direction: str = "all"):
        """
        Get ordered stop sequence for a line.
        
        Args:
            line_id: Single line identifier (e.g., 'victoria')
            direction: 'inbound', 'outbound', or 'all'
        
        Returns:
            RouteSequence object with ordered stop sequences
        """
        endpoint = f"Line/{line_id}/Route/Sequence/{direction}"
        return self._execute_request(endpoint)
    
    def get_all_line_statuses(self, modes: List[str], detail: bool = True):
        """
        Get current status for all lines of given modes.
        
        Args:
            modes: List of mode names (e.g., ['tube', 'dlr'])
            detail: Include disruption details (default True)
        
        Returns:
            List of Line objects with lineStatuses arrays
        """
        endpoint = f"Line/Mode/{','.join(modes)}/Status"
        params = {'detail': str(detail).lower()}
        return self._execute_request(endpoint, params)
    
    def get_line_status(self, line_ids: List[str], detail: bool = True):
        """
        Get status for specific lines.
        
        Args:
            line_ids: List of line IDs (max ~20)
            detail: Include disruption details
        
        Returns:
            List of Line objects
        """
        endpoint = f"Line/{','.join(line_ids)}/Status"
        params = {'detail': str(detail).lower()}
        return self._execute_request(endpoint, params)
    
    def get_severity_codes(self):
        """
        Get list of valid severity codes.
        
        Returns:
            List of StatusSeverity objects
        """
        endpoint = "Line/Meta/Severity"
        return self._execute_request(endpoint)
    
    def get_disruption_categories(self):
        """
        Get list of valid disruption categories.
        
        Returns:
            List of category strings
        """
        endpoint = "Line/Meta/DisruptionCategories"
        return self._execute_request(endpoint)
    
    def get_stop_arrivals(self, stop_id: str):
        """
        Get arrival predictions for a specific stop.
        
        Args:
            stop_id: NaPTAN ID of the stop
        
        Returns:
            List of Prediction objects
        """
        endpoint = f"StopPoint/{stop_id}/Arrivals"
        return self._execute_request(endpoint)
        

    def _build_url(self, endpoint: str, params: dict = {}) -> str:
        url = f"{self.base_url}/{endpoint}"
        params["app_key"] = self.app_key

        query_string = "&".join(f"{key}={value}" for key, value in params.items())

        return f"{url}?{query_string}"
    
    def _execute_request(self, endpoint: str, params: dict = {}) -> dict:
        url = self._build_url(endpoint, params)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Add small delay to avoid rate limiting
                time.sleep(0.5)
                
                return response.json()
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"Request timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 504 and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"504 Gateway Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Request failed: {e}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    #TODO: add logging
                    raise

tfl_client = TflClient(tfl_config)