def crawl_page(page):
    try:
        # 1. 点击「士兰集科」
        page.locator("div.li", has_text="士兰集科").first.click()
        print("已点击士兰集科")

        # 等待内容切换（给页面一点反应时间）
        page.wait_for_load_state("networkidle")

        # 2. 点击「查看更多」
        more_btn = page.locator("div.join-button", has_text="查看更多")
        more_btn.wait_for(state="visible", timeout=5000)
        more_btn.click()
        if more_btn.is_enabled():
            more_btn.click()
        else:
            print("已点击查看更多")

            return True

    except Exception as e:
        print("点击流程异常:", e)
        return False
