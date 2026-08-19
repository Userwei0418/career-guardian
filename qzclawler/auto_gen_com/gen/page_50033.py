def crawl_page(page):
    try:
        # 定位下一页按钮
        next_page_button = page.locator("div.icon-box")

        if next_page_button.count() > 0:
            class_name = next_page_button.get_attribute("class") or ""
            # 判断是否禁用
            if "disable" not in class_name:
                next_page_button.click()
                page.wait_for_timeout(500)  # 等待页面刷新
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
