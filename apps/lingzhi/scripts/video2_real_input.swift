import CoreGraphics
import Foundation

func number(_ index: Int) -> Double {
    guard CommandLine.arguments.count > index,
          let value = Double(CommandLine.arguments[index]) else {
        fputs("missing numeric argument\n", stderr)
        exit(2)
    }
    return value
}

func move(to target: CGPoint, duration: Double) {
    let start = CGEvent(source: nil)?.location ?? target
    let steps = max(1, Int(duration / 0.014))
    for index in 0...steps {
        let progress = Double(index) / Double(steps)
        let eased = progress * progress * (3.0 - 2.0 * progress)
        let point = CGPoint(
            x: start.x + (target.x - start.x) * eased,
            y: start.y + (target.y - start.y) * eased
        )
        CGEvent(
            mouseEventSource: nil,
            mouseType: .mouseMoved,
            mouseCursorPosition: point,
            mouseButton: .left
        )?.post(tap: .cghidEventTap)
        usleep(14_000)
    }
}

func key(_ code: CGKeyCode, flags: CGEventFlags = []) {
    let down = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: true)
    down?.flags = flags
    down?.post(tap: .cghidEventTap)
    usleep(55_000)
    let up = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: false)
    up?.flags = flags
    up?.post(tap: .cghidEventTap)
}

guard CommandLine.arguments.count >= 2 else { exit(2) }
switch CommandLine.arguments[1] {
case "move":
    move(to: CGPoint(x: number(2), y: number(3)), duration: number(4))
case "click":
    let target = CGPoint(x: number(2), y: number(3))
    move(to: target, duration: number(4))
    usleep(100_000)
    CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: target, mouseButton: .left)?.post(tap: .cghidEventTap)
    usleep(85_000)
    CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: target, mouseButton: .left)?.post(tap: .cghidEventTap)
case "scroll":
    let target = CGPoint(x: number(2), y: number(3))
    move(to: target, duration: number(5))
    CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 1, wheel1: Int32(number(4)), wheel2: 0, wheel3: 0)?.post(tap: .cghidEventTap)
case "down": key(125)
case "enter": key(36)
case "delete": key(51)
case "escape": key(53)
case "select-all": key(0, flags: .maskCommand)
case "paste": key(9, flags: .maskCommand)
default:
    fputs("unknown command\n", stderr)
    exit(2)
}
