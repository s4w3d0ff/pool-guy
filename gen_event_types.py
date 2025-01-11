import os, logging, json
import requests
from bs4 import BeautifulSoup
logger = logging.getLogger(__name__)
eventsubdocurl = "https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/"

def fetch_eventsub_types(dir="db/eventsub_versions"):
    # Check if we already have today's data
    #filename = f"{dir}/{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    filename = f"{dir}/eventsub_types.json"
    if os.path.exists(filename):
        # Load and return existing data
        logger.info(f"fetch_eventsub_types: loaded {filename}")
        with open(filename, 'r') as f:
            return json.load(f)
    # Ensure db directory exists
    os.makedirs(dir, exist_ok=True)
    response = requests.get(eventsubdocurl)
    logger.info(f"[GET] {eventsubdocurl} [{response.status_code}]")
    if response.status_code != 200:
        raise Exception("Failed to fetch webpage") 
    soup = BeautifulSoup(response.text, "html.parser")
    eventsub_types = {}
    # Locate the table containing subscription types
    table = soup.find("table")
    if not table:
        raise Exception("Failed to locate the table in the webpage")
    # Extract rows from the table body
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 3:
            name = cells[1].find("code").get_text(strip=True)  # Extract 'Name'
            version = cells[2].find("code").get_text(strip=True)  # Extract 'Version'
            eventsub_types[name] = version
    with open(filename, 'w') as f:
        json.dump(eventsub_types, f, indent=4)
    return eventsub_types

if __name__ == '__main__':
    fetch_eventsub_types()