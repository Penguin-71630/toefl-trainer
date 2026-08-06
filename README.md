# toefl-trainer

LLM 輔助英文學習系統（TOEFL ITP + 台大資工英文）。

## M0 Content Pipeline

從三個來源字表建立中央共用詞庫：

- `data/raw/wym.txt` — 王玉梅托福詞彙（pdftotext -layout 抽取）
- `data/raw/toefl_txt.txt` — mahavivo TOEFL.txt
- `data/raw/l6.pdf` / `l6.txt` — 高中英文參考詞彙表 第六級

### 執行

```bash
pip install opencc-python-reimplemented wordfreq
python3 pipeline/parse_wym.py
python3 pipeline/parse_toefl_txt.py
python3 pipeline/parse_l6.py
python3 pipeline/merge.py
python3 pipeline/quality_report.py
```

### 輸出

- `data/intermediate/*.json` — 各來源原始 parse 結果（可稽核、可重跑）
- `data/output/vocabulary.json` — 最終詞庫（schema 見設計文件）
- `data/output/ai_todo.json` — 待 AI 離線生成清單（缺 gloss / 缺 thesaurus）
- `data/output/merge_conflicts.json` — 合併決策記錄
- `data/output/quality_report.md` — 品質報告

### difficulty 定義

`difficulty = log2(rank)`；rank 取自 COCA 20,000，查無者以 wordfreq Zipf
頻率經「COCA∩wordfreq 交集字 zipf-bin 中位數單調映射」校準換算。
