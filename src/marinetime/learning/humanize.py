from __future__ import annotations

import re
from typing import Any, Iterable


# English stays visible because the learner needs shipboard/interview vocabulary.
# Vietnamese is the teaching language for explanation and navigation.
_GLOSSARY: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("passage planning", "lập kế hoạch hành trình", ("passage planning",)),
    ("appraisal", "thu thập và đánh giá thông tin trước khi lập tuyến", ("appraisal",)),
    ("planning", "lập và kiểm tra tuyến hành trình", ("planning", "berth-to-berth")),
    ("execution", "thực hiện kế hoạch đã được phê duyệt", ("execution", "approved plan")),
    ("monitoring", "theo dõi tiến trình và vị trí tàu", ("monitoring", "position fixing")),
    ("position fixing", "xác định vị trí tàu", ("position fixing", "position-fixing")),
    ("cross-check", "đối chiếu bằng phương pháp độc lập", ("cross-check", "cross checked", "cross-checked")),
    ("ECDIS", "hệ thống hiển thị hải đồ điện tử và thông tin", ("ecdis",)),
    ("radar", "ra-đa hàng hải", ("radar",)),
    ("COLREG", "Quy tắc phòng ngừa va chạm trên biển", ("colreg", "collision regulation")),
    ("VHF", "vô tuyến VHF", ("vhf",)),
    ("watchkeeping", "trực ca", ("watchkeeping", "watch keeping")),
    ("handover", "bàn giao ca", ("handover", "hand over")),
    ("bunkering", "nhận/nạp nhiên liệu", ("bunkering", "bunker")),
    ("permit to work", "giấy phép làm việc", ("permit to work",)),
    ("enclosed space", "không gian kín", ("enclosed space",)),
    ("purifier / separator", "máy phân ly ly tâm", ("purifier", "separator")),
    ("pump", "bơm", ("pump",)),
    ("boiler", "nồi hơi", ("boiler",)),
    ("air compressor", "máy nén khí", ("compressor",)),
    ("generator", "máy phát điện", ("generator",)),
    ("fuel oil", "dầu nhiên liệu", ("fuel oil",)),
    ("lube oil", "dầu bôi trơn", ("lube oil", "lubricating oil")),
    ("cooling water", "nước làm mát", ("cooling water", "cooling")),
    ("valve", "van", ("valve",)),
    ("bearing", "ổ đỡ / bạc đạn", ("bearing",)),
    ("piston", "pít-tông", ("piston",)),
    ("crankshaft", "trục khuỷu", ("crankshaft",)),
    ("turbocharger", "bộ tăng áp", ("turbocharger",)),
    ("scavenge", "quét khí", ("scavenge",)),
    ("SOLAS", "Công ước quốc tế về an toàn sinh mạng trên biển", ("solas",)),
    ("MARPOL", "Công ước quốc tế ngăn ngừa ô nhiễm do tàu gây ra", ("marpol",)),
    ("STCW", "Công ước về tiêu chuẩn huấn luyện, cấp chứng chỉ và trực ca", ("stcw",)),
    ("ISM Code", "Bộ luật quản lý an toàn quốc tế", ("ism code", "ism")),
)


_VIETNAMESE_CHARS = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệ"
    r"íìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    r"ÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊ"
    r"ÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
)


def contains_vietnamese(text: str) -> bool:
    return bool(_VIETNAMESE_CHARS.search(text))


def _anchor_text(anchor: str) -> str:
    parts = [part.strip() for part in anchor.split("·")]
    if len(parts) < 3:
        return ""
    return parts[-1]


def vietnamese_source_excerpt(anchors: Iterable[str], *, limit: int = 220) -> str | None:
    for anchor in anchors:
        text = _anchor_text(anchor)
        if text and contains_vietnamese(text):
            compact = " ".join(text.split())
            if len(compact) > limit:
                compact = compact[: limit - 1].rstrip() + "…"
            return compact
    return None


def glossary_for_texts(texts: Iterable[str], *, limit: int = 10) -> list[tuple[str, str]]:
    haystack = " ".join(str(text) for text in texts).lower()
    found: list[tuple[str, str]] = []
    for english, vietnamese, needles in _GLOSSARY:
        if any(needle in haystack for needle in needles):
            found.append((english, vietnamese))
        if len(found) >= limit:
            break
    return found


def vietnamese_heading(heading: str) -> str:
    lower = heading.lower()
    mappings = (
        ("four-stage framework", "Khung 4 giai đoạn"),
        ("interview strategy", "Chiến lược trả lời phỏng vấn"),
        ("appraisal", "Appraisal — thu thập và đánh giá thông tin"),
        ("planning", "Planning — lập và kiểm tra tuyến"),
        ("execution", "Execution — thực hiện kế hoạch"),
        ("monitoring", "Monitoring — theo dõi và đối chiếu"),
        ("purifier", "Purifier — máy phân ly"),
        ("separator", "Separator — máy phân ly"),
        ("pump", "Pump — bơm"),
        ("boiler", "Boiler — nồi hơi"),
        ("compressor", "Compressor — máy nén khí"),
        ("generator", "Generator — máy phát điện"),
        ("watchkeeping", "Watchkeeping — trực ca"),
        ("handover", "Handover — bàn giao ca"),
        ("bunkering", "Bunkering — nhận/nạp nhiên liệu"),
        ("enclosed space", "Enclosed space — không gian kín"),
        ("fire", "Fire safety — an toàn cháy"),
        ("valve", "Valve — van"),
        ("bearing", "Bearing — ổ đỡ"),
        ("turbocharger", "Turbocharger — bộ tăng áp"),
    )
    for needle, translated in mappings:
        if needle in lower:
            return translated
    return f"Ý chính — {heading}"


def vietnamese_explanation(
    item: dict[str, Any],
    *,
    heading: str,
    anchors: Iterable[str] = (),
) -> str:
    """Return a conservative learner explanation without inventing new facts.

    This is intentionally not a free-form translation engine. Known marine patterns
    receive a concise Vietnamese explanation; otherwise we reuse Vietnamese source
    speech when available and fall back to a clearly bounded explanation.
    """
    statement = " ".join(str(item.get("statement") or "").split())
    lower = statement.lower()

    if "passage planning" in lower and "four stages" in lower:
        return (
            "Passage planning trong nguồn này được chia thành 4 giai đoạn theo thứ tự: "
            "**Appraisal → Planning → Execution → Monitoring**. Hãy nhớ thứ tự trước, "
            "sau đó mới học việc phải làm trong từng giai đoạn."
        )
    if "appraisal" in lower and any(word in lower for word in ("collect", "information", "before")):
        return (
            "Ở **Appraisal**, ý chính là chưa vội vẽ tuyến. Trước hết phải thu thập và "
            "đánh giá các thông tin liên quan đến chuyến đi mà nguồn đề cập, để có cơ sở "
            "cho bước Planning."
        )
    if "planning" in lower and ("berth-to-berth" in lower or "route" in lower):
        return (
            "Ở **Planning**, nguồn tập trung vào việc xây dựng tuyến **berth-to-berth**, "
            "kiểm tra/validate tuyến và thảo luận trước khi dùng. Đây là phần biến thông "
            "tin đã thu thập thành một kế hoạch hành trình cụ thể."
        )
    if "execution" in lower and "approved plan" in lower:
        return (
            "Ở **Execution**, đội buồng lái thực hiện kế hoạch đã được phê duyệt. Ý cần "
            "nhớ là đây không phải bước tự ý đổi kế hoạch; nguồn đang nói tới việc vận hành "
            "theo kế hoạch đã được thống nhất."
        )
    if "monitoring" in lower and ("position" in lower or "cross-check" in lower):
        return (
            "Ở **Monitoring**, phải theo dõi tàu có đang đi đúng kế hoạch hay không và "
            "đối chiếu vị trí bằng các thông tin/phương pháp mà nguồn nêu. Trọng tâm là "
            "phát hiện sai lệch sớm, không chỉ nhìn một con số rồi bỏ qua việc kiểm tra chéo."
        )
    if "gps" in lower and ("one" in lower or "alone" in lower):
        return (
            "Nguồn đang nhấn mạnh **redundancy**: không nên biến một phương pháp xác định "
            "vị trí thành điểm tựa duy nhất. Đây là cách hiểu từ nội dung creator; khi học "
            "quy trình chính thức vẫn phải đối chiếu tài liệu có thẩm quyền."
        )
    if "purifier" in lower or "separator" in lower:
        return (
            "Phần này nói về **purifier/separator**. Hãy tập trung vào chức năng hoặc hiện "
            "tượng mà nguồn nêu, rồi liên hệ nó với dòng dầu/nước/cặn trong hệ thống. Không "
            "tự suy ra thông số vận hành nếu nguồn chưa cung cấp."
        )
    if "pump" in lower:
        return (
            "Phần này nói về **pump (bơm)**. Khi học, tách ba ý: bơm đang chuyển chất lỏng "
            "nào, qua hệ thống nào, và dấu hiệu/điều kiện nào được nguồn nhắc tới. Chỉ giữ "
            "những chi tiết thật sự có trong nguồn."
        )
    if "watchkeeping" in lower or "watch keeping" in lower or "handover" in lower:
        return (
            "Đây là kiến thức về **watchkeeping / handover**. Mục tiêu là hiểu thông tin nào "
            "phải được nắm và truyền lại giữa các ca theo đúng nội dung nguồn, thay vì học "
            "thuộc một checklist không có ngữ cảnh."
        )
    if "bunker" in lower:
        return (
            "Phần này liên quan đến **bunkering**. Hãy học theo trình tự và điều kiện mà "
            "nguồn thực sự nêu; các bước thao tác thật trên tàu vẫn phải tuân theo SMS, "
            "checklist và lệnh của tàu."
        )
    if "enclosed space" in lower:
        return (
            "Phần này liên quan đến **enclosed space (không gian kín)**. Đây là chủ đề an "
            "toàn cao: dùng nội dung này để hiểu khái niệm và nhận diện rủi ro, không dùng "
            "nó thay cho permit, risk assessment hay quy trình của tàu."
        )
    if "solas" in lower:
        return (
            "**SOLAS** là lớp quy định về an toàn sinh mạng trên biển. Ở ý này, hãy học đúng "
            "điều nguồn đang gắn với SOLAS; đừng biến tên công ước thành câu trả lời chung chung. "
            "Khi cần áp dụng chính thức phải quay về điều khoản/tài liệu có thẩm quyền."
        )
    if "marpol" in lower or "pollution" in lower:
        return (
            "Phần này liên quan đến **MARPOL / pollution prevention**. Hãy tách rõ: nguồn đang "
            "nói về yêu cầu, hành vi hay tình huống nào. Không suy rộng sang toàn bộ quy trình "
            "ngăn ngừa ô nhiễm nếu evidence chỉ hỗ trợ một phần."
        )
    if "stcw" in lower:
        return (
            "**STCW** liên quan đến tiêu chuẩn huấn luyện, chứng chỉ và trực ca. Ý cần nắm ở "
            "đây là phần cụ thể mà nguồn nhắc tới; khi học để thi/phỏng vấn hãy giữ đúng thuật "
            "ngữ English, nhưng giải thích bằng lời của mình thay vì đọc thuộc."
        )
    if "ism" in lower:
        return (
            "Phần này liên quan đến **ISM Code / Safety Management System**. Hãy hiểu mối liên "
            "hệ giữa ý trong nguồn và cách tàu quản lý an toàn; quy trình thao tác thật vẫn phải "
            "theo SMS/checklist của chính tàu."
        )
    if "fire" in lower:
        return (
            "Đây là nội dung về **fire safety**. Khi học, xác định nguồn đang nói về phòng ngừa, "
            "phát hiện hay ứng phó cháy. Không biến một mẹo hoặc kinh nghiệm cá nhân thành trình "
            "tự chữa cháy chính thức."
        )
    if "lifeboat" in lower or "life boat" in lower:
        return (
            "Phần này nói về **lifeboat / survival craft**. Dùng bài để hiểu khái niệm và mục "
            "đích của thiết bị hoặc thao tác mà nguồn nêu; drill/thao tác thật phải theo quy trình "
            "tàu và lệnh của người phụ trách."
        )
    if "drill" in lower or "emergency" in lower:
        return (
            "Đây là nội dung **emergency/drill**. Hãy nhớ vai trò, mục tiêu hoặc hành động mà "
            "nguồn nêu, nhưng khi có tình huống thật phải ưu tiên muster list, emergency plan và "
            "mệnh lệnh trên tàu."
        )
    if "permit to work" in lower:
        return (
            "**Permit to work** là lớp kiểm soát trước khi thực hiện công việc có rủi ro. Hãy "
            "học điều kiện hoặc mục đích mà nguồn nêu; mẫu permit và trình tự phê duyệt thực tế "
            "phụ thuộc SMS của tàu."
        )
    if "generator" in lower:
        return (
            "Phần này nói về **generator (máy phát điện)**. Khi học, xác định hiện tượng/chức "
            "năng nào đang được giải thích và liên hệ nó với tải, nguồn điện hoặc tình trạng máy "
            "chỉ trong phạm vi evidence."
        )
    if "compressor" in lower:
        return (
            "Phần này nói về **air compressor (máy nén khí)**. Hãy tập trung vào chức năng, "
            "dòng khí và dấu hiệu vận hành mà nguồn thực sự nêu; không tự thêm áp suất hay giới "
            "hạn vận hành nếu nguồn chưa cho."
        )
    if "boiler" in lower:
        return (
            "Phần này nói về **boiler (nồi hơi)**. Hãy hiểu quan hệ giữa nước, hơi, đốt và các "
            "tín hiệu/điều kiện mà nguồn đề cập. Thông số và trình tự vận hành thật phải theo "
            "maker manual và SMS."
        )
    if "valve" in lower:
        return (
            "Phần này nói về **valve (van)**. Ý cần nắm là vai trò hoặc trạng thái của van trong "
            "đúng hệ thống mà nguồn mô tả; không suy ra line-up hoàn chỉnh nếu evidence không có."
        )

    source_vi = vietnamese_source_excerpt(anchors)
    if source_vi:
        return (
            f"Nguồn nói bằng tiếng Việt: “{source_vi}”\n\n"
            f"Ý cần nắm ở mục này là **{vietnamese_heading(heading)}**. "
            "Giữ câu tiếng Anh kỹ thuật bên dưới để học đúng thuật ngữ, nhưng không mở "
            "rộng thành quy trình hay kết luận mà nguồn chưa nói."
        )

    return (
        f"Ý cần nắm: **{vietnamese_heading(heading)}**. Marinetime giữ nguyên câu tiếng Anh "
        "kỹ thuật bên dưới để tránh dịch sai thuật ngữ. Phần giải thích này chỉ giúp định "
        "hướng cách học; không bổ sung chi tiết kỹ thuật ngoài nội dung nguồn."
    )


def simple_safety_note(*, safety_count: int, numeric_count: int) -> list[str]:
    if safety_count <= 0 and numeric_count <= 0:
        return []
    notes = [
        "⚠️ **Lưu ý khi học:** đây là tài liệu học và luyện phỏng vấn, không phải lệnh thao tác trên tàu.",
        "Khi áp dụng thực tế, ưu tiên SMS/checklist của tàu, maker manual, standing orders và hướng dẫn của sĩ quan phụ trách.",
    ]
    if numeric_count:
        notes.append(
            "Nếu có con số, luôn kiểm tra lại **đơn vị + điều kiện áp dụng + nguồn gốc con số** trước khi dùng."
        )
    return notes
