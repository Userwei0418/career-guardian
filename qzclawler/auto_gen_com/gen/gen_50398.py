import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie')
        announcement_name = announcement_name.get_text(strip=True) if announcement_name else ''

        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV')
        publish_time = publish_time.get_text(strip=True).replace('发布于 ', '') if publish_time else ''

        link_tag = card.find('a')
        link = link_tag['href'] if link_tag and 'href' in link_tag.attrs else ''

        hd_depts = card.find_all('div', class_='sd-Ellipsis-hiddenContainer-3yguc')
        hd_dept = hd_depts[0].get_text(strip=True) if len(hd_depts) > 0 else ''
        hd_job_category = hd_depts[1].get_text(strip=True) if len(hd_depts) > 1 else ''
        hd_loc = hd_depts[-1].get_text(strip=True) if len(hd_depts) > 0 else ''

        hd_job_num_tag = card.find('div', class_='salary-AOKS3Ocnck')
        hd_job_num = hd_job_num_tag.get_text(strip=True) if hd_job_num_tag else ''

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
