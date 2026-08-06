"""Generate the M0 quality report (markdown) from pipeline outputs."""

import json
import statistics
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "output"
INTER = BASE / "data" / "intermediate"


def main():
    vocab = json.load(open(OUT / "vocabulary.json"))
    todo = json.load(open(OUT / "ai_todo.json"))
    conflicts = json.load(open(OUT / "merge_conflicts.json"))
    wym_anom = json.load(open(INTER / "wym.json"))["anomalies"]
    l6_anom = json.load(open(INTER / "l6.json"))["anomalies"]

    src_counter = Counter()
    for it in vocab:
        src_counter[tuple(sorted(it["sources"]))] += 1
    pos_counter = Counter(s["part_of_speech"] for it in vocab for s in it["senses"])
    rank_src = Counter(it["_rank_source"] for it in vocab)
    diffs = [it["difficulty"] for it in vocab if it["difficulty"]]
    phrases = [it for it in vocab if it["phrase_attribute"]]
    fam_words = sum(1 for it in vocab if it["word_family_id"])
    fams = len({it["word_family_id"] for it in vocab if it["word_family_id"]})
    no_thes = len(todo["need_thesaurus"])
    no_gloss = len(todo["need_meaning"])

    lines = [
        "# M0 Content Pipeline 品質報告", "",
        "## 總量統計", "",
        f"- 總 item 數：**{len(vocab)}**（單字 {len(vocab)-len(phrases)}、片語 {len(phrases)}）",
        f"- 總 sense 數：{sum(len(it['senses']) for it in vocab)}", "",
        "## 來源交集", "",
    ]
    for k, v in sorted(src_counter.items(), key=lambda x: -x[1]):
        lines.append(f"- {' + '.join(k)}: {v}")
    lines += [
        "", "## 詞性分布", "",
        *(f"- {p}: {c}" for p, c in pos_counter.most_common()),
        "", "## difficulty", "",
        f"- rank 來源：COCA {rank_src['coca']}、wordfreq 校準 {rank_src['zipf']}、"
        f"查無（difficulty=NULL）{rank_src['none']}",
        f"- 分布：min {min(diffs)} / median {round(statistics.median(diffs),2)} / max {max(diffs)}",
        "- 校準方式：COCA∩wordfreq 交集字做 zipf-bin 中位數單調映射（非參數），"
        "尾端以 Zipf 定律斜率外插",
        "", "## word family", "",
        f"- {fams} 個家族，涵蓋 {fam_words} 個單字（規則式 stem 啟發法，"
        "有少量誤併如 retail/tailor，之後可 AI 校正）",
        "", "## 待 AI 生成（離線一次性）", "",
        f"- 缺 gloss（need_meaning）：**{no_gloss}** 字（L6 獨有 + wym 片語欄）",
        f"- 缺 thesaurus（need_thesaurus）：**{no_thes}** 字",
        "- 清單見 `ai_todo.json`；生成後須過濾：同義字必須在字集宇集內",
        "", "## 異常與損耗", "",
        f"- wym parse 異常行：{len(wym_anom)}（多為跨行折行的同義字/釋義，"
        "影響少數 entry 的 thesaurus 完整度）",
        f"- l6 parse 異常 cell：{len(l6_anom)}",
        f"- 合併衝突記錄：{len(conflicts)}（wym 與 toefl_txt 同字時採 wym，"
        "toefl_txt 義項捨棄，全部記錄在 merge_conflicts.json）",
        "", "## 已知限制", "",
        "- 片語庫目前僅 213 條（wym 词组欄），台大愛考的 phrasal verbs 覆蓋不足，"
        "之後從考古題與片語表擴充",
        "- wym 跨行折行造成約 3–5% entry 的同義字欄不完整（列入 need_thesaurus 補全）",
        "- `exam_tags` 初版全部為 toefl_itp，ntu_a 待考古題標註",
    ]
    (OUT / "quality_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
