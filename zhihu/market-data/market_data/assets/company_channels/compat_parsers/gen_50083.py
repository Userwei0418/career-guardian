import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        link = card.find('a')['href']
        short_description = card.find('div', class_='short-description-hpQeFUeJUY').text.strip()

        # Extracting details from the short description
        lines = short_description.split(' ')
        publish_time = ""  # Placeholder as publish time is not provided in the HTML
        hd_dept = ""  # Placeholder as department is not provided in the HTML
        hd_loc = ""  # Placeholder as location is not provided in the HTML
        hd_job_num = ""  # Placeholder as job number is not provided in the HTML
        hd_job_category = ""  # Placeholder as job category is not provided in the HTML

        # Create a job entry
        job_entry = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_entry)

    # Write to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
