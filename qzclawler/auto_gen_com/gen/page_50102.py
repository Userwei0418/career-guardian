def crawl_page(page):
    try:
        # 找到可点击的下一页 li
        next_li = page.query_selector('li.rlt-pagination-next[aria-disabled="false"]')
        if not next_li:
            print("已经是最后一页，无下一页可点击")
            return False

        # 找到内部 button
        next_btn = next_li.query_selector('button.rlt-pagination-item-link')
        if not next_btn:
            print("下一页按钮不存在")
            return False

        print("准备翻页 → 下一页")

        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
