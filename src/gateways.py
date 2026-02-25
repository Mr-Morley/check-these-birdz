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

class WikipediaEnricher:
    def __init__(self, user_agent='CheckTheseBirdz/1.0 (will@example.com)'):
        self.wiki = wikipediaapi.Wikipedia(user_agent=user_agent, language='en')

    def enrich(self, sciname):
        page = self.wiki.page(sciname.capitalize())
        if not page.exists():
            return None

        iucn_status = "Unknown"
        for cat in page.categories.keys():
            if "IUCN" in cat:
                iucn_status = cat
                break

        #first 300 words of the summary
        summary_words = page.summary.split()
        description = " ".join(summary_words[:300])

        return {
            "wiki_url": page.fullurl,
            "description": description,
            "iucn_status": iucn_status
        }