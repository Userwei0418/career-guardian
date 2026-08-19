def crawl_page(page):
    try:
        # 等待分页按钮加载完成
        page.wait_for_selector("a:has-text('下一页')", timeout=5000)
        next_page_button = page.locator("a:has-text('下一页')")

        # 获取属性信息
        aria_disabled = next_page_button.get_attribute("aria-disabled")
        class_name = next_page_button.get_attribute("class")

        # 判断是否禁用
        if aria_disabled == "true" or (class_name and "disabled" in class_name):
            print("下一页按钮已禁用，翻页结束。")
            return False

        # 点击下一页
        next_page_button.click()
        print("成功点击下一页按钮。")
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
