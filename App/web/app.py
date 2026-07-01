"""
Giao diện web Gradio cho hệ thống giám sát ổ gà.

File này chỉ nên chứa UI và callback wiring.
Không đặt thuật toán xử lý, không đặt SQL, không đặt render map chi tiết trong file này.
"""

import warnings

warnings.filterwarnings(
    "ignore",
    message="The 'theme' parameter in the Blocks constructor.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="The 'css' parameter in the Blocks constructor.*",
    category=DeprecationWarning,
)

import gradio as gr
from fastrtc import WebRTC

from web.adapter import (
    analyze_image_for_web,
    analyze_video_for_web,
    analyze_webrtc_frame_for_web,
    get_analysis_service,
    preview_media_gps_on_map,
    submit_latest_report_to_admin,
)
from web.config import CAMERA_SETUPS, DEFAULT_SETUP_DISPLAY_NAME
from web.map_service import render_map_html, update_current_location_on_map


setup_choices = list(CAMERA_SETUPS.keys())


CUSTOM_CSS = """
body {
    background: #0f0f0f;
}

#main-title {
    text-align: center;
}

/* ============================================================
   BẢNG KẾT QUẢ ẢNH / VIDEO
   ============================================================ */

.analysis-html {
    color: white !important;
}

.analysis-html table {
    width: 100% !important;
    color: white !important;
    background: #111111 !important;
    border-collapse: collapse !important;
    border: 1px solid #ffffff !important;
}

.analysis-html td {
    color: white !important;
    background: #111111 !important;
    padding: 12px 18px !important;
    vertical-align: top !important;
    border: 1px solid #ffffff !important;
}

.analysis-html b {
    color: white;
}

.analysis-html span {
    font-weight: bold;
}

.analysis-html details {
    width: 100% !important;
    box-sizing: border-box !important;
}

.analysis-html summary {
    color: white !important;
}

.analysis-html div {
    box-sizing: border-box !important;
}

.analysis-html iframe {
    width: 100% !important;
}

/* ============================================================
   CAMERA REALTIME
   ============================================================ */

.realtime-page {
    width: 100% !important;
    max-width: 1280px !important;
    margin: 0 auto !important;
    box-sizing: border-box !important;
}

.realtime-left-card,
.realtime-right-card {
    border: 1px solid #444 !important;
    border-radius: 12px !important;
    background: #111111 !important;
    box-sizing: border-box !important;
    position: relative !important;
    z-index: 1 !important;
}

.realtime-left-card {
    padding: 16px !important;
    overflow: visible !important;
}

.realtime-right-card {
    padding: 12px !important;
    overflow: hidden !important;
}

#realtime_webrtc,
#realtime_webrtc > div,
.webrtc-realtime {
    width: 100% !important;
    max-width: 100% !important;
    position: relative !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
    z-index: 1 !important;
    isolation: isolate !important;
}

#realtime_webrtc video,
#realtime_webrtc canvas,
.webrtc-realtime video,
.webrtc-realtime canvas {
    width: 100% !important;
    max-width: 100% !important;
    height: auto !important;
    max-height: 72vh !important;
    object-fit: contain !important;
    border-radius: 10px !important;
    background: #000000 !important;
    display: block !important;
    position: relative !important;
    z-index: 1 !important;
}

/* Chặn Record / Stop / Settings bị nổi fixed/sticky/absolute. */
#realtime_webrtc [style*="position: fixed"],
#realtime_webrtc [style*="position:fixed"],
#realtime_webrtc [style*="position: sticky"],
#realtime_webrtc [style*="position:sticky"],
#realtime_webrtc [style*="position: absolute"],
#realtime_webrtc [style*="position:absolute"],
.webrtc-realtime [style*="position: fixed"],
.webrtc-realtime [style*="position:fixed"],
.webrtc-realtime [style*="position: sticky"],
.webrtc-realtime [style*="position:sticky"],
.webrtc-realtime [style*="position: absolute"],
.webrtc-realtime [style*="position:absolute"] {
    position: relative !important;
    top: auto !important;
    bottom: auto !important;
    left: auto !important;
    right: auto !important;
    transform: none !important;
    z-index: 2 !important;
}

#realtime_webrtc [class*="control"],
#realtime_webrtc [class*="Control"],
#realtime_webrtc [class*="toolbar"],
#realtime_webrtc [class*="Toolbar"],
#realtime_webrtc [class*="settings"],
#realtime_webrtc [class*="Settings"],
#realtime_webrtc [class*="footer"],
#realtime_webrtc [class*="Footer"],
#realtime_webrtc [class*="button"],
#realtime_webrtc [class*="Button"],
.webrtc-realtime [class*="control"],
.webrtc-realtime [class*="Control"],
.webrtc-realtime [class*="toolbar"],
.webrtc-realtime [class*="Toolbar"],
.webrtc-realtime [class*="settings"],
.webrtc-realtime [class*="Settings"],
.webrtc-realtime [class*="footer"],
.webrtc-realtime [class*="Footer"],
.webrtc-realtime [class*="button"],
.webrtc-realtime [class*="Button"] {
    position: relative !important;
    top: auto !important;
    bottom: auto !important;
    left: auto !important;
    right: auto !important;
    transform: none !important;
    z-index: 2 !important;
}

#realtime_webrtc button,
#realtime_webrtc [role="button"],
#realtime_webrtc select,
.webrtc-realtime button,
.webrtc-realtime [role="button"],
.webrtc-realtime select {
    position: relative !important;
    z-index: 3 !important;
}

/* ============================================================
   MOBILE
   ============================================================ */

@media screen and (max-width: 768px) {
    .gradio-container {
        max-width: 100% !important;
        padding-left: 8px !important;
        padding-right: 8px !important;
        overflow-x: hidden !important;
    }

    .realtime-page {
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
    }

    .realtime-left-card,
    .realtime-right-card {
        width: 100% !important;
        max-width: 100% !important;
        margin-bottom: 12px !important;
        padding: 12px !important;
    }

    #realtime_webrtc,
    .webrtc-realtime {
        width: 100% !important;
        max-width: 100% !important;
        overflow: hidden !important;
    }

    #realtime_webrtc video,
    #realtime_webrtc canvas,
    .webrtc-realtime video,
    .webrtc-realtime canvas {
        width: 100% !important;
        max-width: 100% !important;
        max-height: 68vh !important;
        object-fit: contain !important;
    }
}
"""


# ============================================================
# 1. WRAPPER CALLBACKS
# ============================================================

def run_image(image_path, setup_display_name, detected_markers, browser_lat, browser_lng, route_points):
    return analyze_image_for_web(
        image_path=image_path,
        setup_display_name=setup_display_name,
        detected_markers=detected_markers,
        current_lat=browser_lat,
        current_lng=browser_lng,
        route_points=route_points,
    )


def run_video(video_path, setup_display_name, display_mode, detected_markers, browser_lat, browser_lng):
    return analyze_video_for_web(
        video_path=video_path,
        setup_display_name=setup_display_name,
        detected_markers=detected_markers,
        current_lat=browser_lat,
        current_lng=browser_lng,
        display_mode=display_mode,
    )


def run_webrtc(frame_rgb, setup_display_name, display_mode):
    return analyze_webrtc_frame_for_web(
        frame_rgb=frame_rgb,
        setup_display_name=setup_display_name,
        display_mode=display_mode,
    )


# ============================================================
# 2. BUILD UI
# ============================================================

with gr.Blocks(
    title="Hệ thống giám sát ổ gà",
    css=CUSTOM_CSS,
    theme=gr.themes.Soft(),
) as demo:
    detected_markers_state = gr.State([])
    route_points_state = gr.State([])

    gr.Markdown("# Hệ thống giám sát ổ gà", elem_id="main-title")

    # ========================================================
    # MAP ĐẦU TRANG
    # ========================================================

    gr.Markdown("## Bản đồ vị trí ổ gà")

    map_html = gr.HTML(
        value=render_map_html(),
        label="Map",
    )

    with gr.Row():
        btn_get_current_location = gr.Button("📍 Lấy vị trí hiện tại", variant="primary")
        btn_report = gr.Button("Báo cáo", variant="secondary")

    location_status = gr.Textbox(
        label="Trạng thái GPS",
        value="Chưa lấy vị trí hiện tại.",
        interactive=False,
    )

    report_status = gr.Textbox(
        label="Trạng thái báo cáo",
        value="Chưa gửi báo cáo.",
        interactive=False,
    )

    browser_lat = gr.Textbox(label="browser_lat", visible=False)
    browser_lng = gr.Textbox(label="browser_lng", visible=False)

    get_location_event = btn_get_current_location.click(
        fn=None,
        inputs=[],
        outputs=[browser_lat, browser_lng, location_status],
        js="""
        async () => {
            if (!navigator.geolocation) {
                return ["", "", "Trình duyệt không hỗ trợ lấy vị trí."];
            }

            try {
                const position = await new Promise((resolve, reject) => {
                    navigator.geolocation.getCurrentPosition(
                        resolve,
                        reject,
                        {
                            enableHighAccuracy: true,
                            timeout: 15000,
                            maximumAge: 0
                        }
                    );
                });

                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                const accuracy = position.coords.accuracy;

                return [
                    String(lat),
                    String(lng),
                    `Đã lấy GPS từ trình duyệt: ${lat.toFixed(6)}, ${lng.toFixed(6)} | Sai số khoảng ${accuracy.toFixed(1)} m`
                ];

            } catch (error) {
                let message = "Không lấy được vị trí hiện tại.";

                if (error.code === 1) {
                    message = "Bạn đã chặn quyền vị trí. Hãy vào cài đặt trình duyệt và cho phép Location/GPS.";
                } else if (error.code === 2) {
                    message = "Không xác định được vị trí. Hãy bật GPS/Vị trí trên thiết bị.";
                } else if (error.code === 3) {
                    message = "Lấy GPS quá lâu. Hãy thử lại hoặc đứng ngoài trời/thoáng hơn.";
                }

                return ["", "", message];
            }
        }
        """,
    )

    get_location_event.then(
        fn=update_current_location_on_map,
        inputs=[detected_markers_state, route_points_state, browser_lat, browser_lng],
        outputs=[map_html, location_status, browser_lat, browser_lng],
    )

    btn_report.click(
        fn=submit_latest_report_to_admin,
        inputs=[detected_markers_state, route_points_state, browser_lat, browser_lng],
        outputs=[map_html, report_status, detected_markers_state],
    )

    # ========================================================
    # TAB ẢNH
    # ========================================================

    with gr.Tab("Chụp / Upload ảnh"):
        with gr.Row():
            with gr.Column():
                image_setup = gr.Dropdown(
                    choices=setup_choices,
                    value=DEFAULT_SETUP_DISPLAY_NAME,
                    label="Chọn setup camera để tính diện tích",
                )

                input_image = gr.Image(
                    label="Chụp bằng camera sau hoặc upload ảnh",
                    sources=["webcam", "upload"],
                    type="filepath",
                    webcam_options=gr.WebcamOptions(
                        mirror=False,
                        constraints={
                            "video": {
                                "facingMode": {"ideal": "environment"}
                            }
                        },
                    ),
                )

                image_button = gr.Button("Phân tích ảnh", variant="primary")

            with gr.Column():
                output_image = gr.Image(
                    label="Ảnh kết quả",
                    type="filepath",
                )

        image_result_html = gr.HTML(
            label="Bảng phân tích ảnh",
            elem_classes=["analysis-html"],
        )

        image_button.click(
            fn=run_image,
            inputs=[
                input_image,
                image_setup,
                detected_markers_state,
                browser_lat,
                browser_lng,
                route_points_state,
            ],
            outputs=[
                output_image,
                image_result_html,
                map_html,
                detected_markers_state,
                route_points_state,
            ],
            show_progress=True,
        )

        input_image.change(
            fn=preview_media_gps_on_map,
            inputs=[input_image, detected_markers_state, browser_lat, browser_lng],
            outputs=[map_html, route_points_state],
            show_progress=False,
        )

    # ========================================================
    # TAB VIDEO
    # ========================================================

    with gr.Tab("Upload video"):
        with gr.Row():
            with gr.Column():
                video_setup = gr.Dropdown(
                    choices=setup_choices,
                    value=DEFAULT_SETUP_DISPLAY_NAME,
                    label="Chọn setup camera để tính diện tích",
                )

                # Trước đây run_video có tham số display_mode nhưng UI chưa truyền vào.
                # Bổ sung dropdown này để không bị lệch tham số khi bấm Phân tích video.
                video_display_mode = gr.Dropdown(
                    choices=["Laptop", "Điện thoại"],
                    value="Laptop",
                    label="Chế độ hiển thị chữ trong video kết quả",
                )

                input_video = gr.Video(label="Chọn video từ máy")
                video_button = gr.Button("Phân tích video", variant="primary")

            with gr.Column():
                output_video = gr.Video(label="Video kết quả")

        video_result_html = gr.HTML(
            label="Thông tin phân tích video",
            elem_classes=["analysis-html"],
        )

        video_button.click(
            fn=run_video,
            inputs=[
                input_video,
                video_setup,
                video_display_mode,
                detected_markers_state,
                browser_lat,
                browser_lng,
            ],
            outputs=[
                output_video,
                video_result_html,
                map_html,
                detected_markers_state,
                route_points_state,
            ],
            show_progress=True,
        )

        input_video.change(
            fn=preview_media_gps_on_map,
            inputs=[input_video, detected_markers_state, browser_lat, browser_lng],
            outputs=[map_html, route_points_state],
            show_progress=False,
        )

    # ========================================================
    # TAB CAMERA REALTIME WEBRTC
    # ========================================================

    with gr.Tab("Camera realtime"):
        with gr.Column(elem_classes=["realtime-page"]):
            gr.Markdown(
                """
### Camera realtime

Chức năng này dùng WebRTC/FastRTC để xử lý camera gần thời gian thực.  
Bên trái là phần chọn setup và hướng dẫn, bên phải là video kết quả realtime.
"""
            )

            with gr.Row():
                with gr.Column(scale=1, min_width=320, elem_classes=["realtime-left-card"]):
                    realtime_setup = gr.Dropdown(
                        choices=setup_choices,
                        value=DEFAULT_SETUP_DISPLAY_NAME,
                        label="Chọn setup camera để tính diện tích",
                    )

                    realtime_display_mode = gr.Dropdown(
                        choices=["Laptop", "Điện thoại"],
                        value="Laptop",
                        label="Chế độ hiển thị chữ realtime",
                    )

                    gr.Markdown(
                        """
**Cách dùng**

1. Chọn setup camera.  
2. Chọn **Laptop** nếu chạy trên máy tính, chọn **Điện thoại** nếu chạy trên điện thoại.  
3. Bấm **Record** để bật camera realtime.  
4. Bấm **Stop** để dừng camera.  
5. Nếu dùng điện thoại, nên mở bằng link HTTPS `gradio.live`.
"""
                    )

                with gr.Column(scale=2, min_width=520, elem_classes=["realtime-right-card"]):
                    realtime_stream = WebRTC(
                        label="Video kết quả realtime",
                        mode="send-receive",
                        modality="video",
                        mirror_webcam=False,
                        track_constraints={
                            "width": {"ideal": 480},
                            "height": {"ideal": 360},
                            "frameRate": {"ideal": 8, "max": 10},
                            "facingMode": {"ideal": "environment"},
                        },
                        elem_id="realtime_webrtc",
                        elem_classes=["webrtc-realtime"],
                    )

                    realtime_stream.stream(
                        fn=run_webrtc,
                        inputs=[realtime_stream, realtime_setup, realtime_display_mode],
                        outputs=[realtime_stream],
                        time_limit=180,
                    )

    # ========================================================
    # TAB HƯỚNG DẪN
    # ========================================================

    with gr.Tab("Hướng dẫn"):
        gr.Markdown(
            """
## Cách dùng GPS tự động

Web **không còn ô upload GPS CSV riêng**.

Nếu có GPS CSV, bạn đặt file vào một trong hai thư mục:

```text
App/web/gps_csv
App/web_gps_csv
```

Tên file GPS phải trùng với tên ảnh/video theo dạng:

```text
tên_ảnh_gps.csv
tên_video_gps.csv
```

Ví dụ:

```text
pothole 8.jpg       -> web/gps_csv/pothole 8_gps.csv
pothole 12.jpg      -> web/gps_csv/pothole 12_gps.csv
demo_video.mp4      -> web/gps_csv/demo_video_gps.csv
```

## Nếu không có GPS CSV

1. Bấm **📍 Lấy vị trí hiện tại** ở đầu trang.
2. Chờ trạng thái GPS hiện tọa độ.
3. Sau đó mới bấm **Phân tích ảnh** hoặc **Phân tích video**.

## Định dạng GPS CSV

File CSV cần có các cột:

```csv
timestamp,latitude,longitude
0,10.762622,106.660172
1,10.762700,106.660300
2,10.762850,106.660500
```

Có thể thêm cột `road_name`:

```csv
timestamp,latitude,longitude,road_name
0,10.762622,106.660172,Đường demo
1,10.762700,106.660300,Đường demo
2,10.762850,106.660500,Đường demo
```

## Test bằng điện thoại

1. Chạy `python run_web.py`.
2. Copy link dạng `https://xxxxx.gradio.live`.
3. Gửi link đó sang điện thoại.
4. Bấm **📍 Lấy vị trí hiện tại**.
5. Chụp ảnh hoặc upload ảnh/video.
6. Bấm phân tích.

## Lưu ý

- Nút **Lấy vị trí hiện tại** hoạt động ổn nhất khi dùng link HTTPS `gradio.live`.
- Nếu mở bằng `http://192.168.x.x:7860`, một số trình duyệt điện thoại có thể chặn GPS.
- Video kết quả được ghép bảng thông tin 2 cột ở bên dưới từng frame.
- Diện tích phụ thuộc vào setup camera và file homography `.npy`.
- Nếu chọn sai setup camera, diện tích có thể bị sai.
"""
        )


def launch_web(share=True, server_name="0.0.0.0", server_port=7860):
    """Hàm chạy web, dùng cho run_web.py hoặc chạy trực tiếp file này."""
    print("Đang tải model, vui lòng chờ...")
    get_analysis_service()
    print("Đã tải model xong.")

    demo.queue(max_size=10)
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
    )


if __name__ == "__main__":
    launch_web(share=True)
