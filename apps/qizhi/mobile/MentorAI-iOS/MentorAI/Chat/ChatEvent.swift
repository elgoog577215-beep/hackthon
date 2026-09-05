import Foundation

enum ChatEvent: Equatable {
    case start(sessionID: String)
    case loading(text: String)
    case thinking(text: String)
    case message(content: String)
    case card(payload: String)
    case error(message: String)
    case end
}
