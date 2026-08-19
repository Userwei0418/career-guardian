import time

#使用playwright，查找page页面上【按职位列显示】，进行点击
def crawl_page(page):
    # # 使用CSS选择器定位class为ui-zpxx-list的div元素
    # div_element = page.locator('#jyxx_list').locator('#page_list1')
    # time.sleep(1)
    # # 通过选择器定位到下拉框元素
    # dropdown = div_element.locator('span.k-widget.k-dropdown')
    # # 点击下拉框展开选项列表
    # dropdown.click()
    # time.sleep(1)
    # # 通过定位选项中的值来选择对应的选项，选择值为100的选项
    # option_100 = dropdown.locator('select[data-role="dropdownlist"] option[value="100"]')
    # option_100.style_click()
    # page.evaluate("(element) => element.style.display = 'block'", option_100) 
    # option_100.click()
    time.sleep(1)