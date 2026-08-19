import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    zpxxBox = soup.find('div', id='zpxxHtm')
    for item in zpxxBox.find_all('div', class_='zpxxList'):
        announcement_name = item.find('div', class_='zpxxUnitNature').text.strip()
        publish_time = item.find('div', class_='zpxxUnitTime').text.strip()
        # Assuming the link is derived from the onclick event
        link = item.parent['onclick'].split("'")[1] if item.parent.has_attr('onclick') else None
        link = f"/career/zpxx/view/sxzpxx/{link}"  # Assuming the link format based on ID
        job_listings.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)