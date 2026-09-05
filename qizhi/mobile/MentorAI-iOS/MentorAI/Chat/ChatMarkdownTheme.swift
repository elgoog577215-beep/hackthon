import SwiftUI
import MarkdownUI

extension Theme {
    static let chatAssistant = Theme()
        .text {
            ForegroundColor(.primary)
            FontSize(15)
        }
        .code {
            FontFamilyVariant(.monospaced)
            FontSize(.em(0.92))
            BackgroundColor(Color.black.opacity(0.06))
        }
        .strong { FontWeight(.semibold) }
        .link { ForegroundColor(.accentColor) }
        .heading1 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(.em(1.45))
                }
                .markdownMargin(top: .em(0.6), bottom: .em(0.3))
        }
        .heading2 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(.em(1.3))
                }
                .markdownMargin(top: .em(0.55), bottom: .em(0.25))
        }
        .heading3 { configuration in
            configuration.label
                .markdownTextStyle {
                    FontWeight(.semibold)
                    FontSize(.em(1.15))
                }
                .markdownMargin(top: .em(0.5), bottom: .em(0.2))
        }
        .paragraph { configuration in
            configuration.label
                .relativeLineSpacing(.em(0.18))
                .markdownMargin(top: .em(0), bottom: .em(0.4))
        }
        .listItem { configuration in
            configuration.label
                .markdownMargin(top: .em(0.1), bottom: .em(0.1))
        }
        .blockquote { configuration in
            configuration.label
                .padding(.leading, 12)
                .overlay(alignment: .leading) {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.4))
                        .frame(width: 3)
                }
                .foregroundColor(.secondary)
        }
        .codeBlock { configuration in
            ScrollView(.horizontal, showsIndicators: false) {
                configuration.label
                    .relativeLineSpacing(.em(0.2))
                    .markdownTextStyle {
                        FontFamilyVariant(.monospaced)
                        FontSize(.em(0.88))
                    }
                    .padding(10)
            }
            .background(Color.black.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .markdownMargin(top: .em(0.4), bottom: .em(0.4))
        }
        .table { configuration in
            configuration.label
                .markdownTableBorderStyle(.init(color: .secondary.opacity(0.3)))
        }
}
