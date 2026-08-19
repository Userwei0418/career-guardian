# 进行翻页
def crawl_page(page):
    try:
        # 尝试找到真实可点击的下一页（<a>）
        next_page_button = page.locator("a.ui-paging-next")

        # 如果是真实按钮 → 可翻页
        if next_page_button.count() > 0:
            if next_page_button.is_visible() and next_page_button.is_enabled():
                print("检测到正常的下一页按钮，执行跳转")
                next_page_button.click()
                return True
            else:
                print("下一页按钮不可交互")
                return False

        # 找不到 <a>，可能是最后一页，页面会变成 <span>
        span_next = page.locator("span.ui-paging-next")
        if span_next.count() > 0:
            print("当前为最后一页（下一页是 span）")
            return False

        # 两种都不存在 → 异常
        print("未找到任何下一页元素")
        return False

    except Exception as e:
        print(f"翻页时出现异常: {e}")
        return False
