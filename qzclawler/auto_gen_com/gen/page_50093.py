def crawl_page(page):
    try:
        next_btn = page.query_selector("a.next")

        if not next_btn:
            print("未找到下一页按钮")
            return False

        # 读取 disabled 属性
        disabled_attr = next_btn.get_attribute("disabled")
        class_attr = next_btn.get_attribute("class") or ""

        # 最后一页：<a disabled="disabled" class="next">
        if disabled_attr == "disabled" or "disabled" in class_attr:
            print("已经是最后一页")
            return False

        # 按钮可点击，执行翻页
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页出现异常: {e}")
        return False
