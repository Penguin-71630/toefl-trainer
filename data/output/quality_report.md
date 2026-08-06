# M0 Content Pipeline 品質報告

## 總量統計

- 總 item 數：**7324**（單字 7111、片語 213）
- 總 sense 數：9139

## 來源交集

- toefl_txt + wym: 2383
- wym: 2275
- toefl_txt: 1654
- l6: 402
- l6 + toefl_txt + wym: 319
- l6 + toefl_txt: 154
- l6 + wym: 137

## 詞性分布

- n: 4098
- v: 2328
- adj: 2256
- adv: 230
- phr: 216
- prep: 8
- interj: 2
- conj: 1

## difficulty

- rank 來源：COCA 6137、wordfreq 校準 1149、查無（difficulty=NULL）38
- 分布：min 6.13 / median 12.99 / max 15.68
- 校準方式：COCA∩wordfreq 交集字做 zipf-bin 中位數單調映射（非參數），尾端以 Zipf 定律斜率外插

## word family

- 1198 個家族，涵蓋 3059 個單字（規則式 stem 啟發法，有少量誤併如 retail/tailor，之後可 AI 校正）

## AI/WordNet 補全狀態

- 缺 gloss：**0** 字（AI 生成已套用，生成清單見 gloss_fill_report.json 供抽查）
- 缺 thesaurus：**1992** 字（WordNet 補全已套用且限字集宇集內，剩餘為 WordNet 無在集同義字者，保留空陣列，抽樣時過濾）

## 異常與損耗

- wym parse 異常行：284（多為跨行折行的同義字/釋義，影響少數 entry 的 thesaurus 完整度）
- l6 parse 異常 cell：3
- 合併衝突記錄：2709（wym 與 toefl_txt 同字時採 wym，toefl_txt 義項捨棄，全部記錄在 merge_conflicts.json）

## 已知限制

- 片語庫目前僅 213 條（wym 词组欄），台大愛考的 phrasal verbs 覆蓋不足，之後從考古題與片語表擴充
- wym 跨行折行造成約 3–5% entry 的同義字欄不完整（列入 need_thesaurus 補全）
- `exam_tags` 初版全部為 toefl_itp，ntu_a 待考古題標註