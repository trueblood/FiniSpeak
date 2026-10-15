from services.signaling_service import handle_signaling_socket


def register_signaling_socket(sock):
    sock.route("/ws/signaling")(handle_signaling_socket)
