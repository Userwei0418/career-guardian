def crawl_page(page):
    try:
        # 精准定位“下一页”按钮（IBM Carbon Pagination）
        next_page_button = page.locator("a[data-key='next']")

        # 检查元素是否存在
        if not next_page_button or next_page_button.count() == 0:
            print("未找到下一页按钮")
            return False

        # 判断按钮是否可见且可交互
        if next_page_button.is_visible():
            class_name = next_page_button.get_attribute("class") or ""
            aria_disabled = next_page_button.get_attribute("aria-disabled")

            # 检查禁用状态（class 或 aria-disabled）
            if "disabled" in class_name or aria_disabled == "true":
                print("下一页按钮不可点击（被禁用）")
                return False

            # 点击并等待页面加载
            next_page_button.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            print("成功点击进入下一页")
            return True

        else:
            print("下一页按钮不可见")
            return False

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
