import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.filter-table tbody tr')

    data_list = []

    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) >= 6:
            announcement_name = cells[0].get_text(strip=True)
            hd_dept = cells[2].get_text(strip=True)
            hd_job_num = cells[3].get_text(strip=True)
            hd_loc = cells[4].get_text(strip=True)
            hd_job_category = cells[1].get_text(strip=True)
            post_id = row['data_postid']  # Extracting the postId from the row attribute

            # Constructing the link based on the given format
            link = ""

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": "",  # Placeholder as publish time is not provided in the HTML
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    # Writing the extracted data to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
