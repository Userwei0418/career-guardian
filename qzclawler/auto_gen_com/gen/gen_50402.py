import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0 hjqbak')

    for item in items:
        announcement = {}

        # Extracting announcement name
        title_div = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4 kMriaU')
        announcement['announcement_name'] = title_div.get_text(strip=True) if title_div else ""

        # Extracting publish time
        time_div = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16 eKeZsF')
        announcement['publish_time'] = time_div.get_text(strip=True) if time_div else ""

        # Extracting link (assuming a link is present in the detail button)
        link_div = item.find('div', class_='style__STDetailBtn-editor__sc-10r1nhd-29 bvBJPZ')
        announcement['link'] =  ""

        # Extracting department or institution
        dept_div = item.find('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')
        announcement['hd_dept'] = dept_div.get_text(strip=True) if dept_div else ""

        # Extracting work location
        loc_div = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[2]
        announcement['hd_loc'] = loc_div.get_text(strip=True) if loc_div else ""

        # Extracting job number (assuming it's a static value for this example)
        announcement['hd_job_num'] = ''  # Placeholder value

        # Extracting job category
        announcement['hd_job_category'] = ''  # Placeholder value

        announcements.append(announcement)

    # Write to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)


