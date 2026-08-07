"""Hand-authored fixture questions for mock mode (no API key / quota saver).

Every entry is pushed through the SAME validator as live LLM output, then
assembled into complete question payloads (options, answer_index, markable)
by the real pipeline code. Target/option data comes from the seeded DB with
a fixed random seed so the authored sentences match the sampled targets.

Usage:  python pipeline/handmade_fixtures.py
"""

import json
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from backend import config, db, distractor, markable, sampler, validator  # noqa: E402

SEED = 42

CLOZE = {
    "eligible": "Only students who have completed all core courses are ______ for the advanced seminar in the spring term.",
    "seasoning": "The chef insisted that fresh herbs, rather than any packaged ______, gave the soup its distinctive flavor.",
    "consensus": "After hours of debate, the committee finally reached a ______ on the budget proposal for next year.",
    "overcrowd": "City officials worry that the new stadium will ______ the narrow streets of the historic district on game days.",
    "faithful": "Every Sunday morning, the ______ gather at the small chapel on the hill to attend the service together.",
    "mechanics": "Students in the engineering program must master the basic principles of ______ before studying bridge design.",
    "spectacle": "The annual fireworks display over the harbor is a ______ that attracts thousands of visitors every summer.",
    "pure": "The laboratory requires ______ samples of the mineral, since even tiny impurities can distort the results.",
    "identical": "The two manuscripts are nearly ______ in wording, which suggests that one was copied directly from the other.",
    "ethnic": "The museum's new exhibit celebrates the ______ diversity of the region through costumes, music, and food.",
}

CLOZE_EXPL = {
    "eligible": "eligible「有資格的」符合語境：完成必修課程才「有資格」修進階課。melodious 是「悅耳的」、noisy 是「吵鬧的」、detrimental 是「有害的」，皆與資格無關。",
    "seasoning": "seasoning「調味料」與新鮮香草對比。mushroom 是「蘑菇」、accompaniment 是「伴隨物」、secret 是「祕密」，都無法與 packaged 搭配表達調味料。",
    "consensus": "reach a consensus「達成共識」是固定搭配。chunk 是「大塊」、duration 是「持續時間」、undergraduate 是「大學生」，皆不合語意。",
    "overcrowd": "overcrowd「使過度擁擠」符合球賽日街道壅塞的語境。endanger 是「危及」、erupt 是「爆發」、embarrass 是「使尷尬」。",
    "faithful": "the faithful「信徒（總稱）」與教堂禮拜的語境相符。liaison 是「聯絡」、violation 是「違反」、flock 雖可指教區信眾但需說 the flock of...，此處 the ______ gather 以 the faithful 最自然。",
    "mechanics": "mechanics「力學」是橋梁設計的基礎學科。apology 是「道歉」、melody 是「旋律」、precedent 是「先例」。",
    "spectacle": "spectacle「奇觀」形容煙火表演。staircase 是「樓梯」、steak 是「牛排」、friction 是「摩擦」。",
    "pure": "pure「純淨的」與後文 impurities（雜質）呼應。formal 是「正式的」、primary 是「主要的」、composed 是「鎮定的」。",
    "identical": "identical「完全相同的」與 copied directly 呼應。devoted 是「忠誠的」、literary 是「文學的」、indigenous 是「本土的」。",
    "ethnic": "ethnic diversity「族群多樣性」為固定搭配，與服飾、音樂、食物的展覽內容相符。sectional 是「部分的」、prime 是「主要的」、square 是「方形的」。",
}

SYNONYM = {
    "corruption": "The journalist spent two years documenting the corruption that had spread through the city's licensing offices.",
    "schedule": "The printed schedule on the station wall lists every departure between six in the morning and midnight.",
    "horizontal": "The painter used a ruler to keep the horizontal lines of the fence perfectly straight across the canvas.",
    "fixed": "Residents of the dormitory pay a fixed monthly fee that does not change with the amount of electricity they use.",
    "bronze": "Archaeologists uncovered several tools made of bronze buried beneath the foundations of the ancient temple.",
    "projecting": "Sailors tied their ropes to the projecting beams that extended well beyond the edge of the old wooden pier.",
    "donate": "Local businesses agreed to donate computers and desks to the elementary school after the flood damaged its classrooms.",
    "plantation": "During the eighteenth century, the coastal plantation produced rice and indigo for export to European markets.",
    "spare": "Wise travelers always carry a spare battery for their cameras when hiking in remote mountain areas.",
    "incentive": "The company offered a cash bonus as an incentive for employees who proposed ways to reduce waste.",
}

SYNONYM_EXPL = {
    "corruption": "corruption 在此指「貪腐」，與 fraud（欺詐、舞弊）意思最接近。graph 是「圖表」、rectangle 是「長方形」、mistress 是「女主人」。",
    "schedule": "schedule 指「時刻表」，agenda（議程表）意思最接近。arrange 是動詞「安排」、spectacle 是「奇觀」、reference 是「參考」。",
    "horizontal": "horizontal「水平的」與 level（平的、水平的）最接近。moderate 是「適度的」、generic 是「通用的」、mobile 是「可移動的」。",
    "fixed": "fixed 在此指「固定不變的」，established（既定的）最接近。subtle 是「微妙的」、accessible 是「可達的」、relevant 是「相關的」。",
    "bronze": "bronze「青銅」對應 Bronze Age 相關詞彙；此處選項中 Bronze Age（青銅時代）最直接相關。circulation 是「流通」、dolphin 是「海豚」、absorption 是「吸收」。",
    "projecting": "projecting「突出的」與 protruding（突出的）同義。periodic 是「週期的」、subjected 是「受支配的」、enduring 是「持久的」。",
    "donate": "donate「捐贈」與 grant（授予、給予）最接近。rip 是「撕裂」、interrogate 是「審問」、isolate 是「隔離」。",
    "plantation": "plantation「種植園」本質上是大型農場，與 farm 最接近。torrent 是「激流」、adobe 是「土磚」、stray 是「流浪的」。",
    "spare": "spare「備用的」與 extra（額外的）最接近。avid 是「熱切的」、interconnected 是「互聯的」、save 是動詞「節省」。",
    "incentive": "incentive「誘因、動機」與 motivation（動機）最接近。trout 是「鱒魚」、code 是「代碼」、perception 是「感知」。",
}

STRUCTURE = {
    33: {
        "full_sentence": "After the merger failed, the board decided to pursue another strategy for entering the Asian market.",
        "stem": "After the merger failed, the board decided to pursue ______ for entering the Asian market.",
        "correct_option": "another strategy",
        "wrong_options": [
            {"text": "another strategies", "error_pattern": "another 後誤接複數"},
            {"text": "other strategy", "error_pattern": "other/the other 特指泛指混淆"},
            {"text": "the another strategy", "error_pattern": "other/the other 特指泛指混淆"},
        ],
        "explanation": "another 後必須接單數可數名詞，故 another strategy 正確。(B) another 不可接複數；(C) other 接單數需加冠詞；(D) another 前不可再加 the。",
    },
    18: {
        "full_sentence": "The tour guide explained where the ancient artifacts had been discovered during the excavation.",
        "stem": "The tour guide explained ______ during the excavation.",
        "correct_option": "where the ancient artifacts had been discovered",
        "wrong_options": [
            {"text": "where had the ancient artifacts been discovered", "error_pattern": "間接問句誤用倒裝"},
            {"text": "where did the ancient artifacts be discovered", "error_pattern": "間接問句殘留助動詞 do/does/did"},
            {"text": "where were the ancient artifacts discovered they", "error_pattern": "間接問句誤用倒裝"},
        ],
        "explanation": "間接問句用直述語序：疑問詞 + 主詞 + 動詞。(B) 誤用倒裝；(C) 殘留助動詞 did；(D) 倒裝且句尾多出代名詞。",
    },
    30: {
        "full_sentence": "Each of the laboratory technicians must submit his or her safety report before leaving the building.",
        "stem": "Each of the laboratory technicians must submit ______ safety report before leaving the building.",
        "correct_option": "his or her",
        "wrong_options": [
            {"text": "their", "error_pattern": "each/every 先行詞誤配 their（依 ITP 規範判錯）"},
            {"text": "him or her", "error_pattern": "主格/受格/所有格混用"},
            {"text": "they", "error_pattern": "主格/受格/所有格混用"},
        ],
        "explanation": "each 為單數先行詞，ITP 規範要求用 his or her。(B) their 是複數；(C)(D) 需要所有格而非受格/主格。",
    },
    16: {
        "full_sentence": "The bridge, designed by a famous Swiss engineer, has carried traffic across the river for over a century.",
        "stem": "The bridge, ______ by a famous Swiss engineer, has carried traffic across the river for over a century.",
        "correct_option": "designed",
        "wrong_options": [
            {"text": "was designed", "error_pattern": "減化後殘留 be 動詞"},
            {"text": "designing", "error_pattern": "主動/被動分詞選錯"},
            {"text": "is designed", "error_pattern": "減化後殘留 be 動詞"},
        ],
        "explanation": "關係子句 which was designed 減化後只留過去分詞 designed。(B)(D) 殘留 be 動詞造成雙動詞；(C) 橋是「被設計」，需被動分詞。",
    },
    41: {
        "full_sentence": "The Grand Canyon is one of the most spectacular natural phenomena in North America.",
        "stem": "The Grand Canyon is one of the most spectacular natural ______ in North America.",
        "correct_option": "phenomena",
        "wrong_options": [
            {"text": "phenomenon", "error_pattern": "one of the 後誤用單數"},
            {"text": "phenomenons", "error_pattern": "不規則複數形式誤用（phenomenon/phenomena）"},
            {"text": "phenomena's", "error_pattern": "不規則複數形式誤用（phenomenon/phenomena）"},
        ],
        "explanation": "one of the + 複數名詞；phenomenon 的複數是不規則的 phenomena。(B) 單數；(C) 錯誤複數形；(D) 誤加所有格。",
    },
    21: {
        "full_sentence": "Many commuters wish that the subway system extended farther into the northern suburbs.",
        "stem": "Many commuters wish that the subway system ______ farther into the northern suburbs.",
        "correct_option": "extended",
        "wrong_options": [
            {"text": "extends", "error_pattern": "wish 後誤用現在式"},
            {"text": "will extend", "error_pattern": "wish 後誤用現在式"},
            {"text": "is extending", "error_pattern": "wish 後誤用現在式"},
        ],
        "explanation": "wish 表達與現在事實相反的願望，子句用過去式 extended。(B)(C)(D) 皆為現在／未來式，不符假設語氣。",
    },
    10: {
        "full_sentence": "The old lighthouse has been converted into a maritime museum that attracts many tourists.",
        "stem": "The old lighthouse ______ into a maritime museum that attracts many tourists.",
        "correct_option": "has been converted",
        "wrong_options": [
            {"text": "has being converted", "error_pattern": "has being／is been 誤用"},
            {"text": "is been converted", "error_pattern": "has being／is been 誤用"},
            {"text": "has been converting", "error_pattern": "has being／is been 誤用"},
        ],
        "explanation": "現在完成被動語態為 has been + 過去分詞。(B) has 後不可接 being；(C) is 後不可接 been；(D) 主動進行式不符「被改建」語意。",
    },
    3: {
        "full_sentence": "Because the harvest was unusually poor, grain prices rose sharply throughout the region.",
        "stem": "______, grain prices rose sharply throughout the region.",
        "correct_option": "Because the harvest was unusually poor",
        "wrong_options": [
            {"text": "Because of the harvest was unusually poor", "error_pattern": "despite/because of 後誤接子句"},
            {"text": "Because the unusually poor harvest", "error_pattern": "although/because 後誤接名詞片語"},
            {"text": "Because of being the harvest unusually poor", "error_pattern": "despite/because of 後誤接子句"},
        ],
        "explanation": "because 是連接詞，後接完整子句。(B) because of 是介系詞，不可接子句；(C) because 後不可只接名詞片語；(D) 結構錯亂。",
    },
    1: {
        "full_sentence": "The recent discovery of water ice on the moon has renewed interest in lunar exploration.",
        "stem": "The recent discovery of water ice on the moon ______ interest in lunar exploration.",
        "correct_option": "has renewed",
        "wrong_options": [
            {"text": "renewing", "error_pattern": "選項造成句子缺動詞"},
            {"text": "it has renewed", "error_pattern": "主詞重複（名詞 + 代名詞疊用）"},
            {"text": "has renewed it is", "error_pattern": "選項造成雙動詞（兩個限定動詞無連接詞）"},
        ],
        "explanation": "句子需要限定動詞 has renewed。(B) 分詞不能當主要動詞；(C) it 與主詞重複；(D) 出現兩個限定動詞。",
    },
    26: {
        "full_sentence": "The climate of southern Spain is much milder than that of northern Scotland.",
        "stem": "The climate of southern Spain is much milder than ______.",
        "correct_option": "that of northern Scotland",
        "wrong_options": [
            {"text": "northern Scotland", "error_pattern": "比較對象不對稱（氣候比國家）"},
            {"text": "those of northern Scotland", "error_pattern": "that of/those of 單複數錯誤"},
            {"text": "it is northern Scotland", "error_pattern": "比較對象不對稱（氣候比國家）"},
        ],
        "explanation": "氣候要與氣候比較：that of = the climate of。(B) 拿氣候比地區；(C) that 指單數 climate，不可用 those；(D) 結構錯誤。",
    },
}

WRITTEN_EXPRESSION = {
    33: {
        "correct_version": "The curator plans to exhibit another painting from the museum's permanent collection next month.",
        "segments": ["plans to exhibit", "another paintings", "permanent collection", "next month"],
        "wrong_index": 1,
        "corrected_segment": "another painting",
        "explanation": "another 後必須接單數可數名詞：another paintings 應改為 another painting。",
    },
    18: {
        "full_note": "indirect question order",
        "correct_version": "The report does not specify when the committee reached its final decision on the funding request.",
        "segments": ["does not specify", "when did the committee reach", "its final decision", "funding request"],
        "wrong_index": 1,
        "corrected_segment": "when the committee reached",
        "explanation": "間接問句用直述語序：when did the committee reach 應改為 when the committee reached。",
    },
    30: {
        "correct_version": "Every student in the physics course must bring his or her own calculator to the final examination.",
        "segments": ["Every student", "must bring", "their own calculator", "final examination"],
        "wrong_index": 2,
        "corrected_segment": "his or her own calculator",
        "explanation": "every 為單數先行詞，依 ITP 規範代名詞用 his or her，不可用 their。",
    },
    16: {
        "correct_version": "The novel written by the young author quickly became one of the best sellers of the decade.",
        "segments": ["The novel", "was written by", "quickly became", "of the decade"],
        "wrong_index": 1,
        "corrected_segment": "written by",
        "explanation": "關係子句減化後不可殘留 be 動詞：was written by 應改為 written by。",
    },
    41: {
        "correct_version": "Yellowstone is home to several active geysers, making it one of the most studied volcanic areas on Earth.",
        "segments": ["is home to", "several active geyser", "most studied", "on Earth"],
        "wrong_index": 1,
        "corrected_segment": "several active geysers",
        "explanation": "several 後接複數名詞：several active geyser 應改為 several active geysers。",
    },
    21: {
        "correct_version": "Many farmers wish that the drought had ended before the planting season began in April.",
        "segments": ["Many farmers", "wish that", "the drought has ended", "season began"],
        "wrong_index": 2,
        "corrected_segment": "the drought had ended",
        "explanation": "wish 對過去事實相反的願望用過去完成式：has ended 應改為 had ended。",
    },
    10: {
        "correct_version": "The ancient manuscript has been preserved in a climate-controlled vault since its discovery in 1947.",
        "segments": ["ancient manuscript", "has being preserved", "climate-controlled vault", "its discovery"],
        "wrong_index": 1,
        "corrected_segment": "has been preserved",
        "explanation": "現在完成被動語態為 has been + 過去分詞：has being preserved 應改為 has been preserved。",
    },
    3: {
        "correct_version": "Despite the heavy rainfall, the outdoor concert continued as scheduled until nearly midnight.",
        "segments": ["Despite the heavy rainfall was", "outdoor concert", "as scheduled", "nearly midnight"],
        "wrong_index": 0,
        "corrected_segment": "Despite the heavy rainfall",
        "explanation": "despite 是介系詞，後接名詞片語，不可接子句：Despite the heavy rainfall was 應改為 Despite the heavy rainfall。",
    },
    1: {
        "correct_version": "The theory of continental drift explains why similar fossils appear on continents separated by vast oceans.",
        "segments": ["The theory of continental drift", "it explains why", "similar fossils", "separated by"],
        "wrong_index": 1,
        "corrected_segment": "explains why",
        "explanation": "主詞 The theory 之後不可再用代名詞 it 重複主詞：it explains why 應改為 explains why。",
    },
    26: {
        "correct_version": "The population of California is considerably larger than that of any other state in the country.",
        "segments": ["population of California", "considerably larger", "than any other state", "in the country"],
        "wrong_index": 2,
        "corrected_segment": "than that of any other state",
        "explanation": "人口要與人口比較，需用 that of：than any other state 應改為 than that of any other state。",
    },
}


def main() -> None:
    random.seed(SEED)
    conn = db.ensure_db(":memory:")
    markable.build_index(conn)
    cur = conn.execute(
        "INSERT INTO users (username, rating, created_at) VALUES ('x', ?, ?)",
        (config.RATING_INIT, db.now_iso()))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id=?",
                        (cur.lastrowid,)).fetchone()

    store: dict[str, list[dict]] = {t: [] for t in (
        "cloze", "synonym", "structure", "written_expression")}

    for qtype, sentences, expls in (("cloze", CLOZE, CLOZE_EXPL),
                                    ("synonym", SYNONYM, SYNONYM_EXPL)):
        targets = sampler.pick_vocab_targets(conn, user, qtype, 10)
        for target in targets:
            if target["word"] not in sentences:
                raise SystemExit(
                    f"{qtype}: sampled '{target['word']}' has no authored "
                    "sentence — re-run with the same SEED or add it")
            options, answer_index = (
                distractor.cloze_options(conn, target) if qtype == "cloze"
                else distractor.synonym_options(conn, target))
            raw = {"sentence": sentences[target["word"]],
                   "explanation": expls[target["word"]]}
            reason = validator.check(raw, target, options, qtype)
            if reason:
                raise SystemExit(f"{qtype} '{target['word']}': {reason}")
            store[qtype].append({
                "question_type": qtype,
                "item_id": target["item_id"],
                "sense_index": target["sense_index"],
                "word": target["word"],
                "gloss": target["sense"].get("gloss", ""),
                "item_rating": target["rating"],
                "sentence": raw["sentence"],
                "options": options,
                "answer_index": answer_index,
                "explanation": raw["explanation"],
                "markable": markable.find_markable(raw["sentence"]),
                "generated_by": "handmade:fixture",
            })

    grammar_targets = sampler.pick_grammar_targets(conn, user, 10)
    for target in grammar_targets:
        gid = target["grammar_point_id"]
        raw = dict(STRUCTURE[gid])
        reason = validator.check(raw, target, None, "structure")
        if reason:
            raise SystemExit(f"structure gp{gid}: {reason}")
        options = [raw["correct_option"]] + [w["text"]
                                             for w in raw["wrong_options"]]
        order = list(range(4))
        random.shuffle(order)
        store["structure"].append({
            "question_type": "structure",
            "grammar_point_id": gid,
            "grammar_point": target["name"],
            "item_rating": config.GRAMMAR_DEFAULT_RATING,
            "sentence": raw["stem"],
            "options": [options[i] for i in order],
            "answer_index": order.index(0),
            "explanation": raw["explanation"],
            "markable": markable.find_markable(raw["stem"]),
            "generated_by": "handmade:fixture",
        })

        we = dict(WRITTEN_EXPRESSION[gid])
        we["error_pattern"] = target["error_pattern"] = "handmade"
        target_we = dict(target, error_pattern="handmade")
        reason = validator.check(we, target_we, None, "written_expression")
        if reason:
            raise SystemExit(f"written_expression gp{gid}: {reason}")
        store["written_expression"].append({
            "question_type": "written_expression",
            "grammar_point_id": gid,
            "grammar_point": target["name"],
            "item_rating": config.GRAMMAR_DEFAULT_RATING,
            "sentence": we["_display_sentence"],
            "segments": we["segments"],
            "segment_offsets": we["_segment_offsets"],
            "corrected_segment": we["corrected_segment"],
            "answer_index": we["wrong_index"],
            "explanation": we["explanation"],
            "markable": markable.find_markable(we["_display_sentence"]),
            "generated_by": "handmade:fixture",
        })

    config.FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.FIXTURES_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=1))
    for qtype, questions in store.items():
        print(f"{qtype}: {len(questions)}")
    print(f"Wrote {config.FIXTURES_PATH}")


if __name__ == "__main__":
    main()
