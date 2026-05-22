"""集中管理 ticketplus 頁面 selectors。

平台改版時統一在這裡更新即可。優先使用語意化（text/role）selector，CSS class
為輔。每個邏輯按鈕保留多個 fallback 試法。
"""
from __future__ import annotations

# 主要按鈕
BUY_NOW_TEXTS = ["立即購買", "立即購票", "立即訂購", "Buy Tickets Now"]
NEXT_TEXTS = ["下一步", "Next"]
NEXT_BTN_CSS = "button.nextBtn"   # 遠大專用 class，比文字定位更穩
GO_TO_PAYMENT_TEXTS = ["前往付款", "Go to Payment"]
CONFIRM_TEXTS = ["確定", "確認", "OK"]
FINISH_TEXTS = ["完成", "Done"]

# 票區選擇頁面的偵測條件（任一命中視為已進入）
ZONE_PAGE_TEXT_MARKERS = ["選擇票種", "選擇票區"]
ZONE_PAGE_STRUCTURAL_MARKERS = [
    "button.v-expansion-panel-header",
    ".v-card:has-text('剩餘')",
]
ZONE_MODAL_HEADER = "選擇票種"  # 保留供舊代碼參考
ZONE_ROW_SELECTOR = "[class*='zone'], [class*='ticket-area'], tr, li"

# 同意條款
AGREE_TEXTS = ["我已經閱讀並同意", "我已閱讀並同意"]

# 取票方式：「ibon」「便利生活站」是 logo 圖片，無法用 text 匹配。
# 改用選項下方的描述文字（純 DOM 文字節點，inner_text 抓得到）
PICKUP_LABELS = {
    "ibon": [
        "酌收 NT.30",          # 描述文字（最穩定）
        "超商門市付款",
        "NT.30手續費",
        "便利生活站",          # 若不是圖片時的 fallback
        "ibon",
    ],
    "宅配": ["宅配", "郵寄", "中華郵政"],
}

# 付款方式：類似情況，圖片 logo 可能無文字。改用描述文字
PAYMENT_LABELS = {
    "信用卡": [
        "信用卡線上刷卡一次付清",
        "本金流服務由",
        "遠傳電信 提供",
        "可接受 VISA",
        "MasterCard",
        "JCB",
        "信用卡線上刷卡",
        "信用卡",
    ],
    "ATM": [
        "120 分鐘內完成繳款程序",
        "ATM 虛擬帳號",
        "ATM虛擬帳號",
        "虛擬帳號",
    ],
}

# 驗證碼（圖形）
CAPTCHA_INPUT_HINTS = [
    "input[name*='captcha' i]",
    "input[id*='captcha' i]",
    "input[placeholder*='驗證碼']",
]

# 售完/不可選樣式偵測
SOLD_OUT_INDICATORS = ["已售完", "已售出", "售完", "Sold Out"]
SOLD_OUT_PATTERN = r"剩餘\s*0\b"  # expansion panel header 顯示「剩餘 0」

# Expansion panel (票區是 collapsible 時)
EXPANSION_PANEL_HEADER = "button.v-expansion-panel-header, .v-expansion-panel-header"
EXPANSION_PANEL_CONTENT = ".v-expansion-panel-content"

# 中間頁
SEAT_CONFIRM_HEADER = "確認選位結果"

# 參加者資訊
PARTICIPANT_SECTION_HEADER = "參加者資訊"
PARTICIPANT_FIELD_LABELS = {
    "name": ["姓名"],
    "id_number": ["身分證或護照", "身分證", "護照"],
    "nationality": ["國籍/地區", "國籍", "Nationality"],
}

# 登入態偵測
LOGGED_IN_INDICATORS = ["會員專區", "登出", "我的帳戶"]
