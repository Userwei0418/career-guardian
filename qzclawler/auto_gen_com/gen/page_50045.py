from playwright.sync_api import Page

def crawl_page(page: Page, action="next", wait_time=5000):
    """
    翻页函数：支持 'next' 或 'prev'
    """
    if action not in ["next", "prev"]:
        raise ValueError("action 必须是 'next' 或 'prev'")

    # 根据 HTML 调整按钮选择器
    if action == "next":
        button_selector = "a.next:not(.disabled)[href]"  # 可点击的下一页
    else:
        button_selector = "a.next:not(.disabled)[disabled!=disabled]"  # 可点击的上一页

    print(f"按钮选择器：{button_selector}")
    btn = page.locator(button_selector)

    try:
        btn.wait_for(state="visible", timeout=wait_time)
        print("✅ 按钮已可见")
    except Exception as e:
        print(f"⚠️ 按钮不可见: {e}")
        return False

    # 点击按钮
    try:
        print("👉 点击分页按钮")
        btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=wait_time)
        page.wait_for_timeout(1000)
        print("✅ 翻页成功")
        return True
    except Exception as e:
        print(f"❌ 点击失败: {e}")
        return False
