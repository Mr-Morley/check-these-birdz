import requests
import wikipediaapi

class EBirdGateway:
    def __init__(self, api_key):
        self.base_url = "https://api.ebird.org/v2"
        self.headers = {"X-eBirdApiToken": api_key}

    def fetch_recent_observations(self, region="ZA", days=14):
        url = f"{self.base_url}/data/obs/{region}/recent?back={days}"
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            raise Exception(f"eBird API Error: {response.status_code}")
        return response.json()



IUCN_CATEGORY_MAP = {
    "critically endangered": "Critically Endangered",
    "near threatened":       "Near Threatened",
    "least concern":         "Least Concern",
    "endangered":            "Endangered",
    "vulnerable":            "Vulnerable",
    "data deficient":        "Data Deficient",
    "extinct":               "Extinct",
}


class WikipediaEnricher:
    def __init__(self, user_agent='CheckTheseBirdz/1.0 (will@example.com)'):
        self.wiki = wikipediaapi.Wikipedia(user_agent=user_agent, language='en')

    def _parse_iucn(self, categories: dict) -> str:
        """Extracts a clean IUCN status from Wikipedia category keys."""
        for cat_key in categories:
            cat_lower = cat_key.lower()
            if "iucn" not in cat_lower:
                continue
            # Check from most specific to least specific
            for keyword, label in IUCN_CATEGORY_MAP.items():
                if keyword in cat_lower:
                    return label
        return "Unknown"

    def enrich(self, sciname: str) -> dict | None:
        page = self.wiki.page(sciname.capitalize())
        if not page.exists():
            return None

        iucn_status = self._parse_iucn(page.categories)

        summary_words = page.summary.split()
        description = " ".join(summary_words[:300])

        return {
            "wiki_url": page.fullurl,
            "description": description,
            "iucn_status": iucn_status,
        }