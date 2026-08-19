def crawl_page(page):
    try:
        # 滚动到页面底部，确保分页区域加载
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)

        # 定位并点击“下一页”
        page.locator("#nextPage").click()
        print("成功点击下一页。")
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
