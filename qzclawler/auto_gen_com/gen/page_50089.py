def crawl_page(page):
    try:
        # 1) 检测真正的下一页按钮（Avature 结构）
        next_btn = page.locator('a.paginationNextLink')

        # 如果不存在就说明到头了
        if not next_btn or next_btn.count() == 0:
            print("下一页按钮不存在，可能到最后一页")
            return False

        # 2) 取第一个next按钮（即使有分页也只会点这个）
        next_btn = next_btn.first

        # 3) 降低风险：确认按钮是可点击的
        if not next_btn.is_visible():
            print("下一页按钮不可见，结束分页")
            return False

        # 4) 点击并等待加载
        next_btn.click()
        page.wait_for_timeout(1800)
        return True

    except Exception as e:
        print(f"翻页出错: {e}")
        return False
