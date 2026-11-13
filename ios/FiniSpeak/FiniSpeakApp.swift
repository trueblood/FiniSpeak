import SwiftUI

@main
struct FiniSpeakApp: App {
    @StateObject private var app = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .tint(FiniTheme.blue)
        }
    }
}
