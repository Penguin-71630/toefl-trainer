# toefl-trainer

LLM 輔助英文學習系統（TOEFL ITP + 台大資工英文）。

## Repo 結構

```text
toefl-trainer/
├── README.md                 # pipeline 說明、執行指令、difficulty 定義
├── pipeline/                 # M0 content pipeline（可重跑）
│   ├── parse_wym.py          # 王玉梅 parser
│   ├── parse_toefl_txt.py    # TOEFL.txt parser
│   ├── parse_l6.py           # 高中 L6 parser
│   ├── parse_barrons.py      # Barron's EPUB parser
│   ├── merge.py              # 合併四來源 + 繁化 + difficulty + word family + phrase
│   ├── cleanup.py            # 修 OCR 殘留：截斷詞、拼錯詞、gloss 尾端雜訊
│   ├── morph_difficulty.py   # 構詞折扣：衍生字難度以字根 + 詞綴罰分為上限
│   ├── enrich_thesaurus.py   # WordNet 補 thesaurus（限字集內）
│   ├── apply_ai_gloss.py     # 套用 AI 生成的繁中 gloss
│   └── quality_report.py     # 產出品質報告
└── data/
    ├── vocabulary.json       # 最終詞庫（seed 來源）
    ├── grammar.json          # 文法考點（seed 來源）
    ├── raw/                  # 來源原始檔（wym.txt、TOEFL.txt、COCA、l6.pdf、
    │                         #   barrons.epub、OG ITP pdf+OCR、Elmetaher epub）
    ├── intermediate/         # 各 parser 的中間 JSON + AI gloss 批次檔（可稽核）
    └── output/               # quality_report.md、ai_todo.json、
                              #   merge_conflicts.json、fill reports
```

規劃中：`backend/`（FastAPI：orchestrator、sampler、distractor、LLM gateway）、
`frontend/`（Textual CLI，之後換 React）。`data/vocabulary.json` 與
`data/grammar.json` 是 pipeline 與 backend 的交接點（seed script 從這裡灌 SQLite）。
架構規格見 `docs/mvp-architecture.md`。

## M0 Content Pipeline

從四個來源字表建立中央共用詞庫：

- `data/raw/wym.txt` — 王玉梅托福詞彙（pdftotext -layout 抽取）
- `data/raw/toefl_txt.txt` — mahavivo TOEFL.txt
- `data/raw/l6.pdf` / `l6.txt` — 高中英文參考詞彙表 第六級
- `data/raw/barrons_essential_words.epub` — Barron's Essential Words for the TOEFL
  （500 核心字：英文釋義、精選同義字、衍生詞形、例句）

### 執行

```bash
pip install opencc-python-reimplemented wordfreq nltk
python3 -c "import nltk; nltk.download('wordnet')"
python3 pipeline/parse_wym.py
python3 pipeline/parse_toefl_txt.py
python3 pipeline/parse_l6.py
python3 pipeline/parse_barrons.py
python3 pipeline/merge.py
python3 pipeline/cleanup.py
python3 pipeline/morph_difficulty.py
python3 pipeline/enrich_thesaurus.py
python3 pipeline/apply_ai_gloss.py
python3 pipeline/quality_report.py
```

### 輸出

- `data/intermediate/*.json` — 各來源原始 parse 結果（可稽核、可重跑）
- `data/vocabulary.json` — 最終詞庫（schema 見設計文件）
- `data/output/ai_todo.json` — 待 AI 離線生成清單（缺 gloss / 缺 thesaurus）
- `data/output/merge_conflicts.json` — 合併決策記錄
- `data/output/gloss_fill_report.json` / `thesaurus_report.json` — AI/WordNet 補全記錄（供抽查）
- `data/output/quality_report.md` — 品質報告

### difficulty 定義

`difficulty = log2(rank)`；rank 取自 COCA 20,000，查無者以 wordfreq Zipf
頻率經「COCA∩wordfreq 交集字 zipf-bin 中位數單調映射」校準換算。

## 文法資料來源（grammar_points seed，規劃中）

考點依據鏈：Official Guide to TOEFL ITP Chapter 3（官方考點敘述 + Practice Sets）
→ Elmetaher《ITP Listening, Grammar & Reading》（逐題 Grammar Point 解說 + 變體）
→ 台大資工英文考古題（`ntu_a` 標註）→ 旋元佑文法 coverage audit 補的 7 個 category。
