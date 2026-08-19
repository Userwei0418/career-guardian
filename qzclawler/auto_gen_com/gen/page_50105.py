def crawl_page(page):
    try:
        # 找到分页区域
        paging = page.query_selector('div.pagenum')
        if not paging:
            print("未找到分页区域")
            return False

        # 获取所有 span
        spans = paging.query_selector_all('span')

        # 下一页按钮是最后一个 span，且 class="icon iconfont"
        next_btn = spans[-1]

        # 判断是否可点击（比如已到最后一页可能会 disable，这里根据你的 UI 调整）
        cls = next_btn.get_attribute("class") or ""
        if "iconfont" not in cls:
            print("下一页按钮不可点击")
            return False

        print("准备翻页 → 下一页")

        # 点击下一页
        next_btn.click()

        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
