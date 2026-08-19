def crawl_page(page):
    try:
        next_page_button = page.locator("a.nextPage")

        if not next_page_button or next_page_button.count() == 0:
            return False

        class_attr = next_page_button.get_attribute("class") or ""

        # 如果 class 中出现常见禁用标记，就不能点
        if "disable" in class_attr or "disabled" in class_attr or "stop" in class_attr:
            return False

        # 如果文本变成“下一页 »”也能识别
        text = next_page_button.inner_text().strip()
        if "下一页" not in text:
            return False

        # 一切正常就点
        next_page_button.click()
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
