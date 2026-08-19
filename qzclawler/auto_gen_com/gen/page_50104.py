def crawl_page(page):
    try:
        # 找到文字为“下一頁”的链接
        next_a = page.query_selector('a:has-text("下一頁")')
        if not next_a:
            print("已经是最后一页，无下一页可点击")
            return False

        print("准备翻页 → 下一页")

        next_a.click()
        page.wait_for_load_state("networkidle")

        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
