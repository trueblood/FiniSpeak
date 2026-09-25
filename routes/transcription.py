from controllers.transcription_controller import handle_socket


def register_transcription_socket(sock):
    sock.route("/ws/transcription")(handle_socket)
