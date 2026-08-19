def crawl_page(page):
    try:
        # 定位“下一页”按钮
        next_page_button = page.locator("li.next_page a.page-link")

        # 检查元素是否存在并可见
        if next_page_button.count() == 0:
            print("没有找到下一页按钮")
            return False

        # 获取父元素（li），判断是否是禁用状态
        parent_li = page.locator("li.next_page")
        parent_class = parent_li.get_attribute("class")
        aria_disabled = parent_li.get_attribute("aria-disabled")

        # 如果有禁用状态
        if (aria_disabled == "true") or ("disabled" in (parent_class or "")):
            print("下一页按钮不可用，翻页结束。")
            return False

        # 元素存在且可点，执行点击
        next_page_button.click()
        page.wait_for_load_state("networkidle")  # 等待页面加载完毕
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
