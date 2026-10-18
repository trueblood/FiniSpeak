from services.camera_relay import handle_camera_socket


def register_camera_socket(sock):
    sock.route("/ws/camera")(handle_camera_socket)
