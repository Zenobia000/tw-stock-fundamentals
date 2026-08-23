---
name: 波段決策台
description: 冷調、克制且可信任的個人台股研究工作台
colors:
  shell: "#26343d"
  shell-deep: "#1e2b33"
  canvas: "#e8ebea"
  paper: "#f6f7f4"
  paper-soft: "#eef1ef"
  ink: "#26343d"
  muted: "#58676e"
  line: "#cfd5d3"
  line-strong: "#aeb9b6"
  morandi-blue: "#647f8c"
  morandi-blue-deep: "#496575"
  morandi-blue-soft: "#dfe7e8"
  positive: "#5f806f"
  negative: "#9d6368"
  caution: "#a98256"
typography:
  display:
    fontFamily: "Segoe UI Variable, Noto Sans TC, Microsoft JhengHei UI, system-ui, sans-serif"
    fontSize: "clamp(50px, 7vw, 92px)"
    fontWeight: 590
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  body:
    fontFamily: "Segoe UI Variable, Noto Sans TC, Microsoft JhengHei UI, system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: 1.45
  data:
    fontFamily: "IBM Plex Mono, Cascadia Mono, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 650
rounded:
  square: "0px"
  subtle: "2px"
  status: "4px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "18px"
  lg: "44px"
components:
  button-primary:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.paper}"
    rounded: "{rounded.subtle}"
    padding: "13px 18px"
  input-search:
    backgroundColor: "{colors.shell-deep}"
    textColor: "{colors.paper}"
    rounded: "{rounded.square}"
    padding: "9px 12px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "16px"
---

# Design System: 波段決策台

## Overview

**Creative North Star: "冷奢研究室"**

這是一個在安靜環境中長時間使用的個人研究工具。它的尊貴感來自秩序、可信度、留白與細節，不來自炫耀性的效果。首頁與研究內頁共用冷灰紙面、深灰墨藍與低彩度莫蘭迪藍，讓使用者從查詢到判讀都停留在同一個視覺世界。

介面語氣簡短、直接、有分寸。品牌可以神祕，但功能不可含糊；研究資料與狀態永遠比裝飾更醒目。

**Key Characteristics:**

- 冷灰紙面與深灰墨藍形成安靜、專注的使用場景
- 莫蘭迪藍是唯一品牌 accent
- 數字採等寬字並使用 tabular figures
- 以細線、色階與留白建立層次，卡片預設無圓角
- 文案短而具體，不使用 AI 行銷腔

## Colors

色彩採冷調低彩度策略。品牌色只負責導引與選取；紅、綠、琥珀只表達資料狀態或圖表語義。

### Primary

- **霧藍**：用於主要選取、關鍵連結、focus 與少量引導。
- **深霧藍**：用於淺色介面上的可讀 accent 與主要操作。
- **薄霧藍**：用於選取面、摘要面與低層次提示。

### Neutral

- **墨藍外殼**：全域導覽、搜尋列與深色操作面。
- **冷灰畫布**：首頁與研究工作區的連續背景。
- **研究紙面**：資料表、卡片、欄位與浮層內容面。
- **灰藍文字**：次要說明與 metadata，仍須達到 WCAG AA。

### Named Rules

**The No-Neon Rule.** 禁止霓虹色、外發光、紫藍 AI 漸層、高飽和 cyan 與無語義的彩色光暈。

**The One-Accent Rule.** 全站只以莫蘭迪藍作為品牌 accent；紅、綠、琥珀不得用作品牌裝飾。

## Typography

**Display Font:** Segoe UI Variable，搭配繁體中文系統 sans fallback
**Body Font:** Segoe UI Variable，搭配繁體中文系統 sans fallback
**Label/Mono Font:** IBM Plex Mono，後備 Cascadia Mono 與 Consolas

**Character:** 中文以乾淨、略窄、清晰的無襯線字為主。大標題靠尺度與克制字重建立存在感，不用粗黑字、漸層字或混搭襯線字製造高級感。

### Hierarchy

- **Display**：只用於首頁主張，最多兩行，tracking 不低於 -0.04em。
- **Headline**：頁面與功能區標題，字重 590-700，避免在上方疊加英文 eyebrow。
- **Title**：卡片與圖表標題，短而具體。
- **Body**：以繁體中文自然語序撰寫，段落保持易掃讀。
- **Data**：價格、比率、日期與座標軸使用等寬字及 tabular figures。

### Named Rules

**The Plain-Spoken Rule.** 優先使用「查詢、查看、比較、更新、判讀」等具體動詞。避免「建立決策脈絡、開啟投資新視野、無縫掌握、解鎖潛力」等 AI 式包裝。

## Layout

首頁採不對稱雙欄，左側保留大面積主張與單一操作，右側只列研究範圍。內頁維持高密度資料工作台，以固定頂部搜尋、股票摘要、功能頁籤與內容區建立穩定掃讀順序。

寬螢幕內容控制在 1680px 內；1180px 以下收斂多欄圖表，820px 以下改為單欄並讓搜尋獨占一列，520px 以下進一步簡化控制群。滿版高度一律使用 dynamic viewport unit。

## Elevation & Depth

系統以 tonal layering 為主，陰影只用於搜尋結果、tooltip、drawer 與少數浮層。一般資料卡不使用大面積陰影；紙面、畫布與細線已足以表達層級。

**The Flat-By-Default Rule.** 內容面在靜止狀態保持平整，不能同時使用厚邊框與寬陰影。

## Shapes

整體以直角與 1px 細線為主。主要按鈕僅保留 2px 微圓角，狀態標籤使用 4px；圓形只留給真實狀態點與首頁的大尺度背景幾何。

## Components

### Buttons

- **Shape:** 主要操作使用 2px 微圓角；工具按鈕維持直角。
- **Primary:** 深色墨藍面配研究紙白文字，標籤保持單行。
- **Hover / Focus:** 使用自訂 cubic-bezier 色彩轉場、可見 focus ring 與 1px pressed 位移，禁止 glow。
- **Secondary:** 透明底配單一細框，hover 只做同色系 tonal shift。

### Chips

- **Style:** 4px 小圓角、低彩度語義底色與細框。
- **State:** 只表達健康、風險、等待或資料來源，不作裝飾 badge。

### Cards / Containers

- **Corner Style:** 直角。
- **Background:** 研究紙面或柔和紙面。
- **Shadow Strategy:** 預設無陰影。
- **Border:** 單一 1px 冷灰線。
- **Internal Padding:** 以 12-18px 為主要密度。

### Inputs / Fields

- **Style:** 搜尋欄使用深墨藍底、莫蘭迪藍細框與清晰 placeholder。
- **Focus:** 以內縮 1px highlight 加外部可見 focus outline 呈現，不使用發光。
- **Error / Disabled:** 使用低彩度語義色，保留文字說明與足夠 contrast。

### Navigation

頂部導覽使用深色外殼與低彩度文字。Active 狀態採霧藍文字與 3px 底線；手機版搜尋獨占下一列，頁籤可水平捲動。

## Do's and Don'ts

### Do:

- **Do** 讓首頁與內頁共用同一組畫布、紙面、墨藍與莫蘭迪藍 tokens。
- **Do** 讓資料層級、時效與狀態比裝飾更容易被看到。
- **Do** 使用短句與具體動詞，讓控制名稱直接說明動作。
- **Do** 保留紅綠語義給市場與健康狀態，並維持低彩度。

### Don't:

- **Don't** 使用霓虹色、外發光、紫藍漸層或亮 cyan 按鈕。
- **Don't** 在每個區塊標題上方加入英文 eyebrow、編號或假裝專業的 metadata。
- **Don't** 使用「建立決策脈絡」一類抽象、矯飾或 AI 感強烈的說辭。
- **Don't** 用圓角卡片、厚色邊、陰影和 badge 同時包裝同一個資訊區塊。
