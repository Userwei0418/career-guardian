def crawl_page(page):
    try:
        # 直接按文字定位“下一页”
        next_btn = page.locator("a.next", has_text="下一页")

        if next_btn.count() == 0:
            return False

        # 判断是否被禁用
        class_name = next_btn.get_attribute("class") or ""
        disabled_attr = next_btn.get_attribute("disabled")

        if "disabled" in class_name or disabled_attr is not None:
            return False

        next_btn.click()
        page.wait_for_load_state("domcontentloaded")
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
