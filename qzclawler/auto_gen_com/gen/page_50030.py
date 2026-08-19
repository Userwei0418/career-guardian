def crawl_page(page):
    try:
        # 根据 aria-label 定位“下一页”
        next_page_button = page.locator('a[aria-label="Next"]')

        if next_page_button.count() > 0:
            # 获取按钮父 li 判断是否禁用
            parent_li = next_page_button.locator('xpath=..')  # 上一级 li
            class_name = parent_li.get_attribute("class") or ""

            if "disabled" not in class_name:
                next_page_button.click()
                page.wait_for_timeout(500)  # 等待页面刷新
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
