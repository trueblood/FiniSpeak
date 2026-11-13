import SwiftUI

enum FiniTheme {
    static let blue = Color(red: 11 / 255, green: 108 / 255, blue: 255 / 255)
    static let ink = Color(red: 17 / 255, green: 24 / 255, blue: 39 / 255)
    static let mist = Color(red: 231 / 255, green: 235 / 255, blue: 240 / 255)
    static let line = Color(red: 230 / 255, green: 235 / 255, blue: 241 / 255)
    static let chip = Color(red: 236 / 255, green: 239 / 255, blue: 243 / 255)
    static let soft = Color(red: 243 / 255, green: 244 / 255, blue: 246 / 255)
    static let field = Color(red: 248 / 255, green: 250 / 255, blue: 252 / 255)
    static let search = Color(red: 242 / 255, green: 244 / 255, blue: 247 / 255)
    static let blurb = Color(red: 36 / 255, green: 82 / 255, blue: 122 / 255)
    static let avatarFill = Color(red: 219 / 255, green: 231 / 255, blue: 245 / 255)
    static let avatarInk = Color(red: 18 / 255, green: 60 / 255, blue: 105 / 255)
    static let star = Color(red: 245 / 255, green: 180 / 255, blue: 0)

    static func initials(_ name: String) -> String {
        let parts = name.split(whereSeparator: { $0 == " " || $0 == "@" || $0 == "." }).prefix(2)
        let letters = parts.compactMap { $0.first }.map { String($0) }.joined()
        return letters.isEmpty ? "FS" : letters.uppercased()
    }
}

struct FiniCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    }
}

struct FiniButton: View {
    let title: String
    var systemImage: String?
    var filled = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let systemImage { Image(systemName: systemImage) }
                Text(title)
            }
            .font(.body.weight(.semibold))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(filled ? FiniTheme.blue : Color(red: 243 / 255, green: 244 / 255, blue: 246 / 255), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .foregroundStyle(filled ? Color.white : FiniTheme.ink)
        }
        .buttonStyle(.plain)
    }
}

struct AvatarView: View {
    let name: String
    var size: CGFloat = 48

    var body: some View {
        Text(FiniTheme.initials(name))
            .font(.system(size: size * 0.32, weight: .heavy))
            .foregroundStyle(FiniTheme.avatarInk)
            .frame(width: size, height: size)
            .background(FiniTheme.avatarFill, in: Circle())
    }
}

struct StatusBanner: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(FiniTheme.ink)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color(red: 239 / 255, green: 246 / 255, blue: 1), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
