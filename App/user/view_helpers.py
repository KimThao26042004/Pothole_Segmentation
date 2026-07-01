def format_brightness(value):
    value = float(value or 0)
    percent = value / 255 * 100
    return f"{percent:.2f}% ({value:.2f}/255)"

def build_analysis_html(depth_info):
    has_water = depth_info.get("has_water", False)
    water_score = depth_info.get("water_info", {}).get("water_score", 0)
    water_color = "#0D47A1" if has_water or water_score >= 2 else "#B71C1C"

    water_info = depth_info.get("water_info", {})
    is_night = water_info.get("is_night", False)
    night_text = "Đúng" if is_night else "Sai"
    night_color = "#6A1B9A" if is_night else "#388E3C"

    depth_level = depth_info.get("depth_level", "Không xác định")
    if depth_level == "Nông":
        depth_color = "#16A34A"
    elif depth_level == "Trung bình":
        depth_color = "#FF9800"
    elif depth_level == "Sâu":
        depth_color = "#D32F2F"
    else:
        depth_color = "#000000"

    left_html = f"""
    <b>THÔNG TIN NƯỚC / ÁNH SÁNG</b><br><br>

    Ảnh ban đêm: <b><span style="color:{night_color};">{night_text}</span></b><br>
    Độ sáng toàn ảnh: <b>{format_brightness(water_info.get('global_mean_v', 0))}</b><br>
    Độ sáng vùng ổ gà: <b>{format_brightness(water_info.get('pothole_mean_v', 0))}</b><br>

    Tỷ lệ vùng tối toàn ảnh: <b>{water_info.get('dark_global_ratio', 0) * 100:.2f}%</b><br>
    Tỷ lệ vùng sáng toàn ảnh: <b>{water_info.get('bright_global_ratio', 0) * 100:.2f}%</b><br>

    Trạng thái nước: <b><span style="color:{water_color};">{'Có nước' if has_water else 'Không có nước'}</span></b><br>
    Điểm nước: <b><span style="color:{water_color};">{water_score}</span></b><br>

    Phản chiếu sáng: <b>{water_info.get('highlight_ratio', 0) * 100:.2f}%</b><br>
    Vùng tối mịn: <b>{water_info.get('dark_smooth_ratio', 0) * 100:.2f}%</b><br>
    Texture thấp: <b>{water_info.get('low_texture_ratio', 0) * 100:.2f}%</b><br>
    """

    right_html = f"""
    <b>THÔNG TIN ĐỘ SÂU</b><br><br>

    Phương pháp: <b>{depth_info.get('depth_method', 'CLAHE brightness')}</b><br>
    Độ sâu tương đối: <b><span style="color:{depth_color};">{depth_level}</span></b><br>
    Độ tin cậy: <b>{depth_info.get('depth_confidence', 'Thấp')}</b><br>
    Điểm độ sâu (cuối cùng): <b>{depth_info.get('depth_score', 0):.2f}</b><br>

    Điểm Depth Anything: <b>{depth_info.get('depth_score_da', 0):.2f}</b><br>
    Điểm viền tối: <b>{depth_info.get('rim_score', 0):.2f}</b><br>
    Điểm tương phản: <b>{depth_info.get('contrast_score', 0):.2f}</b><br>

    Độ sâu TB ổ gà: <b>{depth_info.get('pothole_depth_mean', 0):.3f}</b><br>
    Độ sâu TB mặt đường: <b>{depth_info.get('road_depth_mean', 0):.3f}</b><br>

    Tỷ lệ viền tối: <b>{depth_info.get('dark_rim_ratio', 0) * 100:.2f}%</b><br>

    Độ sáng ổ gà: <b>{format_brightness(depth_info.get('pothole_brightness', 0))}</b><br>
    Độ sáng mặt đường: <b>{format_brightness(depth_info.get('road_brightness', 0))}</b><br>
    """

    return f"""
    <table width="100%" cellspacing="0" cellpadding="6">
        <tr>
            <td width="50%" valign="top" style="border-right:1px solid #7acb8c;">
                {left_html}
            </td>
            <td width="50%" valign="top">
                {right_html}
            </td>
        </tr>
    </table>
    """
