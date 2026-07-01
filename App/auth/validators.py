import re


def validate_register_data(full_name, username, email, password, confirm_password):
    """
    Kiểm tra dữ liệu đăng ký tài khoản người dùng.

    Trả về:
        list[str]: danh sách lỗi. Nếu list rỗng nghĩa là hợp lệ.
    """

    errors = []

    full_name = str(full_name or "").strip()
    username = str(username or "").strip()
    email = str(email or "").strip()
    password = str(password or "")
    confirm_password = str(confirm_password or "")

    if not full_name:
        errors.append("Vui lòng nhập họ tên.")
    elif len(full_name) < 3:
        errors.append("Họ tên phải có ít nhất 3 ký tự.")

    if not username:
        errors.append("Vui lòng nhập tên đăng nhập.")
    elif not re.match(r"^[A-Za-z0-9_]{4,30}$", username):
        errors.append(
            "Tên đăng nhập phải dài 4-30 ký tự và chỉ gồm chữ, số, dấu gạch dưới."
        )

    if not email:
        errors.append("Vui lòng nhập email.")
    elif not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email):
        errors.append("Email không đúng định dạng.")

    if not password:
        errors.append("Vui lòng nhập mật khẩu.")
    elif len(password) < 8:
        errors.append("Mật khẩu phải có ít nhất 8 ký tự.")
    elif " " in password:
        errors.append("Mật khẩu không được chứa khoảng trắng.")
    elif not re.search(r"[A-Z]", password):
        errors.append("Mật khẩu cần có ít nhất 1 chữ hoa.")
    elif not re.search(r"[a-z]", password):
        errors.append("Mật khẩu cần có ít nhất 1 chữ thường.")
    elif not re.search(r"[0-9]", password):
        errors.append("Mật khẩu cần có ít nhất 1 chữ số.")
    elif not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Mật khẩu cần có ít nhất 1 ký tự đặc biệt.")

    if password != confirm_password:
        errors.append("Mật khẩu xác nhận không khớp.")

    return errors
