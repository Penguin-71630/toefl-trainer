"""Static instruction pages: question types and the rating system."""

from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

QUIZ_TEXT = """\
[bold]Question Types 題型說明[/bold]

[bold]Cloze — 字彙填空[/bold]
句子挖掉一個字，從 (A)–(D) 選出最適合的字。干擾項與正解詞性相同、難度相近。

[bold]Synonym — 同義詞[/bold]
給一個句子與其中的目標字，選出「在此語境下」意思最接近的字。
注意多義字陷阱：某選項可能是目標字另一個義項的同義詞。

[bold]Structure — 句構選擇（TOEFL ITP Section 2 Part A）[/bold]
句子挖掉一個結構成分，選出使句子文法完整的選項。

[bold]Written Expression — 挑錯（TOEFL ITP Section 2 Part B）[/bold]
句中四個劃底線片段 A–D，找出文法錯誤的那一個。

[bold]共同規則[/bold]
- 每場 10 題，右上角顯示經過時間（不限時，僅記錄）。
- (E) I don't know：不確定就選它——答錯不倒扣，且系統會把該題目標
  自動標記為「不熟」，之後更常出給你練。
- 作答中可用游標把句中任何不熟的單字標記起來（詳見 Quiz 畫面按鍵說明）。

按 q 返回選單
"""

RATING_TEXT = """\
[bold]Rating System 說明[/bold]

本系統採 Codeforces 式 Elo：每場 quiz 相當於一場 contest，10 題一起結算。
每題有預期答對率 E（由你的 rating 與該題 rating 決定），
rating 變化 = K × Σ(實際得分 − E)。贏過預期就漲，輸給預期就掉。

[bold]段位[/bold]
  < 1200      Newbie
  1200–1399   Pupil
  1400–1599   Specialist
  1600–1899   Expert
  1900–2099   Candidate Master
  2100–2399   Master        ≈ TOEFL ITP 627
  2400–2699   Grandmaster   ≈ TOEFL ITP 677（需擴充詞庫才可達）
  2700+       Native Speaker

[bold]與 TOEFL 的關係[/bold]
錨點：rating 2100 ≈ TOEFL ITP 627（每 6 rating ≈ 1 分）。
注意：rating 只反映「字彙與文法」的水準——本系統不練 Listening，
所以推估 TOEFL 分數僅供參考，不是成績預測。

新使用者從 1400（Specialist）開始。單字的 rating 依它在詞庫中的
難度百分位固定標定（1100–2250），文法考點固定 1800。

按 q 返回選單
"""


class _InstructionScreen(Screen):
    BINDINGS = [("q,escape", "app.pop_screen", "Back")]
    TEXT = ""

    def compose(self):
        with VerticalScroll(id="instruction-body"):
            yield Static(self.TEXT)


class QuizInstructionScreen(_InstructionScreen):
    TEXT = QUIZ_TEXT


class RatingInstructionScreen(_InstructionScreen):
    TEXT = RATING_TEXT
