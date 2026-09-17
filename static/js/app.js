const startCallButton = document.getElementById("startCall");
const statusText = document.getElementById("status");

startCallButton?.addEventListener("click", () => {
    statusText.textContent = "Call flow is ready for Firebase Auth and WebRTC integration.";
});
