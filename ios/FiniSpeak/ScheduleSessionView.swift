import SwiftUI

/// The same schedule screen as the website: this month, Audio or Video, 30/60/90 minutes, and an 11:00 AM start.
struct ScheduleSessionView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let profile: Interpreter
    var onInstant: () -> Void
    var onScheduled: (String) -> Void

    @State private var day = Calendar.current.startOfDay(for: Date())
    @State private var kind = "Audio"
    @State private var minutes = 60
    @State private var status = ""
    @State private var busy = false

    private var calendar: Calendar {
        var calendar = Calendar.current
        calendar.firstWeekday = 1
        return calendar
    }

    private var monthDate: Date {
        calendar.date(from: calendar.dateComponents([.year, .month], from: Date())) ?? Date()
    }

    private var slot: (start: Date, end: Date) {
        var parts = calendar.dateComponents([.year, .month, .day], from: day)
        parts.hour = 11
        parts.minute = 0
        let start = calendar.date(from: parts) ?? day
        let end = calendar.date(byAdding: .minute, value: minutes, to: start) ?? start
        return (start, end)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(monthTitle)
                        .font(.title3.weight(.heavy))
                        .foregroundStyle(FiniTheme.ink)
                    calendarGrid
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Session type")
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(FiniTheme.ink)
                        Picker("Session type", selection: $kind) {
                            Text("Audio").tag("Audio")
                            Text("Video").tag("Video")
                        }
                        .pickerStyle(.segmented)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Select a Duration")
                            .font(.subheadline.weight(.heavy))
                            .foregroundStyle(FiniTheme.avatarInk)
                        HStack(spacing: 8) {
                            ForEach([30, 60, 90], id: \.self) { value in
                                Button("\(value) min") { minutes = value }
                                    .font(.subheadline.weight(.heavy))
                                    .frame(maxWidth: .infinity, minHeight: 40)
                                    .foregroundStyle(minutes == value ? Color.white : FiniTheme.ink)
                                    .background(minutes == value ? FiniTheme.blue : FiniTheme.soft, in: Capsule())
                            }
                        }
                    }
                    slotCard
                    Button("Request Instant Call", action: onInstant)
                        .buttonStyle(ConceptFilledButtonStyle())
                    Button(busy ? "Scheduling…" : "Schedule a Session") { Task { await confirm() } }
                        .buttonStyle(ConceptFilledButtonStyle())
                        .disabled(busy)
                    if !status.isEmpty {
                        Text(status)
                            .font(.footnote)
                            .foregroundStyle(FiniTheme.ink)
                    }
                }
                .padding(18)
            }
            .background(Color.white)
            .navigationTitle("Schedule a Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .presentationDragIndicator(.visible)
    }

    private var monthTitle: String {
        let formatter = DateFormatter()
        formatter.locale = Locale.current
        formatter.dateFormat = "MMMM yyyy"
        return formatter.string(from: monthDate)
    }

    private var calendarGrid: some View {
        let symbols = ["S", "M", "T", "W", "T", "F", "S"]
        let days = calendar.range(of: .day, in: .month, for: monthDate) ?? 1..<2
        let first = calendar.date(from: calendar.dateComponents([.year, .month], from: monthDate)) ?? monthDate
        let blanks = max(0, calendar.component(.weekday, from: first) - 1)
        let columns = Array(repeating: GridItem(.flexible(), spacing: 4), count: 7)
        return LazyVGrid(columns: columns, spacing: 6) {
            ForEach(Array(symbols.enumerated()), id: \.offset) { _, symbol in
                Text(symbol)
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(FiniTheme.muted)
                    .frame(maxWidth: .infinity, minHeight: 28)
            }
            ForEach(0..<blanks, id: \.self) { _ in
                Color.clear.frame(height: 36)
            }
            ForEach(Array(days), id: \.self) { number in
                dayButton(number)
            }
        }
    }

    private func dayButton(_ number: Int) -> some View {
        let date = date(for: number)
        let selected = calendar.isDate(date, inSameDayAs: day)
        let past = date < calendar.startOfDay(for: Date())
        return Button {
            day = date
            status = ""
        } label: {
            Text("\(number)")
                .font(.subheadline.weight(.bold))
                .frame(maxWidth: .infinity, minHeight: 36)
                .foregroundStyle(selected ? Color.white : (past ? FiniTheme.muted : FiniTheme.ink))
                .background(selected ? FiniTheme.blue : Color.clear, in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(past)
    }

    private func date(for dayNumber: Int) -> Date {
        var parts = calendar.dateComponents([.year, .month], from: monthDate)
        parts.day = dayNumber
        return calendar.startOfDay(for: calendar.date(from: parts) ?? monthDate)
    }

    private var slotCard: some View {
        let range = timeRange(slot.start, slot.end)
        let dayLabel = calendar.isDateInToday(slot.start) ? "Today" : "\(calendar.component(.day, from: slot.start))"
        let meta = (profile.specialties + profile.languages).filter { !$0.isEmpty }.prefix(2).joined(separator: ", ")
        return HStack {
            Text(dayLabel)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(FiniTheme.muted)
            Text(range)
                .font(.body.weight(.heavy))
                .foregroundStyle(FiniTheme.ink)
            Spacer()
            Text(meta.isEmpty ? "Live session" : meta)
                .font(.caption.weight(.semibold))
                .foregroundStyle(FiniTheme.muted)
                .lineLimit(1)
        }
        .padding(14)
        .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
    }

    private func confirm() async {
        let start = slot.start
        guard start > Date() else {
            status = "That time has already passed. Choose a later day."
            return
        }
        busy = true
        defer { busy = false }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let language = profile.languages.first { !$0.isEmpty } ?? "Spanish"
        let purpose = "\(kind) session, \(minutes) min"
        do {
            _ = try await app.api.createSession(
                translatorId: profile.id,
                language: language,
                dialect: profile.dialects.first { !$0.isEmpty },
                specialty: profile.specialties.first { !$0.isEmpty },
                purpose: purpose,
                scheduledAt: formatter.string(from: start)
            )
            await app.refreshHistory()
            let message = "Scheduled for \(timeRange(start, slot.end)). \(profile.name) will be notified now, 5 minutes before, and when the session starts."
            onScheduled(message)
            dismiss()
        } catch {
            status = error.localizedDescription
        }
    }

    private func timeRange(_ start: Date, _ end: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale.current
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "h:mm a"
        return "\(formatter.string(from: start)) – \(formatter.string(from: end))"
    }
}
