def crawl_page(page):
    try:
        # 获取当前页
        curr_span = page.query_selector("span.layui-laypage-curr em:last-child")
        current_page = int(curr_span.inner_text()) if curr_span else 0

        # 获取所有页码链接
        page_links = page.query_selector_all("div.layui-box a[data-page]")

        # 如果没有页码链接，说明只有一页
        if not page_links:
            print("已经是最后一页")
            return False

        # 获取最大页码
        max_page = 0
        for link in page_links:
            page_num = int(link.get_attribute("data-page"))
            if page_num > max_page:
                max_page = page_num

        # 如果当前页等于最大页码，说明已是最后一页
        if current_page >= max_page:
            print("已经是最后一页")
            return False

        # 查找下一个页码的链接并点击
        next_page = current_page + 1
        next_btn = page.query_selector(f"a[data-page='{next_page}']")

        if not next_btn:
            print("未找到下一页按钮")
            return False

        # 执行翻页
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页出现异常: {e}")
        return False
