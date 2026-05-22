# Ticket Plus 遠大售票 搶票輔助腳本

個人合法輔助工具：協助你在 ticketplus.com.tw 搶票時自動完成可自動化的步驟（選票區、選張數、勾條款、選取票/付款方式、送出），**只在必須人為判斷的環節（圖形驗證碼、3D 驗證）暫停讓你接手**。

## 設計原則

- **不破解驗證碼、不偽造請求**：完全走瀏覽器 UI 路徑，遇到圖形驗證碼就暫停讓你輸入
- **不儲存信用卡/帳密**：聯絡人與卡片由遠大會員系統自動帶入
- **headed 模式可見**：你能隨時介入

## 環境需求

- macOS（音效/系統通知使用 `afplay` 與 `osascript`）
- Python 3.11+

## 一次性設定

```bash
# 1) 安裝套件
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# 2) 複製設定範本
cp config.example.yaml config.yaml
# 編輯 config.yaml：填入活動 URL、開賣時間、票區優先序

# 3) 一次性手動登入並儲存 session
.venv/bin/python prep.py
# 在開啟的瀏覽器中登入會員 → 回終端機按 Enter
```

## 使用方式

### 正式搶票

```bash
.venv/bin/python snipe.py
```

腳本會：
1. 對 NTP 校時（`time.stdtime.gov.tw`）
2. 倒數到開賣前 N 秒（config 中 `lead_seconds`，預設 3）
3. 用儲存的 session 開瀏覽器進入訂購頁
4. 高頻點擊「立即購票」→ 選票區 → 選張數
5. **遇到驗證碼會暫停 + 發出提示音**，你填好後腳本自動繼續
6. 確認選位 → 勾條款 → 下一步
7. 選取票方式 → 選付款方式 → 點「前往付款」
8. **抵達 3D 驗證頁面後音效＋系統通知**，瀏覽器保持開啟讓你接手

### 演練（測試 selector 是否還能命中）

開賣前可挑一個冷門活動演練：

```bash
.venv/bin/python snipe.py --dry-run --url "https://ticketplus.com.tw/order/<某個冷門場次>"
```

`--dry-run` 不倒數，直接開瀏覽器執行流程。建議手動取消訂單，不要真的付款。

## 設定檔說明

```yaml
event:
  url: "https://ticketplus.com.tw/order/<event-id>/<session-id>"
  sale_time: "2026-06-01T12:00:00+08:00"  # 必須含時區

preferences:
  ticket_count: 1                # 目前只支援 1
  zone_priority:                 # 從最高價/最想要的往下排
    - "搖滾"
    - "4880"
    - "3880"
  seat_allocation: "電腦選位"     # 或 "自行選位"（自行選位需手動點座位）
  pickup: "ibon"
  payment: "信用卡"               # 或 "ATM"

state:
  storage_state_path: "state/storage_state.json"

lead_seconds: 3
```

## 專案結構

```
spider/
├── prep.py              # 一次性登入工具
├── snipe.py             # 搶票主程式
├── snipe/
│   ├── config.py        # YAML 載入與驗證
│   ├── browser.py       # Playwright 啟動
│   ├── timer.py         # NTP 對時 + 倒數
│   ├── selectors.py     # 頁面 selector 集中管理
│   ├── flow.py          # 訂購流程順序動作
│   └── notify.py        # 音效 + macOS 通知
├── tests/               # 單元測試
├── config.example.yaml
├── config.yaml          # 你自己的設定 (gitignored)
├── state/               # session (gitignored)
└── logs/                # 截圖、log (gitignored)
```

## 測試

```bash
.venv/bin/python -m pytest tests/ -v
```

## 平台改版怎麼辦

頁面 selector 集中在 `snipe/selectors.py`，遇到改版只需要：

1. 用 `.venv/bin/python snipe.py --dry-run --url <測試場次>` 跑一次
2. 觀察 `logs/` 內截圖看哪一步卡住
3. 在瀏覽器 DevTools 找新的 text/CSS selector
4. 更新 `snipe/selectors.py`

## 已知限制

- 只搶 1 張票（程式碼有 assert，需要改 `config.py` 與 `flow.py:set_ticket_count` 才能支援多張）
- 自行選位需要手動點座位，腳本不自動選位置
- 信用卡 3D 驗證需要使用者自己完成
- macOS 專用通知；Linux/Windows 需自行替換 `notify.py`

## 合規聲明

本工具僅供個人輔助使用，**不破解驗證碼、不偽造請求、不繞過任何反爬蟲機制**。請遵守 Ticket Plus 的服務條款，違規造成帳號封鎖或法律風險須自行承擔。
