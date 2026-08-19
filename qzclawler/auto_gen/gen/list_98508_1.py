import time

#使用playwright，查找page页面上【按职位列显示】，进行点击
def crawl_page(page):
    time.sleep(1)
    # 通过元素包含的文本内容定位到“实习信息”对应的<p>元素所在的<li>元素，然后点击它 
    # 先等待包含目标元素的父级div加载出现，超时时间设置为5秒（可根据实际调整）
    page.wait_for_selector('div.f-left.hd', timeout=5000)
    # 通过文本内容定位到“实习信息”对应的<p>元素所在的<li>元素
    # 使用XPath选择器定位包含“实习信息”文本的<li>元素
    shixi_info_li = page.locator('//li[.//p[text()="专场招聘"]]')
    shixi_info_li.click()
    time.sleep(1)