
import json
from bs4 import BeautifulSoup
import time
 
def crawl_page(page,_sch_info): 
    time.sleep(2)
    announcements = {}
    #获取div的class的html
    index_url_selector = _sch_info['index_url_selector']
    style_element = page.query_selector(index_url_selector)
    if style_element:
        tableObj = page.locator(index_url_selector)
        htmlcontext = tableObj.inner_html() 
        soup = BeautifulSoup(htmlcontext, 'html.parser')
        index = 0
        for li in soup.find_all('li'):
            a_tag = li.find('a')
            if a_tag: 
                link = a_tag['href']
                if link.startswith('http'):
                    link = link
                else:
                    link = _sch_info['json_domain'] + link
                announcements[f"link{index}"] = link
            index += 1
    #print(announcements,"1!")
    return announcements 