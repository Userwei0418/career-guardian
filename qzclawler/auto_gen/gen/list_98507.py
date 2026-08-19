import time

#使用playwright，查找page页面上【按职位列显示】，进行点击
def crawl_page(page):
    page.wait_for_selector('text=按职位列显示')
    page.click('text=按职位列显示')

    time.sleep(2)
    # 先点击展开下拉菜单的按钮（那个带有dropdown-toggle类的按钮）
    page.locator('button.btn.btn-xs.btn-default.dropdown-toggle').click()
    time.sleep(1)
    # 再定位到下拉菜单中文本为100的选项并点击
    elements = page.locator('ul.dropdown-menu li:has(a:has-text("100")) a').all()
    if len(elements) > 0:
        elements[0].click()
    time.sleep(2)