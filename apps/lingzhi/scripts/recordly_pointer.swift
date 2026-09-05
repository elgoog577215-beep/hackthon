import CoreGraphics
import Foundation

let arguments = CommandLine.arguments

guard arguments.count >= 3,
      let targetX = Double(arguments[1]),
      let targetY = Double(arguments[2]) else {
    FileHandle.standardError.write(
        Data(
            "usage: recordly-pointer <x> <y> [steps] [step_delay] [move|click|scroll] [scroll_delta] [scroll_count]\n".utf8
        )
    )
    exit(2)
}

let steps = max(Int(arguments.count > 3 ? arguments[3] : "18") ?? 18, 1)
let stepDelay = max(Double(arguments.count > 4 ? arguments[4] : "0.010") ?? 0.010, 0)
let action = arguments.count > 5 ? arguments[5] : "click"
let target = CGPoint(x: targetX, y: targetY)
let start = CGEvent(source: nil)?.location ?? target
let eventSource = CGEventSource(stateID: .hidSystemState)

for index in 1...steps {
    let progress = Double(index) / Double(steps)
    let eased = progress * progress * (3.0 - 2.0 * progress)
    let point = CGPoint(
        x: start.x + (target.x - start.x) * eased,
        y: start.y + (target.y - start.y) * eased
    )
    let moveEvent = CGEvent(
        mouseEventSource: eventSource,
        mouseType: .mouseMoved,
        mouseCursorPosition: point,
        mouseButton: .left
    )
    moveEvent?.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: stepDelay)
}

if action == "scroll" {
    let scrollDelta = Int32(arguments.count > 6 ? arguments[6] : "-7") ?? -7
    let scrollCount = max(Int(arguments.count > 7 ? arguments[7] : "1") ?? 1, 1)
    for _ in 1...scrollCount {
        let scrollEvent = CGEvent(
            scrollWheelEvent2Source: nil,
            units: .line,
            wheelCount: 1,
            wheel1: scrollDelta,
            wheel2: 0,
            wheel3: 0
        )
        scrollEvent?.post(tap: .cghidEventTap)
        Thread.sleep(forTimeInterval: 0.08)
    }
    exit(0)
}

guard action == "click" else {
    exit(0)
}

let mouseDown = CGEvent(
    mouseEventSource: eventSource,
    mouseType: .leftMouseDown,
    mouseCursorPosition: target,
    mouseButton: .left
)
let mouseUp = CGEvent(
    mouseEventSource: eventSource,
    mouseType: .leftMouseUp,
    mouseCursorPosition: target,
    mouseButton: .left
)

mouseDown?.post(tap: .cghidEventTap)
Thread.sleep(forTimeInterval: 0.045)
mouseUp?.post(tap: .cghidEventTap)
