
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    def extract_unique_texts(nodes):
        seen = set()
        result = []
        for n in nodes:
            txt = n.get_text(strip=True)
            if txt and txt not in seen:
                seen.add(txt)
                result.append(txt)
        return result
    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']
        types = card.find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')
        if len(types) > 3 :
            hd_loc = types[3].text.strip()
            hd_dept = types[0].text.strip()
            hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
            hd_job_category = types[2].text.strip()
        else:
            hd_loc = ""
            hd_dept = types[0].text.strip()
            hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
            hd_job_category = types[-1].text.strip()
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
