import re


def strip_html(html_text):
    """
    Xóa tag HTML để đọc các thông tin đã lưu trong analysis_html.
    """
    if not html_text:
        return ""

    text = re.sub(r"<br\s*/?>", "\n", str(html_text), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_bool_from_text(text, true_keywords, false_keywords):
    text_lower = strip_html(text).lower()

    for keyword in false_keywords:
        if keyword.lower() in text_lower:
            return False

    for keyword in true_keywords:
        if keyword.lower() in text_lower:
            return True

    return None


def get_water_status_from_analysis(analysis_html):
    """
    Lấy trạng thái có nước / không nước từ analysis_html đã lưu trong DB.
    """

    text = strip_html(analysis_html).lower()

    if "không nước" in text or "khong nuoc" in text or "không có nước" in text:
        return False, "Không nước"

    if "có nước" in text or "co nuoc" in text or "has_water: true" in text:
        return True, "Có nước"

    return None, "Không xác định"


def get_light_status_from_analysis(analysis_html):
    """
    Lấy trạng thái ban ngày / ban đêm từ analysis_html đã lưu trong DB.
    """

    text = strip_html(analysis_html).lower()

    if "ban đêm" in text or "ban dem" in text or "is_night: true" in text:
        return True, "Ban đêm"

    if "ban ngày" in text or "ban ngay" in text or "is_night: false" in text:
        return False, "Ban ngày"

    return None, "Không xác định"


def extract_first_number_after_keywords(text, keywords):
    """
    Tìm số đầu tiên nằm gần các từ khóa.
    Ví dụ:
    - final_depth_score: 42.5
    - Diện tích: 0.493 m²
    """

    clean_text = strip_html(text)

    for keyword in keywords:
        pattern = rf"{keyword}[^0-9\-]*([0-9]+(?:[.,][0-9]+)?)"
        match = re.search(pattern, clean_text, flags=re.IGNORECASE)

        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except Exception:
                pass

    return None


def get_depth_status_from_analysis(analysis_html):
    """
    Lấy trạng thái độ sâu từ analysis_html đã lưu trong DB.
    Ưu tiên đọc chữ: Sâu / Trung bình / Nông.
    Nếu không có chữ thì đọc final_depth_score.
    """

    text = strip_html(analysis_html).lower()

    if "độ sâu cao" in text or "Độ sâu trung bình: sâu" in text or "Độ sâu trung bình: sau" in text:
        return "high", "Sâu"

    if "trung bình" in text or "trung binh" in text:
        return "medium", "Trung bình"

    if "nông" in text or "nong" in text:
        return "low", "Nông"

    depth_score = extract_first_number_after_keywords(
        analysis_html,
        [
            "final_depth_score",
            "điểm độ sâu",
            "diem do sau",
            "depth score",
            "depth_score"
        ]
    )

    if depth_score is None:
        return None, "Không xác định"

    if depth_score >= 35:
        return "high", "Sâu"

    if depth_score >= 15:
        return "medium", "Trung bình"

    return "low", "Nông"


def get_area_status(area_m2):
    """
    Phân loại diện tích ổ gà từ area_m2 đã lưu trong DB.
    Không tính lại từ ảnh.
    """

    try:
        area_m2 = float(area_m2)
    except Exception:
        area_m2 = 0.0

    if area_m2 >= 1.0:
        return "high", "Diện tích lớn"

    if area_m2 >= 0.3:
        return "medium", "Diện tích trung bình"

    if area_m2 > 0:
        return "low", "Diện tích nhỏ"

    return None, "Không xác định"


def evaluate_repair_priority_from_db(
    pothole_count=0,
    area_m2=0.0,
    analysis_html=""
):
    """
    Đánh giá trạng thái hư hỏng từ dữ liệu đã lưu trong database.

    Dữ liệu đầu vào:
    - pothole_count: lấy từ image_count hoặc COUNT ảnh trong pothole_report_images
    - area_m2: lấy từ cột area_m2 trong pothole_report_images
    - analysis_html: lấy từ cột analysis_html trong DB

    Không chạy lại YOLO.
    Không tính lại mask.
    Không đọc lại ảnh.
    """

    try:
        pothole_count = int(pothole_count)
    except Exception:
        pothole_count = 0

    try:
        area_m2 = float(area_m2)
    except Exception:
        area_m2 = 0.0

    has_water, water_text = get_water_status_from_analysis(analysis_html)
    is_night, light_text = get_light_status_from_analysis(analysis_html)
    depth_level, depth_text = get_depth_status_from_analysis(analysis_html)
    area_level, area_text = get_area_status(area_m2)

    risk_score = 0
    reasons = []

    # 1. Tổng số ổ gà / số ảnh báo cáo trong cùng vị trí
    if pothole_count >= 3:
        risk_score += 2
        reasons.append("Khu vực có nhiều ghi nhận ổ gà")
    elif pothole_count >= 1:
        risk_score += 1
        reasons.append("Có ghi nhận ổ gà tại vị trí này")

    # 2. Có nước hay không
    if has_water is True:
        risk_score += 2
        reasons.append("Ổ gà có nước, có thể che khuất độ sâu thực tế")
    elif has_water is False:
        reasons.append("Ổ gà không có nước")

    # 3. Độ sâu
    if depth_level == "high":
        risk_score += 3
        reasons.append("Ổ gà được đánh giá là sâu")
    elif depth_level == "medium":
        risk_score += 2
        reasons.append("Ổ gà có độ sâu trung bình")
    elif depth_level == "low":
        risk_score += 1
        reasons.append("Ổ gà có độ sâu thấp")

    # 4. Ban ngày / ban đêm
    if is_night is True:
        risk_score += 1
        reasons.append("Phát hiện trong điều kiện ban đêm, khả năng quan sát thấp hơn")
    elif is_night is False:
        reasons.append("Phát hiện trong điều kiện ban ngày")

    # 5. Diện tích
    if area_level == "high":
        risk_score += 2
        reasons.append("Diện tích hư hỏng lớn")
    elif area_level == "medium":
        risk_score += 1
        reasons.append("Diện tích hư hỏng ở mức trung bình")
    elif area_level == "low":
        reasons.append("Diện tích hư hỏng nhỏ")

    if risk_score >= 8:
        damage_status = "Rất nghiêm trọng"
        priority = "Khẩn cấp"
        need_urgent_repair = True
        repair_decision = "Cần sửa chữa gấp"
        recommendation = "Nên ưu tiên xử lý ngay vì vị trí này có nguy cơ cao gây mất an toàn giao thông."

    elif risk_score >= 6:
        damage_status = "Nghiêm trọng"
        priority = "Cao"
        need_urgent_repair = True
        repair_decision = "Nên sửa chữa sớm"
        recommendation = "Cần đưa vào danh sách ưu tiên xử lý trong thời gian gần."

    elif risk_score >= 3:
        damage_status = "Trung bình"
        priority = "Trung bình"
        need_urgent_repair = False
        repair_decision = "Cần theo dõi và lên kế hoạch sửa"
        recommendation = "Chưa cần xử lý khẩn cấp nhưng nên theo dõi định kỳ."

    else:
        damage_status = "Nhẹ"
        priority = "Thấp"
        need_urgent_repair = False
        repair_decision = "Chưa cần sửa ngay"
        recommendation = "Có thể tiếp tục theo dõi, chưa cần ưu tiên xử lý."

    return {
        "pothole_count": pothole_count,
        "area_m2": area_m2,
        "area_text": area_text,
        "water_text": water_text,
        "light_text": light_text,
        "depth_text": depth_text,
        "risk_score": risk_score,
        "damage_status": damage_status,
        "priority": priority,
        "need_urgent_repair": need_urgent_repair,
        "repair_decision": repair_decision,
        "recommendation": recommendation,
        "reasons": reasons,
    }


def build_admin_damage_summary_html(summary):
    """
    Tạo HTML để hiển thị trong trang chi tiết báo cáo admin.
    """

    if not summary:
        return ""

    urgent_text = "Có" if summary.get("need_urgent_repair") else "Không"

    reasons = summary.get("reasons", [])
    if reasons:
        reason_html = "<br>".join([f"- {reason}" for reason in reasons])
    else:
        reason_html = "--"

    area_m2 = summary.get("area_m2", 0.0)

    try:
        area_text = f"{float(area_m2):.3f} m²"
    except Exception:
        area_text = "--"

    return f"""
    <div style="
        margin-top:10px;
        padding:10px;
        border-radius:10px;
        background:#F0FDF4;
        border:1px solid #86EFAC;
        color:#064E3B;
    ">

        <b>Tổng diện tích hư hỏng:</b> {area_text}<br>
        <b>Phân loại diện tích:</b> {summary.get("area_text", "--")}<br>

        <b>Điểm nguy cơ:</b> {summary.get("risk_score", "--")}<br>
        <b>Trạng thái hư hỏng:</b> {summary.get("damage_status", "--")}<br>
        <b>Khuyến nghị:</b> {summary.get("recommendation", "--")}<br>
    </div>
    """