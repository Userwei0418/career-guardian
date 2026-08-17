
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('li', class_='social_position_card__epffd')

    for card in job_cards:
        link_tag = card.find('a')
        link = link_tag['href'] if link_tag else ''

        title_tag = card.find('h4', class_='PositionCard_title__Gb9xb')
        announcement_name = title_tag.get_text(strip=True) if title_tag else ''

        keyword_tag = card.find('p', class_='PositionCard_keyword__FFaH5')
        if keyword_tag:
            keyword_text = keyword_tag.get_text(strip=True).split(' | ')
            hd_loc = keyword_text[0] if len(keyword_text) > 0 else ''
            hd_category = keyword_text[1] if len(keyword_text) > 1 else ''
            publish_time = keyword_text[3] if len(keyword_text) > 3 else ''
        else:
            hd_loc = hd_category = publish_time = ''
        if "实习" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": '',  # Placeholder as the number is not provided in the HTML
            "hd_job_category": hd_category,
            "hd_hopeworktype": hd_hopeworktype
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
