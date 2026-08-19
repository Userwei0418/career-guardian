def crawl_page(page):
    try:
        # 选择 Layui 的下一页按钮
        next_btn = page.query_selector("a.layui-laypage-next")

        if not next_btn:
            print("未找到下一页按钮")
            return False

        # 获取下一页页码
        next_page = next_btn.get_attribute("data-page")
        if not next_page:
            print("已经是最后一页")
            return False

        # 获取当前页
        curr_span = page.query_selector("span.layui-laypage-curr em:last-child")
        current_page = int(curr_span.inner_text()) if curr_span else 0

        # 判断是否已经是最后一页
        if int(next_page) <= current_page:
            print("已经是最后一页")
            return False

        # 执行翻页
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页出现异常: {e}")
        return False
