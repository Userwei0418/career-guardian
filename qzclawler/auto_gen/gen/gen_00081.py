
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    # Find all list items in the specified class
    for li in soup.select('.yinRightContains li'):
        a_tag = li.find('a')
        if a_tag:
            announcement_name = a_tag.find('span', class_='reds').text.strip()
            publish_time = a_tag.find('span', class_='tim').text.strip()
            aids = a_tag['onclick'].split("','")  # Extracting the unique identifier from the onclick attribute
            link = f"https://jyzx.zzife.edu.cn/module/newsdetail/id-{aids[1]}/nid-{aids[2]}"
            hd_company = ""  # Placeholder for company name, as it's not provided in the HTML
            
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_company": hd_company
            })
    
    # Write the announcements list to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)