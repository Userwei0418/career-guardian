def crawl_page(page):
    try:
        # 找“下一页”按钮所在的 li（未禁用）
        next_li = page.query_selector('li.ant-pagination-next:not(.ant-pagination-disabled)')
        if not next_li:
            print("已经是最后一页，无下一页可点击")
            return False

        # 取 button
        btn = next_li.query_selector('button.ant-pagination-item-link')
        if not btn:
            print("下一页按钮不存在")
            return False

        print("准备翻页 → 下一页")
        btn.click()

        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
