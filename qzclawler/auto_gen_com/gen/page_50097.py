def crawl_page(page):
    try:
        # 定位下一页 li
        next_li = page.query_selector("li.ant-pagination-next")
        if not next_li:
            print("未找到下一页按钮")
            return False

        # 判断是否禁用
        disabled = next_li.get_attribute("aria-disabled") == "true" or "disabled" in (next_li.get_attribute("class") or "")
        if disabled:
            print("已经是最后一页")
            return False

        # 点击 li 内的 a 标签
        next_a = next_li.query_selector("a")
        if not next_a:
            print("下一页链接不存在")
            return False

        next_a.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页出现异常: {e}")
        return False
