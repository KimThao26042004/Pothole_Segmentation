"""
File chạy web chính.

Sau khi refactor, bạn chạy web bằng:

    python run_web.py

Không cần chạy trực tiếp web/app.py.
"""

from web.app import launch_web


if __name__ == "__main__":
    launch_web(
        share=True,
        server_name="0.0.0.0",
        server_port=7860,
    )
