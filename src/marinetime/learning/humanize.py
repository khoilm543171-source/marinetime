from __future__ import annotations

import re
from typing import Any, Iterable

from marinetime.authority.verify import is_exact_four_stage_claim


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
    """Render a vetted complete proposition or clearly label an untranslated claim.

    Keyword-triggered prose must never attribute extra details to the source.
    Original English and evidence anchors remain available in the caller's lesson.
    """
    statement = " ".join(str(item.get("statement") or "").split())
    if is_exact_four_stage_claim(statement):
        return (
            "Nguồn liệt kê **4 giai đoạn** của lập kế hoạch hành trình: "
            "**Appraisal → Planning → Execution → Monitoring**."
        )

    source_vi = vietnamese_source_excerpt(anchors)
    if source_vi:
        return (
            f"Trích đoạn tiếng Việt từ bằng chứng: “{source_vi}”\n\n"
            "Đây là trích đoạn để đối chiếu, chưa phải bản diễn giải đã kiểm chứng "
            "của toàn bộ mệnh đề tiếng Anh. Kiểm tra đủ điều kiện và ngữ cảnh trong nguồn."
        )

    return (
        "**Cần duyệt diễn giải tiếng Việt.** Chưa có bản diễn giải được kiểm chứng "
        "cho mệnh đề này. Hãy đối chiếu câu tiếng Anh và bằng chứng gốc, giữ nguyên "
        "phủ định, điều kiện, con số và đơn vị; không tự bổ sung chi tiết kỹ thuật."
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
