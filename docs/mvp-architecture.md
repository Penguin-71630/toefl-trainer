# MVP 架構文件（終端機版 LLM 出題服務）

本文件是實作規格：模組職責、資料庫 DDL、API 契約、出題流水線、prompt 與
JSON schema、驗證規則、狀態更新公式、CLI 狀態機、安裝與啟動腳本。

設計主張：**LLM 是周邊設備，後端是控制單元**。後端決定考什麼、選項是什麼、
答案是什麼、狀態怎麼變；LLM 只負責它擅長的自然語言生成，且輸出必經驗證。

---

## 1. 專案結構

```text
toefl-trainer/
├── init.py                   # 建 venv、裝依賴、寫 .env（純標準庫）
├── run.py                    # sanity check、啟動 backend、textual serve（純標準庫）
├── requirements.txt
├── .env.example              # 不含任何真實 key
├── .gitignore                # venv/  app.db  .env
├── pipeline/                 # M0 內容生產線（已完成，與 runtime 無關）
├── data/
│   ├── vocabulary.json       # 7,439 items（唯讀內容，進 repo）
│   ├── grammar.json          # 45 考點（唯讀內容，進 repo）
│   └── fixtures/questions.json # 預錄題目與批改（無 API key 時回放）
├── backend/
│   ├── main.py               # FastAPI 端點（薄層）
│   ├── orchestrator.py       # 流程控制：sampler → distractor → generator → validator
│   ├── sampler.py            # 選目標字／考點（加權隨機）
│   ├── distractor.py         # 組干擾選項（權重表）
│   ├── generator.py          # 呼叫 LLM 生成題幹（prompt 在此）
│   ├── validator.py          # 驗證 LLM 輸出
│   ├── grader.py             # 批改（客觀題本地、翻譯題送 LLM）
│   ├── state.py              # proficiency / streak / unfamiliar 更新
│   ├── rating.py             # Elo：單字 rating、預期答對率、段位、TOEFL 推估
│   ├── llm.py                # LLM gateway：provider 切換、fixture、節流重試
│   ├── db.py                 # SQLite 連線、DDL、seed
│   └── config.py             # 所有可調係數
└── frontend/
    ├── toefl.py              # Textual App 入口
    ├── screens/              # welcome / menu / loading / exam / result / review / stats
    ├── api.py                # 唯一碰 HTTP 的地方
    ├── models.py             # 回傳 JSON 的 dataclass
    └── styles.tcss
```

---

## 2. 資料庫（SQLite，`app.db`，runtime 生成）

### difficulty 實際分佈（7,433 字全部有值）

min 6.13、max 15.68、median 12.85。八成的字集中在 11–14.5，因此所有與
difficulty 相關的常數都以 **11–15** 這個有效區間為基準（不是理論的 2–17）。

| 區間 | 6–9 | 9–10 | 10–11 | 11–12 | 12–13 | 13–14 | 14–15 | 15–16 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 字數 | 67 | 216 | 534 | 1,239 | 1,995 | 2,312 | 1,043 | 27 |

三個已知限制與對策：

1. **頻率飽和**：rank 以 COCA 20,000 校準，凡低於語料下限的字都被壓到
   rank ≈ 2^14.1，所以 14 以上的排序解析度很差。要真正拉開需要更大的頻率語料。
2. **構詞透明度**：純頻率會把 `nonrelevant`、`unbiased` 判成極難字，但會
   `relevant` / `bias` 的人不需要另外學。`pipeline/morph_difficulty.py` 以
   「字根 difficulty + 詞綴罰分」為上限修正（676 字），並用 WordNet 的屈折／
   derivational 連結擋掉假字根（`wither` ≠ `with` + `er`）。
3. **查不到的字**：15 個字在 COCA 與 wordfreq 都查不到且無法拆解，人工標定
   （`antiquate` 13.0，其餘 15.0）。

`vocabulary` 與 `grammar_points` 由 seed script 從 JSON 灌入，執行期唯讀。

```sql
-- 共用內容（seed，唯讀）
CREATE TABLE vocabulary (
    id             INTEGER PRIMARY KEY,
    word           TEXT    NOT NULL,
    difficulty     REAL    NOT NULL,         -- log2(rank)，含構詞折扣與人工標定
    rating         REAL    NOT NULL,         -- Elo（seed 時由 difficulty 百分位算出）
    word_family_id INTEGER,
    phrase_head    TEXT,                    -- phrase_attribute.head，單字為 NULL
    phrase_particles TEXT,                   -- JSON array，單字為 NULL
    sources        TEXT NOT NULL,            -- JSON array
    exam_tags      TEXT NOT NULL,            -- JSON array
    senses         TEXT NOT NULL             -- JSON array（含 pos/gloss/thesaurus/
                                             --   definition_en/examples）
);
CREATE INDEX idx_vocab_rating ON vocabulary(rating);

CREATE TABLE grammar_points (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    description    TEXT NOT NULL,
    example        TEXT NOT NULL,            -- JSON {sentence, source}
    error_patterns TEXT NOT NULL,            -- JSON array
    exam_tags      TEXT NOT NULL             -- JSON array
);

-- 使用者與狀態（runtime）
CREATE TABLE users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL UNIQUE,
    rating     REAL    NOT NULL DEFAULT 1400,   -- Elo（見 §3）
    exams_done INTEGER NOT NULL DEFAULT 0,      -- 決定 K-factor
    created_at TEXT NOT NULL
);

CREATE TABLE rating_history (                -- 每場 exam 一筆，畫成長曲線
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    rating     REAL    NOT NULL,
    delta      REAL    NOT NULL,
    recorded_at TEXT   NOT NULL
);

CREATE TABLE user_items (                    -- 字彙狀態快取
    user_id          INTEGER NOT NULL,
    item_id          INTEGER NOT NULL,
    correct_count    INTEGER NOT NULL DEFAULT 0,
    wrong_count      INTEGER NOT NULL DEFAULT 0,
    proficiency      REAL    NOT NULL,       -- p_stored
    streak           INTEGER NOT NULL DEFAULT 0,
    unfamiliar_score INTEGER NOT NULL DEFAULT 0,
    last_seen_at     TEXT,
    PRIMARY KEY (user_id, item_id)
);

CREATE TABLE user_grammar_points (           -- 文法狀態快取（同結構）
    user_id          INTEGER NOT NULL,
    grammar_point_id INTEGER NOT NULL,
    correct_count    INTEGER NOT NULL DEFAULT 0,
    wrong_count      INTEGER NOT NULL DEFAULT 0,
    proficiency      REAL    NOT NULL,
    streak           INTEGER NOT NULL DEFAULT 0,
    unfamiliar_score INTEGER NOT NULL DEFAULT 0,
    last_seen_at     TEXT,
    PRIMARY KEY (user_id, grammar_point_id)
);

CREATE TABLE reviews (                       -- append-only 原始事實
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    item_id          INTEGER,                -- 字彙題；文法題為 NULL
    sense_index      INTEGER,
    grammar_point_id INTEGER,                -- 文法題；字彙題為 NULL
    question_type    TEXT NOT NULL,          -- cloze|synonym|structure|
                                             --   written_expression|translation
    question_payload TEXT NOT NULL,          -- JSON，含 generated_by
    user_answer      TEXT NOT NULL,
    score            REAL NOT NULL,          -- 0.0 ~ 1.0
    grader_payload   TEXT,                   -- LLM 批改輸出；本地批改為 NULL
    marked_unfamiliar INTEGER NOT NULL DEFAULT 0,
    answered_at      TEXT NOT NULL
);
CREATE INDEX idx_reviews_user ON reviews(user_id, answered_at);
CREATE INDEX idx_reviews_item ON reviews(item_id);
```

只 INSERT `reviews`，永不 UPDATE/DELETE。`user_items` / `user_grammar_points`
的每一欄都可由 reviews 重放重算——換 proficiency 公式或改上 FSRS 時，
只需重跑重算腳本。

---

## 3. 使用者能力估計（Elo rating，`rating.py`）

採 Codeforces 式設計：**題目（單字）rating 固定**（由語料頻率標定，執行期不浮動），
只有**使用者 rating 浮動**；一場 exam（10 題）= 一場 contest，結算一次。
單一使用者的資料量不足以修正單字難度，讓它浮動只會把「這字難」與
「今天忘了」混在一起。

### 尺度錨定

兩個 anchor：TOEFL ITP **627 → 2100**（Master，C1 下限）、**677 → 2400**（Grandmaster）。

```python
rating = 2100 + (toefl - 627) * 6        # 每 1 分 TOEFL = 6 rating
toefl  = clamp(627 + (rating - 2100) / 6, 310, 677)   # 顯示用推估分數
```

| 段位 | rating | ≈ TOEFL | CEFR |
| --- | --- | --- | --- |
| Newbie | < 1200 | < 477 | A2 / B1 低 |
| Pupil | 1200–1399 | 477–510 | B1 |
| Specialist | 1400–1599 | 510–543 | B1 高 |
| Expert | 1600–1899 | 543–593 | B2（1600 即 B2 下限） |
| Candidate Master | 1900–2099 | 593–627 | B2 高 |
| Master | 2100–2399 | 627–677 | C1（目標） |
| Grandmaster | 2400–2699 | 677+ | 超出 ITP 上限 |
| Native Speaker | 2700+ | — | 需更大詞庫才支援 |

MVP 將 rating 上限 clamp 在 **2500**（`RATING_CAP`），但實際上現有詞庫最難的字
只到 2250（見下），所以 Grandmaster 以上在 MVP 內幾乎不可達——這是刻意的：
詞庫學完約 10–11k 總詞彙量，不足以認定 Grandmaster（Native Speaker 需 20k+）。
未來要考 TOEFL iBT / IELTS 再擴詞庫，新字從 2250 往上延伸。

### 單字 rating（以百分位映射，seed 時算好存欄位）

不能直接對 `difficulty` 做線性映射：詞庫難度分佈非常密集（八成在 11.1–14.1），
線性映射會讓 rating 2100 對到詞庫的 99.5 百分位——與 2400（100%）幾乎無法區別。
改用**百分位（quantile）映射**，讓相同數量的字佔相同的 rating 區間：

```python
# seed 時計算並寫入 vocabulary.rating（靜態欄位，之後不再重算）
pct         = 該字 difficulty 在詞庫中的百分位          # 0.0 ~ 1.0
rating_word = 1100 + 1150 * pct                        # 1100 ~ 2250
```

| difficulty | 11 | 12 | 13（中位） | 13.5 | 14 | 14.5 | 15.68 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 百分位 | 11% | 28% | 55% | 71% | 86% | 99.4% | 100% |
| rating | 1226 | 1418 | 1727 | 1913 | 2084 | 2243 | 2250 |

**頂端為何是 2250（Master 上緣）而不是 2400（Grandmaster）**：現有詞庫學完
約 10–11k 總詞彙量，而 677 / Grandmaster 本來就應該**超出這個詞庫**。
讓詞庫頂端只到 2250，才不會讓「本詞庫全通」被誤讀成「已達 677」。

**一致性檢查**（這組數字的意義很直接：rating 對應「你會詞庫的多少 %」）：

| rating | 段位 | 詞庫百分位 | 累計字數 |
| --- | --- | --- | --- |
| 1200 | Pupil | 8.7% | 646 |
| 1400 | Specialist | 26% | 1,939 |
| 1600 | Expert | 44% | 3,232 |
| 1900 | Candidate Master | 70% | 5,171 |
| **2100** | **Master（目標，≈ TOEFL 627）** | **87%** | **6,463** |
| 2250 | Master 上緣 | 100% | 7,433（全詞庫） |
| 2400 | Grandmaster（≈ 677） | — | 需擴詞庫 |

2100 → 詞庫的 87%（6,463 字）加上一般基礎字彙 ≈ 10k words，大致落在
CEFR C1 的 receptive vocabulary 量級（B2 ≈ 5,000 word families、C1 ≈ 8,000），
且留有緩衝。

### 這個 anchor 是可校準的猜測

rating 只量測**本系統練的字彙＋文法題表現**；ITP 的 Listening（50 題）完全沒練、
Reading（50 題）也只間接相關。因此 UI 文案要寫成「字彙／文法部分相當於
≈ XXX 分的水準」，**不是分數預測**。

待使用者考過一次真的 ITP（或完整模擬考）後，記下實際分數並調整 anchor 常數
（`TOEFL_ANCHOR_SCORE` / `TOEFL_ANCHOR_RATING`）即可；因為 `reviews` 是 append-only，
rating 歷史可整條重算，不會遺失資料。

百分位映射的唯一代價：它依賴當前詞庫。因此 rating **在 seed 時算好寫進資料庫就凍結**，
未來擴詞庫時新字從 2250 往上延伸，而不是把舊字重新縮放（否則歷史 rating
就不可比）。

### 預期答對率（含猜對修正）

```python
E_raw = 1 / (1 + 10 ** ((rating_word - rating_user) / 400))
E     = 0.25 + 0.75 * E_raw    # 四選一的 guessing floor（cloze/synonym/structure/WE）
E     = E_raw                  # 翻譯題無猜對空間，不修正
```

這便是新字的 `p_init`，取代原本手調的線性公式（3-parameter IRT 的 guessing
參數簡化版）。

### 更新（一場 exam 結算一次）

```python
delta = K * sum(score_i - E_i for i in exam)          # 10 題一起結算
K     = 12 if exams_done < 10 else (8 if exams_done < 40 else 4)
rating_user = clamp(rating_user + delta, 0, RATING_CAP)
```

`score` 可以是小數（翻譯題的部分分數），Elo 的 S 值本來就允許 [0,1]，
不需特別處理。K 遞減是西洋棋/Codeforces 慣例：初期大步收斂，
積累資料後小步微調。初始 rating：`1400`（Specialist），或由使用者輸入
自評 TOEFL 分數換算。

理論依據：這就是 Rasch model / 1-parameter IRT 的線上梯度下降版；
Klinkenberg et al. (2011) 的 Math Garden 以同樣方式做即時能力估計。

文法題：`grammar_points` 沒有 difficulty，MVP 給固定 rating `1800`
（`GRAMMAR_DEFAULT_RATING`，約 Expert 中段），之後可依實測答對率手動標定，
就跟 Codeforces 人工標題目分數一樣。

### 與 proficiency 的分工

Elo rating：**一個數字**，管難度媒合、新字先驗、進度展示。
`proficiency` / `streak`：**7,439 個數字**，管單字記憶狀態與間隔複習。
兩者互補，都要保留。

---

## 4. 狀態更新公式（`state.py`）

所有係數在 `config.py`。

```python
# 先驗（第一次遇到該字時建立記錄）：直接用 Elo 預期答對率
p_init = E(rating_user, rating_word, question_type)     # 見 §3
# 文法考點沒有 difficulty，固定用 0.4
streak = 0
unfamiliar_score = 0

# 作答後更新
alpha = ALPHA_UP if score >= p_old else ALPHA_DOWN            # 0.3 / 0.5
p_stored = p_old + alpha * (score - p_old)
streak   = streak + 1 if score >= 0.5 else 0
unfamiliar_score = (unfamiliar_score + 3) if marked else max(unfamiliar_score - 1, 0)
last_seen_at = now()

# 讀取時（sampler / heat map）：只對高分衰減
half_life = min(5 * 1.8 ** streak, 180)                       # 天
decay     = 0.5 ** (days_since_last_seen / half_life)
p_eff     = p_stored + (0.5 - p_stored) * (1 - decay) if p_stored > 0.5 else p_stored
```

`unfamiliar_score` 不寫入 proficiency（保持證據純淨），只影響抽樣權重與
heat map 的顯示標記。

---

## 5. Sampler（`sampler.py`）

候選池：同詞性／可出當前題型、`rating_word` 在 `rating_user ± 350` 內
（≈ 詞庫的 30% 寬度）、未在本 session 出現過。不再用「近 50 筆答對平均難度」
這種 heuristic，一律以 `rating_user` 為基準（見 §3）。

```python
w_prof       = 1 + 3 * (1 - p_eff)                     # 1 ~ 4
w_unfamiliar = 1 + 0.5 * unfamiliar_score              # 標記加成，會自然衰退
w_recency    = min(1.0, 0.2 + 0.8 * days_since / 14)   # 0.2 → 1.0（14 天）
w_level      = exp(-((rating_word - rating_user) / 175) ** 2)
                                                       # 鐘形，貼合當前程度；
                                                       # sigma 175 ≈ 詞庫的 15%
weight       = (w_prof * w_unfamiliar * w_recency * w_level) ** TEMPERATURE  # T=1
```

抽樣：依 weight 的**不重複加權隨機**（輪盤法；`random.choices` 會重複，
不可直接用）。一輪 10 題中保留 `NEW_ITEM_QUOTA`（預設 3）個從未練過的新字，
確保詞彙量成長。文法題同理，候選池換成 grammar_points，去掉 `w_level`，
改用 `exam_tags` 篩選練習範圍。

---

## 6. 干擾項（`distractor.py`）

候選：同詞性、`difficulty` 在目標 ±1.5。

```python
weight = 0                                   if cand in 目標義項.thesaurus
       = 0                                   if 同 word_family 且詞性不同
       = 3                                   if 同 word_family 且詞性相同、義不同
       = 1 + 5 * SequenceMatcher(None, a, b).ratio()   否則
```

全部歸零時退回一般池（同詞性、difficulty 相近的隨機字）。
Synonym 題的**強版本**額外插入一個「目標字其他義項的 thesaurus 字」當干擾
（是同義字但不是此語境的），這是對齊 ITP「as used in the passage」的關鍵。

---

## 7. 題型與 LLM 契約

四種客觀題 + 一種自由作答。LLM 一律回傳 JSON，後端驗證後才採用；
失敗重試一次，再失敗降級（改出不需生成題幹的題型或換題）。

### A. cloze（語境填空，練用法）

LLM 輸入：目標字、目標義項 gloss/詞性、四個選項（僅供避免洩題）。
LLM 輸出：
```json
{"sentence": "The hotel was large enough to ______ all 300 attendees.",
 "explanation": "…（並說明其他三個選項為何不適用）"}
```
驗證：恰一處 `______`；句長 8–35 字；句中不得出現任何選項字或目標字變形；
explanation 非空。

### B. synonym（語境同義字替換，對齊 ITP vocabulary question）

LLM 輸入：目標字、**指定義項**的 gloss。
LLM 輸出：
```json
{"sentence": "I cannot abide the constant noise from the construction site.",
 "explanation": "…"}
```
驗證：句中含目標字（可含變形）；句長 8–35 字；句中不得出現任何選項字；
語境須能排除其他義項（由 explanation 說明，人工抽查）。
選項：正解取自目標義項 thesaurus；干擾取自其他義項 thesaurus + 權重抽樣。

### C. structure（ITP Structure 型填空）

LLM 輸入：考點 `name` / `description` / `error_patterns` / `example`。
LLM 輸出：
```json
{"full_sentence": "Mount Kilauea, a volcano located in Hawaii, is one of …",
 "stem": "Mount Kilauea, ______, is one of …",
 "correct_option": "a volcano located",
 "wrong_options": [
   {"text": "which a volcano",   "error_pattern": "誤用關係代名詞開頭卻無動詞"},
   {"text": "is a volcano located", "error_pattern": "同位格片語內誤加動詞（is/was）"},
   {"text": "where a volcano",   "error_pattern": "誤用關係代名詞開頭卻無動詞"}],
 "explanation": "…"}
```
驗證：四選項互異；`stem` 恰一處挖空；`correct_option` 填回 `stem` 等於
`full_sentence`；每個 `error_pattern` **必須在該考點的 error_patterns 清單內**
（否則拒收——錯誤模式由我們定義，不由 LLM 發明）。

### D. written_expression（ITP 找錯型）

LLM 輸入：考點 + **後端指定的一個 error_pattern**。
LLM 輸出：
```json
{"correct_version": "The manager praised the team for working quickly, carefully, and efficiently.",
 "segments": ["quickly", "carefully", "with efficiency", "assigned"],
 "wrong_index": 2,
 "corrected_segment": "efficiently",
 "error_pattern": "並列項詞性不一致",
 "explanation": "…"}
```
呈現時把 4 個 segment 標 (A)(B)(C)(D)，其餘句子照 `correct_version` 但
第 `wrong_index` 段替換為錯誤版本。
驗證：4 段皆為句子的子字串且互不重疊；把錯段換成 `corrected_segment` 後
等於 `correct_version`（自我一致性）；`error_pattern` 等於後端指定的那個。

### E. translation（中翻英，LLM 批改）

出題 LLM 輸出：
```json
{"zh_sentence": "這間飯店大到足以容納三百位參加會議的人。",
 "reference_translation": "The hotel was large enough to accommodate 300 conference attendees."}
```
驗證：`reference_translation` 含目標字（可含變形）；中文句長合理。

批改 LLM 輸入：中文原句、參考譯文、目標字、使用者譯文、評分準則
（目標字未用或用錯最多扣 0.3；每處文法錯誤扣 0.2；語意偏離扣 0.3）。
批改 LLM 輸出：
```json
{"score": 0.7,
 "used_target_word": true,
 "errors": [{"span": "attendee", "type": "number", "fix": "attendees"}],
 "better_version": "…",
 "comment": "…"}
```
驗證：`score` ∈ [0,1]（超出則 clamp）；欄位齊全；`errors` 為 array。
`errors` 中出現的字若在詞庫內，回饋給 sampler 當**弱訊號**（提高抽中權重），
但不寫成 reviews（避免弱證據污染 proficiency）。

---

## 8. LLM Gateway（`llm.py`）

```python
providers = [
    {"name": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "model": os.environ["LLM_MODEL"]},
    {"name": "groq",   "base_url": "https://api.groq.com/openai/v1",
     "model": "llama-3.3-70b-versatile"},
]
```
- 統一用 `openai` 套件 + 換 `base_url`（不裝各家 SDK）
- `LLM_PROVIDER=mock` 或 key 缺失／格式錯 → `FixtureProvider`：從
  `data/fixtures/questions.json` 依序回放（內容事先用真 LLM 產生）
- 一律要求 JSON 輸出（`response_format={"type": "json_object"}` 或 prompt 約束），
  解析失敗即視為驗證失敗
- 節流：全域 `asyncio.Semaphore(MAX_CONCURRENCY)` + 每分鐘請求數上限；
  429／5xx 指數退避重試（最多 2 次），仍失敗則整批降級為 fixture
- 每次呼叫記錄 provider/model 進 `question_payload.generated_by`（可稽核）

---

## 9. API（`main.py`）

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| POST | `/users` | `{username}` → `{user_id, is_new}`（無密碼，本地單機） |
| POST | `/exams` | `{user_id, question_type, n=10}` → `{exam_id, questions[]}`（**不含答案**） |
| POST | `/exams/{exam_id}/submit` | `{answers: [{q_index, answer, marked_unfamiliar}]}` → 成績與逐題解析 |
| POST | `/translations` | `{user_id}` → 一題中翻英 |
| POST | `/translations/{id}/submit` | `{text}` → LLM 批改結果 |
| GET | `/stats?user_id=` | rating、段位、推估 TOEFL、rating 成長曲線、正確率、練習量、弱點字／考點 top-N |
| GET | `/heatmap?user_id=` | `{item_id, p_eff, unfamiliar_score}[]`（供之後前端視覺化） |

答案與 explanation 在交卷前不下發。`exam_id` 對應的正解暫存在後端
（記憶體 dict 或 `exams` 暫存表）。

---

## 10. 出題流水線（`orchestrator.py`）

```python
async def build_exam(user_id, question_type, n=10):
    targets = sampler.pick_targets(user_id, question_type, n)      # 一次抽 n 個
    tasks   = [build_question(t, question_type) for t in targets]
    return await asyncio.gather(*tasks)                            # 並行生成

async def build_question(target, question_type):
    options, answer_index, sources = distractor.build_options(target, question_type)
    for _ in range(2):
        raw = await generator.generate(target, options, question_type)
        if validator.check(raw, target, options, question_type):
            return assemble(target, options, answer_index, raw, sources)
    return fallback(target, options)          # 降級題型
```

批改與狀態更新（交卷時）：
```python
for ans in answers:
    score = grader.grade(question, ans)                    # 客觀題純本地比對
    db.insert_review(...)                                  # append-only
    state.update(user_id, target, score, ans.marked_unfamiliar)
```

---

## 11. CLI 狀態機（`frontend/`）

```
WELCOME ─username→ MENU ─選題型→ LOADING ─10題→ EXAM ─交卷→ RESULT ─→ REVIEW
                    ▲              │(失敗)                              │
                    └──────────── ERROR ◀──────────────────────────────┘
```
- 狀態 = Textual `Screen`，轉移 = `push_screen` / `pop_screen`
- 共用 ctx（username、user_id、exam）掛在 `App` 上
- LOADING 用 `@work` 背景 worker 呼叫 API，顯示「出題中 n/10」
- EXAM 內部狀態：目前題號、每題暫存答案、`u` 標記「其實不會」、可前後跳題、交卷確認
- 所有 HTTP 只在 `api.py`；screen 不知道 HTTP 存在
- 強制 UTF-8 輸出（Windows cp950 相容）；提供 `--plain` 純文字模式備援

---

## 12. 安裝與啟動

`init.py`（純標準庫）：
1. 檢查 Python ≥ 3.10
2. `venv.create("venv", with_pip=True)`
3. `subprocess.run([venv_python, "-m", "pip", "install", "-r", "requirements.txt"])`
   （`venv_python` 依 `sys.platform`：`venv/bin/python` 或 `venv\Scripts\python.exe`）
4. 互動寫 `.env`：提示輸入 API key，Enter 跳過或格式不符 → `LLM_PROVIDER=mock`；
   由前綴自動判斷 provider（`AIza`→gemini、`gsk_`→groq）
5. 印出下一步指令

`run.py`（純標準庫）：sanity check（venv、依賴、`.env`、`app.db`——缺 DB 則自動
seed）→ 背景啟動 FastAPI → `subprocess` 呼叫 venv 的 `textual serve frontend/toefl.py`
→ 印出網址提示使用者在瀏覽器開啟。

`.env`：
```ini
LLM_PROVIDER=gemini    # gemini | groq | mock
LLM_API_KEY=
LLM_MODEL=gemini-2.0-flash
```

---

## 13. 有意識砍掉的功能（MVP 範圍外）

Auth（密碼）、placement test、完整 FSRS、單字卡與 AI collocation、
heat map 視覺化、false-positive 以外的標記、Reading／Listening 題型、
React 前端、雲端部署。所有 schema 都已為它們留擴充位（見各節備註）。
